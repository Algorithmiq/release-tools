# Copyright 2026 Algorithmiq
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Scratch git repositories for the tests of the release package and cliff.toml."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Repo:
    """A clone in `path` of the bare repository `origin`; the current directory."""

    path: Path
    origin: Path

    def git(self, *args: str) -> str:
        """Run git in the clone and return its stripped standard output."""
        result = subprocess.run(
            ["git", *args], cwd=self.path, check=True, text=True, capture_output=True
        )
        return result.stdout.strip()

    def commit(self, message: str, files: dict[str, str] | None = None) -> str:
        """Commit FILES (path -> content), or an empty change, and return the sha."""
        for name, content in (files or {}).items():
            (self.path / name).write_text(content, encoding="utf-8")
            self.git("add", name)
        self.git("commit", "--quiet", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def remote_tags(self) -> list[str]:
        """Return the tag names on origin."""
        lines = self.git("ls-remote", "--tags", "--refs", "origin").splitlines()
        return sorted(line.split("refs/tags/")[1] for line in lines)


@pytest.fixture(autouse=True)
def no_github_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset GITHUB_REPOSITORY, which GitHub Actions also sets when it runs the tests.

    cliff.toml links PR numbers to that repository; tests that want links set it.
    """
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
    """Return an empty clone with a local bare origin, as the current directory.

    Git runs with a fixed identity and without the user's or the system's
    configuration, and the GitHub Actions variables that the release package
    reads are unset.
    """
    empty_config = tmp_path / "gitconfig"
    empty_config.touch()
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Release Tester")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "tester@example.com")
    for name in ("GITHUB_OUTPUT", "GITHUB_REF_NAME", "VERSION_FILES"):
        monkeypatch.delenv(name, raising=False)

    origin = tmp_path / "origin.git"
    path = tmp_path / "work"
    subprocess.run(
        ["git", "init", "--quiet", "--bare", "--initial-branch=main", str(origin)],
        check=True,
    )
    subprocess.run(
        ["git", "init", "--quiet", "--initial-branch=main", str(path)], check=True
    )
    clone = Repo(path=path, origin=origin)
    clone.git("remote", "add", "origin", str(origin))
    monkeypatch.chdir(path)
    return clone


# The stand-in for `gh api graphql`, run by the Python of the tests. It reads the state
# that FakeGitHub writes, answers the aliases of the query, records their numbers, and
# exits with status 1 when the answer has errors, as gh does.
FAKE_GH = r"""
import json, os, re, sys

args = sys.argv[1:]
assert args[:2] == ["api", "graphql"], args
query = next(a for a in args if a.startswith("query="))
numbers = [int(n) for n in re.findall(r"pr(\d+): pullRequest", query)]
state_path = os.environ["FAKE_GH_STATE"]
with open(state_path + ".calls", "a") as calls:
    calls.write(json.dumps(numbers) + "\n")
with open(state_path) as f:
    state = json.load(f)
if state["error"]:
    print(json.dumps({"message": state["error"], "status": "403"}))
    print(f"gh: {state['error']} (HTTP 403)", file=sys.stderr)
    sys.exit(1)
data, errors = {}, []
for n in numbers:
    pr = state["prs"].get(str(n))
    if pr is None:
        data[f"pr{n}"] = None
        message = f"Could not resolve to a PullRequest with the number of {n}."
        errors.append({"type": "NOT_FOUND", "path": ["repository", f"pr{n}"],
                       "message": message})
    else:
        data[f"pr{n}"] = {"body": pr["body"], "merged": pr["merged"],
                          "mergeCommit": {"oid": pr["oid"]} if pr["oid"] else None}
answer = {"data": {"repository": data}}
if errors:
    answer["errors"] = errors
    print(f"gh: {errors[0]['message']}", file=sys.stderr)
print(json.dumps(answer))
sys.exit(1 if errors else 0)
"""


@dataclass(frozen=True)
class FakeGitHub:
    """The GitHub API behind a stand-in for `gh api graphql`, with canned answers.

    It answers the query of release.descriptions from the pull requests added here,
    and records the numbers of each query.
    """

    state: Path
    gh: Path

    def _update(self, **changes: Any) -> None:  # noqa: ANN401
        state = json.loads(self.state.read_text(encoding="utf-8"))
        state.update({k: v for k, v in changes.items() if k != "pr"})
        if "pr" in changes:
            number, pr = changes["pr"]
            state["prs"][str(number)] = pr
        self.state.write_text(json.dumps(state), encoding="utf-8")

    def add(
        self, number: int, body: str | None, oid: str, *, merged: bool = True
    ) -> None:
        """Add the pull request NUMBER, merged (or not) as the commit OID."""
        self._update(pr=(number, {"body": body, "merged": merged, "oid": oid}))

    def fail(self, message: str) -> None:
        """Make every query fail with MESSAGE, as when the API is rate-limited."""
        self._update(error=message)

    @property
    def calls(self) -> list[list[int]]:
        """The pull request numbers of each query so far."""
        calls = Path(f"{self.state}.calls")
        if not calls.exists():
            return []
        return [json.loads(line) for line in calls.read_text().splitlines()]


@pytest.fixture
def github(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeGitHub:
    """Return a fake GitHub API: `gh` is first on PATH, and the repository is set.

    FAKE_GH is the stand-in itself, for the tests that have a `gh` of their own.
    """
    directory = tmp_path / "fake-gh-bin"
    directory.mkdir()
    gh = directory / "gh"
    script = directory / "fake-gh.py"
    script.write_text(FAKE_GH, encoding="utf-8")
    gh.write_text(
        f'#!/usr/bin/env bash\nexec "{sys.executable}" "{script}" "$@"\n',
        encoding="utf-8",
    )
    gh.chmod(0o755)
    state = tmp_path / "fake-gh-state.json"
    state.write_text(json.dumps({"prs": {}, "error": None}), encoding="utf-8")
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GH", str(gh))
    monkeypatch.setenv("FAKE_GH_STATE", str(state))
    monkeypatch.setenv("GITHUB_REPOSITORY", "Algorithmiq/example")
    return FakeGitHub(state=state, gh=gh)

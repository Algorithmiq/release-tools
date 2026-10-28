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

"""Scratch git repositories for the tests of release.py and cliff.toml."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

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


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
    """Return an empty clone with a local bare origin, as the current directory.

    Git runs with a fixed identity and without the user's or the system's
    configuration, and the GitHub Actions variables that release.py reads are unset.
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

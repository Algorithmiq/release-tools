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

"""Whole release flows, driven as the jobs of release.yml and backport.yml drive them.

Each step runs the release package in a subprocess with the environment of the workflow
step (GITHUB_OUTPUT, GITHUB_REF_NAME, VERSION_FILES, ...) against a clone with a local
bare origin, with a stand-in for gh that finds no open PR. Merging a PR is simulated by
a squash commit titled as GitHub titles it. Every action happens a minute after the
previous one: git-cliff tells releases apart by their dates.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from conftest import ROOT

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from conftest import Repo

VERSION_FILES = "VERSION pyproject.toml"
PYPROJECT = '[project]\nname = "demo"\nversion = "0.0.0"\n'


class Workflow:
    """Runs the steps of the release and backport jobs."""

    def __init__(
        self, repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Run the steps in REPO, with their files under TMP_PATH."""
        self.repo = repo
        self.tmp_path = tmp_path
        self.monkeypatch = monkeypatch
        self.clock = 0
        self.steps = 0
        self.changes = 0
        self.bin_dir = tmp_path / "bin"
        self.bin_dir.mkdir()
        gh = self.bin_dir / "gh"
        gh.write_text(
            f'#!/usr/bin/env bash\necho "$*" >> "{tmp_path}/gh-calls"\n',
            encoding="utf-8",
        )
        gh.chmod(0o755)
        self.runner_temp = tmp_path / "runner-temp"
        self.runner_temp.mkdir()

    def env(self, **extra: str) -> dict[str, str]:
        """Return the environment of a step, with EXTRA."""
        return {
            **os.environ,
            "PATH": f"{self.bin_dir}{os.pathsep}{os.environ['PATH']}",
            "RUNNER_TEMP": str(self.runner_temp),
            "RELEASE_TOOLS": str(ROOT),
            "VERSION_FILES": VERSION_FILES,
            "GH_TOKEN": "token",
            **extra,
        }

    def tick(self) -> None:
        """Move the clock a minute on: later commits and tags get later dates."""
        self.clock += 1
        when = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=self.clock)
        for role in ("AUTHOR", "COMMITTER"):
            self.monkeypatch.setenv(f"GIT_{role}_DATE", when.isoformat())

    def gh_calls(self) -> list[str]:
        """Return the gh calls so far."""
        return (self.tmp_path / "gh-calls").read_text(encoding="utf-8").splitlines()

    def step(self, *argv: str, ref_name: str) -> dict[str, str]:
        """Run `release ARGV` on the ref REF_NAME and return the step's outputs."""
        self.tick()
        self.steps += 1
        outputs = self.tmp_path / f"output-{self.steps}"
        subprocess.run(
            [sys.executable, str(ROOT / "release"), *argv],
            cwd=self.repo.path,
            env=self.env(GITHUB_OUTPUT=str(outputs), GITHUB_REF_NAME=ref_name),
            check=True,
            capture_output=True,
            text=True,
        )
        if not outputs.exists():  # set-version and sync-changelog have no outputs
            return {}
        lines = outputs.read_text(encoding="utf-8").splitlines()
        return dict(line.split("=", 1) for line in lines)

    def release_pr(self, series: str, pending: str, stage: str, head: str) -> None:
        """Run the release-pr command as the start and update jobs run it."""
        self.step(
            "release-pr",
            "--series",
            series,
            "--version",
            pending,
            "--stage",
            stage,
            "--head",
            head,
            ref_name=f"release/{series}",
        )

    def checkout(self, ref: str) -> None:
        """Fetch origin and check out REF detached, as actions/checkout does."""
        self.repo.git("fetch", "--quiet", "--tags", "origin")
        self.repo.git("checkout", "--quiet", "--detach", f"origin/{ref}")

    def start(self, bump: str = "minor", stage: str = "rc") -> dict[str, str]:
        """Run the `start` job on main."""
        self.checkout("main")
        started = self.step("start", "--bump", bump, "--stage", stage, ref_name="main")
        if started["action"] == "promote":
            self.release_pr(
                started["series"], started["version"], "rc", started["head"]
            )
        return started

    def update(self, branch: str) -> dict[str, str]:
        """Run the `update` job for a push to BRANCH; return the plan."""
        self.checkout(branch)
        head = self.repo.git("rev-parse", "HEAD")
        plan = self.step("plan", ref_name=branch)
        if plan["action"] in {"prerelease", "final"}:
            final = ["--final"] if plan["action"] == "final" else []
            self.step("tag", plan["tag_version"], *final, ref_name=branch)
        if plan["action"] in {"prerelease", "pr"}:
            self.release_pr(plan["series"], plan["pending"], plan["stage"], head)
        return plan

    def merge(self, branch: str, title: str) -> str:
        """Squash-merge a PR titled TITLE, with a file of its own, into BRANCH."""
        self.tick()
        self.changes += 1
        self.checkout(branch)
        sha = self.repo.commit(title, {f"change-{self.changes}.txt": title})
        self.repo.git("push", "--quiet", "origin", f"HEAD:refs/heads/{branch}")
        return sha

    def backport(self, title: str) -> list[str]:
        """Merge the fix TITLE into main, then its backport PRs; return the targets."""
        sha = self.merge("main", title)
        targets = self.step("backport-targets", ref_name="main")["branches"].split()
        for branch in targets:
            self.checkout(branch)
            self.tick()
            self.repo.git("cherry-pick", sha)
            self.repo.git("push", "--quiet", "origin", f"HEAD:refs/heads/{branch}")
        return targets

    def merge_release_pr(self, series: str, number: int) -> None:
        """Squash-merge the release PR release-pr/SERIES into release/SERIES."""
        branch = f"release/{series}"
        self.checkout(branch)
        pr_head = f"origin/release-pr/{series}"
        title = self.repo.git("log", "-1", "--format=%s", pr_head)
        self.tick()
        self.repo.git("checkout", pr_head, "--", ".")
        self.repo.git("commit", "--quiet", "-m", f"{title} (#{number})")
        self.repo.git("push", "--quiet", "origin", f"HEAD:refs/heads/{branch}")

    def sync_changelog(self, tag: str) -> None:
        """Run the `sync-changelog` job for TAG and merge its PR into main."""
        self.checkout("main")
        self.step("sync-changelog", tag, ref_name=tag)
        self.repo.git("add", "CHANGELOG.md")
        if self.repo.git("diff", "--cached", "--name-only"):
            self.tick()
            self.repo.git(
                "commit", "--quiet", "-m", f"chore: update changelog for {tag}"
            )
            self.repo.git("push", "--quiet", "origin", "HEAD:refs/heads/main")


def tagged_file(repo: Repo, ref: str, name: str) -> str:
    """Return the content of NAME in the commit that REF points to."""
    return repo.git("show", f"{ref}^{{commit}}:{name}")


def headings(text: str) -> list[str]:
    """Return the versions of the sections of a CHANGELOG.md."""
    return [line.split()[1] for line in text.splitlines() if line.startswith("## ")]


def section(text: str, version: str) -> str:
    """Return the section of VERSION in a CHANGELOG.md."""
    return text.split(f"## {version} (")[1].split("\n## ", maxsplit=1)[0]


def start_repository(repo: Repo) -> None:
    """Commit the version files, tag v0.0.0 and push main."""
    repo.commit("chore: start", {"VERSION": "0.0.0\n", "pyproject.toml": PYPROJECT})
    repo.git("tag", "-a", "v0.0.0", "-m", "Start of the changelog")
    repo.git("push", "--quiet", "--follow-tags", "origin", "HEAD:refs/heads/main")


def test_two_release_series(
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = Workflow(repo, tmp_path, monkeypatch)
    flow.tick()  # v0.0.0 too: every date comes from the clock
    start_repository(repo)
    flow.merge("main", "feat: first feature (#1)")

    # Start 0.1 at a release candidate: start tags rc1 with the new branch, and the
    # push of the branch only opens the release PR.
    started = flow.start()
    assert (started["action"], started["branch"], started["tag_version"]) == (
        "cut",
        "release/0.1",
        "0.1.0rc1",
    )
    assert tagged_file(repo, "v0.1.0rc1", "VERSION") == "0.1.0rc1"
    assert flow.update("release/0.1")["action"] == "pr"

    # Starting it again is refused while main moves on.
    flow.checkout("main")
    rejected = subprocess.run(
        [sys.executable, str(ROOT / "release"), "start"],
        cwd=repo.path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode == 1
    assert "release/0.1 is already at release candidates" in rejected.stdout
    flow.merge("main", "feat: second feature (#2)")

    # A backport before 0.1.0 tags rc2; the release branch itself keeps 0.0.0.
    flow.merge("release/0.1", "fix: a bug (#3)")
    assert flow.update("release/0.1")["tag_version"] == "0.1.0rc2"
    assert tagged_file(repo, "origin/release/0.1", "VERSION") == "0.0.0"

    # Merging the release PR tags 0.1.0 on the merge commit itself.
    flow.merge_release_pr("0.1", 4)
    plan = flow.update("release/0.1")
    assert (plan["action"], plan["tag_version"]) == ("final", "0.1.0")
    assert repo.git("rev-parse", "v0.1.0^{commit}") == repo.git(
        "rev-parse", "origin/release/0.1"
    )
    assert tagged_file(repo, "v0.1.0", "VERSION") == "0.1.0"

    # After 0.1.0, backports only update the release PR for 0.1.1; no candidates.
    flow.merge("release/0.1", "fix: another bug (#5)")
    assert flow.update("release/0.1") == {
        "series": "0.1",
        "action": "pr",
        "tag_version": "",
        "pending": "0.1.1",
        "stage": "released",
        "previous": "",
    }
    flow.merge_release_pr("0.1", 6)
    assert flow.update("release/0.1")["tag_version"] == "0.1.1"

    # The next minor release, then a major one.
    assert flow.start()["tag_version"] == "0.2.0rc1"
    flow.update("release/0.2")
    flow.merge_release_pr("0.2", 7)
    assert flow.update("release/0.2")["tag_version"] == "0.2.0"
    started = flow.start("major")
    assert (started["branch"], started["tag_version"]) == ("release/1.0", "1.0.0rc1")

    assert repo.remote_tags() == [
        "v0.0.0",
        "v0.1.0",
        "v0.1.0rc1",
        "v0.1.0rc2",
        "v0.1.1",
        "v0.2.0",
        "v0.2.0rc1",
        "v1.0.0rc1",
    ]


def test_alphas_betas_candidates_and_two_lines(  # noqa: PLR0915
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The branching model in README.md, with 0.1 and 0.2 for 1.1 and 1.2.
    flow = Workflow(repo, tmp_path, monkeypatch)
    flow.tick()  # v0.0.0 too: every date comes from the clock
    start_repository(repo)
    flow.merge("main", "feat: A (#1)")

    # 1. 0.1.0 is out, and its changelog is on main.
    flow.start()
    flow.update("release/0.1")
    flow.merge_release_pr("0.1", 2)
    flow.update("release/0.1")
    flow.sync_changelog("v0.1.0")

    # 2. Alphas: tags on main, no branch.
    flow.merge("main", "feat: B (#3)")
    assert flow.start(stage="alpha")["tag_version"] == "0.2.0a1"
    flow.merge("main", "feat: C (#4)")
    assert flow.start(stage="alpha")["tag_version"] == "0.2.0a2"
    assert repo.git("ls-remote", "--heads", "origin", "release/0.2") == ""

    # 3. Beta: the feature freeze. The release PR opens as a draft.
    flow.merge("main", "feat: D (#5)")
    started = flow.start(stage="beta")
    assert (started["branch"], started["tag_version"]) == ("release/0.2", "0.2.0b1")
    plan = flow.update("release/0.2")
    assert (plan["action"], plan["stage"]) == ("pr", "beta")
    assert flow.gh_calls()[-1].startswith("pr create --draft --head release-pr/0.2 ")
    flow.merge("main", "feat: E (#6)")  # after the freeze: waits for 0.3
    # A fix reaches both lines while 0.2 is in beta.
    assert flow.backport("fix: F (#7)") == ["release/0.2", "release/0.1"]
    assert flow.update("release/0.2")["tag_version"] == "0.2.0b2"
    assert flow.update("release/0.1")["pending"] == "0.1.1"
    flow.merge_release_pr("0.1", 8)
    assert flow.update("release/0.1")["tag_version"] == "0.1.1"
    flow.sync_changelog("v0.1.1")

    # 4. Release candidates: the promotion tags rc1 and updates the release PR.
    promoted = flow.start(stage="rc")
    assert (promoted["action"], promoted["tag_version"]) == ("promote", "0.2.0rc1")
    assert flow.gh_calls()[-1].startswith("pr create --head release-pr/0.2 ")
    assert flow.backport("fix: G (#9)") == ["release/0.2", "release/0.1"]
    assert flow.update("release/0.2")["tag_version"] == "0.2.0rc2"
    flow.update("release/0.1")
    flow.merge_release_pr("0.1", 10)
    assert flow.update("release/0.1")["tag_version"] == "0.1.2"
    flow.sync_changelog("v0.1.2")

    # 5. Final, written before v0.1.2 (a stale release PR), then a patch: one line.
    flow.merge_release_pr("0.2", 11)
    plan = flow.update("release/0.2")
    assert (plan["action"], plan["tag_version"], plan["previous"]) == (
        "final",
        "0.2.0",
        "0.1",
    )
    flow.sync_changelog("v0.2.0")
    assert flow.backport("fix: H (#12)") == ["release/0.2"]
    assert flow.update("release/0.2")["pending"] == "0.2.1"
    flow.merge_release_pr("0.2", 13)
    assert flow.update("release/0.2")["tag_version"] == "0.2.1"
    flow.sync_changelog("v0.2.1")

    flow.checkout("main")
    changelog = (repo.path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert headings(changelog) == ["0.2.1", "0.2.0", "0.1.2", "0.1.1", "0.1.0"]
    released = section(changelog, "0.2.0")
    for entry in ("B (#3)", "C (#4)", "D (#5)", "F (#7)", "G (#9)"):
        assert f"- {entry}" in released
    assert "- E (#6)" not in released
    assert "- A (#1)" not in released
    assert "- F (#7)" in section(changelog, "0.1.1")
    # The file in the stale v0.2.0 tag lacks 0.1.2; main has it.
    assert headings(tagged_file(repo, "v0.2.0", "CHANGELOG.md")) == [
        "0.2.0",
        "0.1.1",
        "0.1.0",
    ]
    assert repo.remote_tags() == [
        "v0.0.0",
        "v0.1.0",
        "v0.1.0rc1",
        "v0.1.1",
        "v0.1.2",
        "v0.2.0",
        "v0.2.0a1",
        "v0.2.0a2",
        "v0.2.0b1",
        "v0.2.0b2",
        "v0.2.0rc1",
        "v0.2.0rc2",
        "v0.2.1",
    ]

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

"""release.py and the release PR step driven as .github/workflows/release.yml does.

Each step runs the script in a subprocess with the environment of the workflow step
(GITHUB_OUTPUT, GITHUB_REF_NAME, VERSION_FILES) against a clone with a local bare
origin. Merging a PR is simulated by a squash commit titled as GitHub titles it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

from conftest import ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import Repo

VERSION_FILES = "VERSION pyproject.toml"
PYPROJECT = '[project]\nname = "demo"\nversion = "0.0.0"\n'


class Workflow:
    """Runs release.py steps the way the jobs of release.yml run them."""

    def __init__(self, repo: Repo, tmp_path: Path) -> None:
        """Run the steps in REPO, with their GITHUB_OUTPUT files under TMP_PATH."""
        self.repo = repo
        self.tmp_path = tmp_path
        self.steps = 0

    def step(self, *argv: str, ref_name: str) -> dict[str, str]:
        """Run `release.py ARGV` on the ref REF_NAME and return the step's outputs."""
        self.steps += 1
        outputs = self.tmp_path / f"output-{self.steps}"
        env = {
            **os.environ,
            "GITHUB_OUTPUT": str(outputs),
            "GITHUB_REF_NAME": ref_name,
            "VERSION_FILES": VERSION_FILES,
        }
        subprocess.run(
            [sys.executable, str(ROOT / "release.py"), *argv],
            cwd=self.repo.path,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        if not outputs.exists():  # set-version has no outputs
            return {}
        lines = outputs.read_text(encoding="utf-8").splitlines()
        return dict(line.split("=", 1) for line in lines)

    def checkout(self, ref: str) -> None:
        """Fetch origin and check out REF detached, as actions/checkout does."""
        self.repo.git("fetch", "--quiet", "--tags", "origin")
        self.repo.git("checkout", "--quiet", "--detach", f"origin/{ref}")

    def update(self, branch: str) -> dict[str, str]:
        """Run the `update` job for a push to BRANCH; return the plan."""
        self.checkout(branch)
        plan = self.step("plan", ref_name=branch)
        if plan["action"] in {"prerelease", "final"}:
            final = ["--final"] if plan["action"] == "final" else []
            self.step("tag", plan["tag_version"], *final, ref_name=branch)
        return plan

    def merge_release_pr(self, branch: str, pending: str, number: int) -> None:
        """Write the release PR for PENDING and squash-merge it into BRANCH."""
        self.checkout(branch)
        self.step("set-version", pending, ref_name=branch)
        self.repo.git("add", "VERSION", "pyproject.toml")
        self.repo.git(
            "commit", "--quiet", "-m", f"chore: release v{pending} (#{number})"
        )
        self.repo.git("push", "--quiet", "origin", f"HEAD:refs/heads/{branch}")

    def merge(self, branch: str, title: str) -> None:
        """Squash-merge a PR titled TITLE into BRANCH."""
        self.checkout(branch)
        self.repo.commit(title)
        self.repo.git("push", "--quiet", "origin", f"HEAD:refs/heads/{branch}")

    def start(self, bump: str = "minor", stage: str = "rc") -> dict[str, str]:
        """Run the `start` job on main: it tags, and pushes any new release branch."""
        self.checkout("main")
        return self.step("start", "--bump", bump, "--stage", stage, ref_name="main")


def tagged_file(repo: Repo, tag: str, name: str) -> str:
    """Return the content of NAME in the commit that TAG points to."""
    return repo.git("show", f"{tag}^{{commit}}:{name}")


def test_two_release_series(repo: Repo, tmp_path: Path) -> None:
    flow = Workflow(repo, tmp_path)
    repo.commit("chore: start", {"VERSION": "0.0.0\n", "pyproject.toml": PYPROJECT})
    repo.git("tag", "-a", "v0.0.0", "-m", "Start of the changelog")
    repo.git("push", "--quiet", "--follow-tags", "origin", "HEAD:refs/heads/main")
    flow.merge("main", "feat: first feature (#1)")

    # Start 0.1: start tags rc1 and pushes the branch.
    started = flow.start()
    assert (started["branch"], started["tag_version"]) == ("release/0.1", "0.1.0rc1")
    assert flow.update("release/0.1")["action"] == "pr"
    assert tagged_file(repo, "v0.1.0rc1", "VERSION") == "0.1.0rc1"

    # Starting it again is refused while main moves on.
    flow.checkout("main")
    rejected = subprocess.run(
        [sys.executable, str(ROOT / "release.py"), "start"],
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
    flow.merge_release_pr("release/0.1", "0.1.0", 4)
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
    flow.merge_release_pr("release/0.1", "0.1.1", 6)
    assert flow.update("release/0.1")["tag_version"] == "0.1.1"

    # The next minor release, then a major one.
    assert flow.start()["tag_version"] == "0.2.0rc1"
    assert flow.update("release/0.2")["action"] == "pr"
    flow.merge_release_pr("release/0.2", "0.2.0", 7)
    assert flow.update("release/0.2")["tag_version"] == "0.2.0"
    started = flow.start("major")
    assert (started["branch"], started["tag_version"]) == ("release/1.0", "1.0.0rc1")

    assert sorted(repo.remote_tags()) == [
        "v0.0.0",
        "v0.1.0",
        "v0.1.0rc1",
        "v0.1.0rc2",
        "v0.1.1",
        "v0.2.0",
        "v0.2.0rc1",
        "v1.0.0rc1",
    ]

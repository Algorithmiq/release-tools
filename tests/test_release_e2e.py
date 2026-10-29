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

import yaml
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

    def start(self, bump: str = "minor") -> dict[str, str]:
        """Run the `start` job on main and push the new release branch."""
        self.checkout("main")
        started = self.step("start", "--bump", bump, ref_name="main")
        self.repo.git(
            "push", "--quiet", "origin", f"HEAD:refs/heads/{started['branch']}"
        )
        return started


def tagged_file(repo: Repo, tag: str, name: str) -> str:
    """Return the content of NAME in the commit that TAG points to."""
    return repo.git("show", f"{tag}^{{commit}}:{name}")


def test_two_release_series(repo: Repo, tmp_path: Path) -> None:
    flow = Workflow(repo, tmp_path)
    repo.commit("chore: start", {"VERSION": "0.0.0\n", "pyproject.toml": PYPROJECT})
    repo.git("tag", "-a", "v0.0.0", "-m", "Start of the changelog")
    repo.git("push", "--quiet", "--follow-tags", "origin", "HEAD:refs/heads/main")
    flow.merge("main", "feat: first feature (#1)")

    # Start 0.1: the first push to the branch tags rc1.
    assert flow.start() == {"branch": "release/0.1", "version": "0.1.0"}
    assert flow.update("release/0.1")["tag_version"] == "0.1.0rc1"
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
    assert "release/0.1 already exists" in rejected.stdout
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
    assert flow.start()["branch"] == "release/0.2"
    assert flow.update("release/0.2")["tag_version"] == "0.2.0rc1"
    flow.merge_release_pr("release/0.2", "0.2.0", 7)
    assert flow.update("release/0.2")["tag_version"] == "0.2.0"
    assert flow.start("major") == {"branch": "release/1.0", "version": "1.0.0"}
    assert flow.update("release/1.0")["tag_version"] == "1.0.0rc1"

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


def workflow_step(job: str, name: str) -> str:
    """Return the run: script of the step NAME of JOB in the reusable release.yml."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    (step,) = [s for s in workflow["jobs"][job]["steps"] if s.get("name") == name]
    return step["run"]


def test_release_pr_step(repo: Repo, tmp_path: Path) -> None:
    # The "Open or update the release PR" step of release.yml, run as the runner runs
    # it, with a stand-in for gh that records its calls and finds no open PR.
    repo.commit("chore: start", {"VERSION": "0.0.0\n", "pyproject.toml": PYPROJECT})
    repo.git("tag", "-a", "v0.0.0", "-m", "start")
    repo.commit("feat!: 💥 drop the old API (#1)\n\n## Migration\n\nUse `new()`.\n")
    sha = repo.commit("fix: 🐛 a fix (#2)")
    repo.git(
        "push", "--quiet", "--follow-tags", "origin", "HEAD:refs/heads/release/0.1"
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        f'#!/usr/bin/env bash\necho "$*" >> "{tmp_path}/gh-calls"\n'
        f'if [[ "$1 $2" == "pr create" ]]; then\n'
        f'  cp "${{@: -1}}" "{tmp_path}/body.md"\n'
        "fi\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": str(runner_temp),
        "RELEASE_TOOLS": str(ROOT),
        "VERSION_FILES": VERSION_FILES,
        "GITHUB_SHA": sha,
        "GH_TOKEN": "token",
        "PENDING": "0.1.0",
        "SERIES": "0.1",
        "BASE": "release/0.1",
    }
    script = workflow_step("update", "Open or update the release PR")
    subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        cwd=repo.path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    pr_head = "origin/release-pr/0.1"
    repo.git("fetch", "--quiet", "origin")
    assert repo.git("log", "-1", "--format=%s", pr_head) == "chore: release v0.1.0"
    assert repo.git("rev-parse", f"{pr_head}^") == sha
    assert repo.git("show", f"{pr_head}:VERSION") == "0.1.0"
    changelog = repo.git("show", f"{pr_head}:CHANGELOG.md")
    assert changelog.startswith("# Changelog\n\nAll notable changes")
    assert (
        "### Breaking changes\n\n- Drop the old API (#1)\n\n  Use `new()`." in changelog
    )
    assert repo.git("status", "--porcelain") == ""  # nothing left in the working tree
    calls = (tmp_path / "gh-calls").read_text().splitlines()
    assert calls[0].startswith("pr list --head release-pr/0.1 --base release/0.1")
    assert calls[1].startswith(
        "pr create --head release-pr/0.1 --base release/0.1 "
        "--title chore: release v0.1.0 --body-file "
    )
    body = (tmp_path / "body.md").read_text()
    assert body.startswith("Merging this PR releases **v0.1.0**.")
    assert "- A fix (#2)" in body

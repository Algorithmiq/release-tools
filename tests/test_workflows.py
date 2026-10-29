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

"""Tests of the contracts between the reusable workflows and release.py.

actionlint checks the workflows themselves; these check that they only read the
outputs release.py writes and pass what release-pr.sh reads.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import TYPE_CHECKING, Any

import pytest
import yaml
from conftest import ROOT

if TYPE_CHECKING:
    from pathlib import Path

WORKFLOWS = ROOT / ".github" / "workflows"

# The outputs of the release.py commands, by the id of the step that runs them; the
# tests of release.py pin each command's outputs exactly.
OUTPUTS = {
    "start": {
        "action",
        "series",
        "branch",
        "version",
        "tag_version",
        "head",
        "summary",
    },
    "plan": {"series", "action", "tag_version", "pending", "stage", "previous"},
    "targets": {"branches", "versions"},
}


def load(name: str) -> dict[Any, Any]:
    """Load a workflow; PyYAML reads its `on:` key as True."""
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["release.yml", "backport.yml"])
def test_steps_read_only_outputs_that_release_py_writes(name: str) -> None:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    used = re.findall(r"steps\.(start|plan|targets)\.outputs\.(\w+)", text)
    assert used
    for step_id, key in used:
        assert key in OUTPUTS[step_id], (step_id, key)


def test_every_release_pr_step_passes_what_the_script_reads() -> None:
    workflow = load("release.yml")
    assert {"RELEASE_TOOLS", "VERSION_FILES"} <= set(workflow["env"])
    steps = [
        (job, step)
        for job, spec in workflow["jobs"].items()
        for step in spec["steps"]
        if "release-pr.sh" in step.get("run", "")
    ]
    assert sorted(job for job, _ in steps) == ["start", "update"]
    for _, step in steps:
        assert {"GH_TOKEN", "SERIES", "PENDING", "STAGE", "HEAD_SHA"} <= set(
            step["env"]
        )


def test_stage_input_defaults_to_release_candidates() -> None:
    stage = load("release.yml")[True]["workflow_call"]["inputs"]["stage"]
    assert (stage["type"], stage["default"]) == ("string", "rc")


def test_changelog_reaches_main_for_final_releases_only() -> None:
    condition = load("release.yml")["jobs"]["sync-changelog"]["if"]
    for suffix in ("'a'", "'b'", "'rc'"):
        assert f"!contains(github.ref_name, {suffix})" in condition


def step_script(workflow: str, job: str, name: str) -> str:
    """Return the run: script of the step NAME of JOB in WORKFLOW."""
    (step,) = [s for s in load(workflow)["jobs"][job]["steps"] if s.get("name") == name]
    return step["run"]


@pytest.mark.parametrize(
    ("versions", "ships"),
    [
        ("v1.1.1", "**v1.1.1**"),
        ("v1.2.0b3 v1.1.1", "**v1.2.0b3** and **v1.1.1**"),
    ],
)
def test_backport_suggestion(tmp_path: Path, versions: str, ships: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        f'#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "{tmp_path}/gh-args"\n',
        encoding="utf-8",
    )
    gh.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GH_TOKEN": "token",
        "GH_REPO": "Algorithmiq/demo",
        "NUMBER": "12",
        "VERSIONS": versions,
    }
    script = step_script("backport.yml", "suggest", "Suggest the backport label")
    subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert (tmp_path / "gh-args").read_text(encoding="utf-8").splitlines() == [
        "pr",
        "comment",
        "12",
        "--body",
        (
            f"This fix isn't in a release yet. To ship it in {ships}, add the "
            "`backport` label; it works after merging too."
        ),
    ]


def test_suggestion_is_only_for_fixes_merged_into_the_default_branch() -> None:
    condition = load("backport.yml")["jobs"]["suggest"]["if"]
    for part in (
        "github.event.action == 'closed'",
        "github.event.pull_request.merged == true",
        "github.event.pull_request.base.ref == github.event.repository.default_branch",
        "!contains(github.event.pull_request.labels.*.name, 'backport')",
        "!contains(github.event.pull_request.title, '!:')",
        "startsWith(github.event.pull_request.title, 'fix:')",
        "startsWith(github.event.pull_request.title, 'perf(')",
    ):
        assert part in condition


@pytest.mark.parametrize("workflow", ["release.yml", "backport.yml"])
def test_release_tools_checkout_is_excluded_from_git(
    workflow: str,
) -> None:
    """Every job that checks out .release-tools excludes it via .git/info/exclude."""
    jobs = load(workflow)["jobs"]
    for job_name, job_spec in jobs.items():
        steps = job_spec["steps"]
        has_release_tools_checkout = any(
            step.get("with", {}).get("path") == ".release-tools" for step in steps
        )
        if not has_release_tools_checkout:
            continue
        # Find the index of the checkout step.
        checkout_idx = next(
            i
            for i, s in enumerate(steps)
            if s.get("with", {}).get("path") == ".release-tools"
        )
        # The next step must be the exclude step.
        next_step = steps[checkout_idx + 1]
        assert "run" in next_step, (
            f"{workflow}::{job_name} checkout of .release-tools must be followed by "
            "the exclude step"
        )
        assert ".git/info/exclude" in next_step["run"], (
            f"{workflow}::{job_name} checkout of .release-tools must be followed by "
            "a step that adds it to .git/info/exclude"
        )

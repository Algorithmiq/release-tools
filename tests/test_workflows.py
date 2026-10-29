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

import re
from typing import Any

import pytest
import yaml
from conftest import ROOT

WORKFLOWS = ROOT / ".github" / "workflows"

# The outputs of the release.py commands, by the id of the step that runs them; the
# tests of release.py pin each command's outputs exactly.
OUTPUTS = {
    "start": {"action", "series", "branch", "version", "tag_version", "head", "summary"},
    "plan": {"series", "action", "tag_version", "pending", "stage", "previous"},
    "targets": {"branches", "versions"},
}


def load(name: str) -> dict[Any, Any]:
    """Load a workflow; PyYAML reads its `on:` key as True."""
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["release.yml"])  # backport.yml joins in Task 8
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

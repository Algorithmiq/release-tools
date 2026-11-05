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

"""Tests of the commands in docs/repository-setup.md that can run without GitHub.

Step 8 rewrites a live ruleset of `main` with jq before a PUT. It must add only what is
missing, so that running it again, or on a ruleset that already has the checks and the
bypass, sends the ruleset back unchanged.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any

import pytest
from conftest import ROOT

APP_ID = 1234567
CHECKS = ["PR checks / PR title", "PR checks / Migration notes"]

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None, reason="jq is not installed"
)


def step_8(ruleset: dict[str, Any]) -> dict[str, Any]:
    """Run step 8's jq program on RULESET, as `gh api …/rulesets/$id` returns it."""
    setup = (ROOT / "docs" / "repository-setup.md").read_text(encoding="utf-8")
    match = re.search(r"""jq --argjson app "\$APP_ID" '(.*?)' \\\n""", setup, re.DOTALL)
    assert match, "step 8's jq program"
    result = subprocess.run(
        ["jq", "--argjson", "app", str(APP_ID), match.group(1)],
        input=json.dumps(ruleset),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def as_put(ruleset: dict[str, Any]) -> dict[str, Any]:
    """Return the fields of RULESET that a PUT sends back."""
    keys = ("name", "target", "enforcement", "conditions", "rules", "bypass_actors")
    return {key: ruleset[key] for key in keys}


def required(ruleset: dict[str, Any]) -> list[str]:
    """Return the contexts that RULESET's required_status_checks rule requires."""
    (rule,) = [r for r in ruleset["rules"] if r["type"] == "required_status_checks"]
    return [check["context"] for check in rule["parameters"]["required_status_checks"]]


def ruleset(
    rules: list[dict[str, Any]], bypass: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return a ruleset of main, with fields that a GET returns and a PUT drops."""
    return {
        "id": 7,
        "name": "Protect main",
        "source_type": "Repository",
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": rules,
        "bypass_actors": bypass,
    }


def test_adds_the_checks_the_rule_and_the_bypass() -> None:
    result = step_8(ruleset([{"type": "deletion"}, {"type": "pull_request"}], []))
    assert required(result) == CHECKS
    assert result["bypass_actors"] == [
        {"actor_id": APP_ID, "actor_type": "Integration", "bypass_mode": "always"}
    ]
    assert "id" not in result


def test_keeps_the_existing_checks_first() -> None:
    lint = {"context": "lint", "integration_id": 15368}
    rule = {
        "type": "required_status_checks",
        "parameters": {"required_status_checks": [lint]},
    }
    assert required(step_8(ruleset([rule], []))) == ["lint", *CHECKS]


def test_a_second_run_changes_nothing() -> None:
    once = step_8(
        ruleset(
            [{"type": "pull_request"}],
            [{"actor_id": 2, "actor_type": "RepositoryRole"}],
        )
    )
    assert step_8(ruleset(once["rules"], once["bypass_actors"])) == as_put(once)

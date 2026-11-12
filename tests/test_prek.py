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

"""Tests of prek.toml: the linters run the versions locked in uv.lock."""

from __future__ import annotations

import re
import tomllib
from typing import Any

from conftest import ROOT


def hooks() -> list[dict[str, Any]]:
    """Return every hook of prek.toml, with its repository under "repo"."""
    with (ROOT / "prek.toml").open("rb") as f:
        repos = tomllib.load(f)["repos"]
    return [{**hook, "repo": repo["repo"]} for repo in repos for hook in repo["hooks"]]


def test_ruff_and_ty_run_the_locked_versions() -> None:
    # A rev of astral-sh/ruff-pre-commit or ty-pre-commit is a second pin that
    # Dependabot's uv ecosystem does not bump; the hooks must run the tools of uv.lock.
    by_id = {hook["id"]: hook for hook in hooks()}
    for hook_id, tool in (
        ("ruff-check", "ruff check"),
        ("ruff-format", "ruff format"),
        ("ty", "ty check"),
    ):
        hook = by_id[hook_id]
        assert hook["repo"] == "local", hook_id
        assert hook["language"] == "system", hook_id
        assert hook["entry"].startswith(f"uv run --no-sync {tool}"), hook_id


def test_no_repository_of_prek_toml_pins_a_tool_of_pyproject() -> None:
    with (ROOT / "pyproject.toml").open("rb") as f:
        dev = tomllib.load(f)["dependency-groups"]["dev"]
    tools = {re.split(r"[=<>~!\s]", requirement)[0] for requirement in dev}
    for hook in hooks():
        repo = str(hook["repo"])
        if repo != "local":
            name = repo.rsplit("/", 1)[-1]
            assert name.removesuffix("-pre-commit") not in tools, repo


def test_shellcheck_has_the_same_pin_in_the_actionlint_hook_and_pyproject() -> None:
    # The hook installs its own environment, so shellcheck-py is pinned twice.
    with (ROOT / "pyproject.toml").open("rb") as f:
        dev = tomllib.load(f)["dependency-groups"]["dev"]
    actionlint = next(hook for hook in hooks() if hook["id"] == "actionlint")
    assert [r for r in dev if r.startswith("shellcheck-py")] == (
        actionlint["additional_dependencies"]
    )

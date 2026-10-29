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

"""Tests that the stubs in examples/, README.md and the dogfooding workflows agree.

The consumer stubs in examples/stubs are the source: README.md shows them verbatim,
and .github/workflows/self-*.yml are the same files calling the local reusable
workflows.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import ROOT

STUBS = ROOT / "examples" / "stubs"
WORKFLOWS = ROOT / ".github" / "workflows"
REUSABLE = ("release", "backport", "pr-checks")
RELEASE_TOOLS_REF = re.compile(r"Algorithmiq/release-tools/([\w./-]+)@([\w.-]+)")
GIT_CLIFF_PIN = re.compile(r"git-cliff==([\d.]+)")


def load(path: Path) -> dict[Any, Any]:
    """Load a workflow; PyYAML reads its `on:` key as True."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def text_files() -> list[Path]:
    """Return every file tracked or to be tracked here, except lock and cache files."""
    skip = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__"}
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and not skip.intersection(path.relative_to(ROOT).parts)
        and path.name not in {"uv.lock", "LICENSE"}
    ]


@pytest.mark.parametrize("name", REUSABLE)
def test_dogfooding_stub_is_the_consumer_stub(name: str) -> None:
    stub = (STUBS / f"{name}.yml").read_text(encoding="utf-8")
    pinned = f"uses: Algorithmiq/release-tools/.github/workflows/{name}.yml@v1.2.0"
    assert pinned in stub
    local = stub.replace(pinned, f"uses: ./.github/workflows/{name}.yml")
    assert (WORKFLOWS / f"self-{name}.yml").read_text(encoding="utf-8") == local


@pytest.mark.parametrize(
    "name",
    [
        "release.yml",
        "backport.yml",
        "pr-checks.yml",
        "deploy.yml",
        "justfile",
        "justfile-internal",
    ],
)
def test_readme_shows_the_stub(name: str) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    stub = (STUBS / name).read_text(encoding="utf-8")
    assert (
        f"```{'just' if name.startswith('justfile') else 'yaml'}\n{stub}```" in readme
    )


@pytest.mark.parametrize("name", REUSABLE)
def test_stub_passes_what_the_reusable_workflow_declares(name: str) -> None:
    called = load(WORKFLOWS / f"{name}.yml")[True]["workflow_call"] or {}
    (job,) = load(STUBS / f"{name}.yml")["jobs"].values()
    declared_inputs = called.get("inputs") or {}
    declared_secrets = called.get("secrets") or {}
    passed_inputs = set(job.get("with") or {})
    passed_secrets = set(job.get("secrets") or {})
    assert passed_inputs <= set(declared_inputs)
    assert passed_secrets <= set(declared_secrets)
    for key, spec in declared_inputs.items():
        assert key in passed_inputs or not spec.get("required"), key
    for key, spec in declared_secrets.items():
        assert key in passed_secrets or not spec.get("required"), key


@pytest.mark.parametrize("name", REUSABLE)
def test_reusable_workflow_has_no_other_trigger(name: str) -> None:
    assert list(load(WORKFLOWS / f"{name}.yml")[True]) == ["workflow_call"]


def test_every_reference_uses_one_release_tools_tag() -> None:
    refs = {
        (path.relative_to(ROOT), target, ref)
        for path in text_files()
        for target, ref in RELEASE_TOOLS_REF.findall(path.read_text(encoding="utf-8"))
    }
    assert refs
    assert {ref for _, _, ref in refs} == {"v1.2.0"}
    for path, target, _ in refs:
        assert (ROOT / target).exists() or (ROOT / target / "action.yml").exists(), (
            path,
            target,
        )


def test_every_git_cliff_pin_is_the_same() -> None:
    pins = {
        path.relative_to(ROOT): set(GIT_CLIFF_PIN.findall(path.read_text("utf-8")))
        for path in text_files()
    }
    pins = {path: versions for path, versions in pins.items() if versions}
    expected = {
        Path("pyproject.toml"),
        Path(".github/workflows/release.yml"),
        Path("actions/release-notes/action.yml"),
        Path("examples/stubs/justfile"),
        Path("examples/stubs/justfile-internal"),
        Path("README.md"),
        Path("tests/test_actions.py"),
    }
    assert expected <= set(pins)
    assert set().union(*pins.values()) == {"2.14.2"}


@pytest.mark.skipif(shutil.which("just") is None, reason="just is not installed")
@pytest.mark.parametrize("name", ["justfile", "justfile-internal"])
def test_justfile_recipes_parse(name: str) -> None:
    result = subprocess.run(
        ["just", "--justfile", str(STUBS / name), "--summary"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.split() == ["changelog"]


def test_changelog_recipe_finds_the_pinned_tag(tmp_path: Path) -> None:
    # The sed expression of the recipe, run on the release stub.
    recipe = (STUBS / "justfile").read_text(encoding="utf-8")
    (expression,) = re.findall(r"sed -nE '([^']+)'", recipe)
    result = subprocess.run(
        ["sed", "-nE", expression, str(STUBS / "release.yml")],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )
    assert result.stdout == "v1.2.0\n"


def test_release_stub_offers_every_stage() -> None:
    inputs = load(STUBS / "release.yml")[True]["workflow_dispatch"]["inputs"]
    assert inputs["stage"]["options"] == ["rc", "beta", "alpha"]
    assert inputs["stage"]["default"] == "rc"
    assert "backport label" in inputs["bump"]["description"]

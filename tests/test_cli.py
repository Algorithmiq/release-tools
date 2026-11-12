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

"""Tests of the entry points and the help of the release package."""

from __future__ import annotations

import ast
import runpy
import subprocess
import sys

import pytest
from conftest import ROOT

COMMANDS = [
    "start",
    "plan",
    "backport-targets",
    "tag",
    "set-version",
    "sync-changelog",
    "changelog-section",
    "develop",
    "tag-development",
    "release-pr",
]


@pytest.mark.parametrize(
    "argv",
    [[str(ROOT / "release")], ["-m", "release"]],
    ids=["path", "module"],
)
def test_entry_points_print_the_help(argv: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, *argv, "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("usage: release ")
    for command in COMMANDS:
        assert command in result.stdout
    assert "VERSION_FILES" in result.stdout


@pytest.mark.parametrize("command", COMMANDS)
def test_every_command_has_help(command: str) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "release"), command, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(f"usage: release {command}")


def test_entry_point_refuses_an_older_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "version_info", (3, 11, 9, "final", 0))
    monkeypatch.setattr(sys, "version", "3.11.9 (main) [Clang]")
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(ROOT / "release" / "__main__.py"), run_name="__main__")
    assert exit_info.value.code == (
        "::error::release-tools needs Python 3.12 or later, not 3.11.9"
        f" ({sys.executable})."
    )


def test_entry_point_parses_with_older_pythons() -> None:
    # An older Python must reach the version check, so __main__.py can't use newer
    # syntax. 3.7 is the oldest that `from __future__ import annotations` allows.
    source = (ROOT / "release" / "__main__.py").read_text(encoding="utf-8")
    ast.parse(source, feature_version=(3, 7))

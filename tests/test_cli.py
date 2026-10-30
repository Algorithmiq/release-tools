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

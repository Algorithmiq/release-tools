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

"""Tests of release/git.py: the one helper that runs git, git cliff and gh."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from release.git import git, run

if TYPE_CHECKING:
    from conftest import Repo


def test_git_strips_its_output_and_run_keeps_it(repo: Repo) -> None:
    repo.commit("chore: start")
    assert git("log", "-1", "--format=%s") == "chore: start"
    assert run("git", "log", "-1", "--format=%s") == "chore: start\n"
    assert run("git", "log", "-1", "--format=%s", strip=True) == "chore: start"


def test_run_lets_the_error_reach_the_log(
    repo: Repo, capfd: pytest.CaptureFixture[str]
) -> None:
    repo.commit("chore: start")
    with pytest.raises(subprocess.CalledProcessError) as error:
        git("show", "HEAD:missing.txt")
    assert error.value.stderr is None
    assert "missing.txt" in capfd.readouterr().err


def test_quiet_keeps_the_error_out_of_the_log(
    repo: Repo, capfd: pytest.CaptureFixture[str]
) -> None:
    repo.commit("chore: start")
    with pytest.raises(subprocess.CalledProcessError) as error:
        git("show", "HEAD:missing.txt", quiet=True)
    assert "missing.txt" in error.value.stderr
    assert capfd.readouterr().err == ""

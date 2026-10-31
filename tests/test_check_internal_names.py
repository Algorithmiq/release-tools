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

"""Tests of scripts/check_internal_names.py, run with a stand-in for gh."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest
from conftest import ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import Repo

SCRIPT = ROOT / "scripts" / "check_internal_names.py"
REPOSITORIES = [
    {"name": "secret-solver", "visibility": "PRIVATE"},
    {"name": "lab", "visibility": "INTERNAL"},
    {"name": "release-tools", "visibility": "PUBLIC"},
]


def fake_gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    """Put a gh on PATH that runs SCRIPT (POSIX shell)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


@pytest.fixture
def gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A gh that lists REPOSITORIES."""
    listing = tmp_path / "repositories.json"
    listing.write_text(json.dumps(REPOSITORIES), encoding="utf-8")
    fake_gh(tmp_path, monkeypatch, f'cat "{listing}"')


def check(repo: Repo, base: str) -> subprocess.CompletedProcess[str]:
    """Run the check on the push of BASE..HEAD, the way prek runs it."""
    env = {**os.environ, "PRE_COMMIT_FROM_REF": base, "PRE_COMMIT_TO_REF": "HEAD"}
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo.path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.usefixtures("gh")
def test_an_added_line_naming_a_private_repository_is_refused(repo: Repo) -> None:
    base = repo.commit("chore: start")
    repo.commit("docs: notes", {"notes.md": "First adopted by secret-solver.\n"})
    result = check(repo, base)
    assert result.returncode == 1
    assert "notes.md: secret-solver" in result.stderr


@pytest.mark.usefixtures("gh")
def test_a_commit_message_naming_an_internal_repository_is_refused(repo: Repo) -> None:
    base = repo.commit("chore: start")
    repo.commit("fix: 🐛 the bug LAB found (#1)")
    result = check(repo, base)
    assert result.returncode == 1
    assert ": LAB" in result.stderr
    assert "commit " in result.stderr


@pytest.mark.usefixtures("gh")
def test_only_what_the_push_adds_is_checked(repo: Repo) -> None:
    base = repo.commit("chore: start", {"notes.md": "secret-solver\n"})
    repo.commit("docs: more notes", {"other.md": "Nothing to see.\n"})
    assert check(repo, base).returncode == 0


@pytest.mark.usefixtures("gh")
def test_names_match_as_whole_words_only(repo: Repo) -> None:
    base = repo.commit("chore: start")
    repo.commit(
        "docs: notes",
        {"notes.md": "A collaborator in a lab-coat, and release-tools.\n"},
    )
    assert check(repo, base).returncode == 0


@pytest.mark.usefixtures("gh")
def test_locally_allowed_names_pass(repo: Repo) -> None:
    (repo.path / ".git" / "info" / "allowed-names").write_text(
        "lab\n", encoding="utf-8"
    )
    base = repo.commit("chore: start")
    repo.commit("docs: notes", {"notes.md": "Back to the lab.\n"})
    assert check(repo, base).returncode == 0


def test_without_access_to_the_organisation_the_check_is_skipped(
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_gh(tmp_path, monkeypatch, "echo 'not logged in' >&2; exit 1")
    base = repo.commit("chore: start")
    repo.commit("docs: notes", {"notes.md": "secret-solver\n"})
    result = check(repo, base)
    assert result.returncode == 0
    assert "skipped" in result.stderr

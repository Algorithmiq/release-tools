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

"""Tests of the composite actions in actions/.

actionlint only checks workflows, so the run: scripts of the actions are checked with
shellcheck here, and run in bash as the runner runs them, with stand-ins for pipx
(running the git-cliff of the dev dependencies) and gh (recording its arguments).
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from typing import TYPE_CHECKING

import pytest
import yaml
from conftest import ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import Repo

ACTIONS = sorted((ROOT / "actions").glob("*/action.yml"))


def script(action: str) -> str:
    """Return the run: script of ACTION, which has exactly one step."""
    metadata = yaml.safe_load((ROOT / "actions" / action / "action.yml").read_text())
    (step,) = metadata["runs"]["steps"]
    assert step["shell"] == "bash"
    return step["run"]


@pytest.fixture
def bin_dir(tmp_path: Path) -> Path:
    """Return a directory, first on PATH, with stand-ins for pipx and gh."""
    directory = tmp_path / "bin"
    directory.mkdir()
    git_cliff = shutil.which("git-cliff")
    assert git_cliff
    stand_ins = {
        # pipx run --spec git-cliff==X git-cliff ARGS...
        "pipx": f'echo "$@" > "{tmp_path}/pipx-args"\nshift 4\nexec "{git_cliff}" "$@"',
        "gh": f'printf "%s\\n" "$@" > "{tmp_path}/gh-args"',
    }
    for name, body in stand_ins.items():
        path = directory / name
        path.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return directory


def run_action(
    action: str, env: dict[str, str], bin_dir: Path, tmp_path: Path
) -> subprocess.CompletedProcess[str]:
    """Run the script of ACTION in the current directory with ENV, like the runner."""
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir(exist_ok=True)
    full_env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": str(runner_temp),
        "GITHUB_OUTPUT": str(tmp_path / "github-output"),
        **env,
    }
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script(action)],
        env=full_env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("path", ACTIONS, ids=lambda path: path.parent.name)
def test_action_scripts_pass_shellcheck(path: Path) -> None:
    run = script(path.parent.name)
    # Inputs reach the scripts through env:, never through ${{ }} in the script itself.
    assert "${{" not in run
    result = subprocess.run(
        ["shellcheck", "--shell=bash", "-"],
        input=run,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout


@pytest.fixture
def released(repo: Repo) -> Repo:
    """Return a repository with the final release v0.1.0 and a candidate v0.2.0rc1."""
    repo.commit("chore: start")
    repo.git("tag", "-a", "v0.0.0", "-m", "start")
    repo.commit("feat: ✨ first feature (#1)")
    repo.git("tag", "-a", "v0.1.0", "-m", "Release 0.1.0")
    repo.commit("fix: 🐛 a fix (#2)")
    repo.git("tag", "-a", "v0.2.0rc1", "-m", "Release 0.2.0rc1")
    return repo


def notes_env(tag: str) -> dict[str, str]:
    """Return the env: of the release-notes step for the input TAG."""
    return {
        "TAG": tag,
        "NOTES": "",
        "CLIFF_CONFIG": str(ROOT / "actions/release-notes/../../cliff.toml"),
        "GITHUB_REF_NAME": "v0.1.0",
    }


def test_release_notes_of_a_final_release(
    released: Repo, bin_dir: Path, tmp_path: Path
) -> None:
    released.git("checkout", "--quiet", "v0.1.0")
    result = run_action("release-notes", notes_env(""), bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    notes = tmp_path / "runner-temp/release-notes.md"
    assert (tmp_path / "github-output").read_text() == f"path={notes}\n"
    text = notes.read_text()
    assert text.lstrip().startswith("## 0.1.0 (")
    assert "- First feature (#1)" in text
    assert "A fix" not in text
    assert (
        (tmp_path / "pipx-args")
        .read_text()
        .startswith("run --spec git-cliff==2.14.2 git-cliff --config ")
    )


def test_release_notes_of_a_release_candidate(
    released: Repo, bin_dir: Path, tmp_path: Path
) -> None:
    released.git("checkout", "--quiet", "v0.2.0rc1")
    env = notes_env("v0.2.0rc1") | {"NOTES": str(tmp_path / "rc.md")}
    result = run_action("release-notes", env, bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    text = (tmp_path / "rc.md").read_text()
    assert text.lstrip().startswith("## 0.2.0rc1 (")
    assert "- A fix (#2)" in text
    assert "First feature" not in text


def test_release_notes_need_the_tag_checked_out(
    released: Repo, bin_dir: Path, tmp_path: Path
) -> None:
    released.git("checkout", "--quiet", "v0.2.0rc1")
    result = run_action("release-notes", notes_env("v0.1.0"), bin_dir, tmp_path)
    assert result.returncode == 1
    assert "::error::Check out v0.1.0 first" in result.stdout


@pytest.mark.parametrize("stage", ["a", "b"])
def test_release_notes_of_an_alpha_or_beta(
    released: Repo, bin_dir: Path, tmp_path: Path, stage: str
) -> None:
    tag = f"v0.2.0{stage}1"
    released.git("checkout", "--quiet", "v0.2.0rc1")
    released.git("tag", "-a", tag, "-m", f"Release {tag[1:]}")
    env = notes_env(tag) | {"NOTES": str(tmp_path / "pre.md")}
    result = run_action("release-notes", env, bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    text = (tmp_path / "pre.md").read_text()
    assert text.lstrip().startswith(f"## 0.2.0{stage}1 (")
    assert "- A fix (#2)" in text


@pytest.mark.usefixtures("released")
def test_release_notes_refuse_pre_releases_of_patches(
    bin_dir: Path, tmp_path: Path
) -> None:
    result = run_action("release-notes", notes_env("v0.1.1rc1"), bin_dir, tmp_path)
    assert result.returncode == 1
    assert "::error::'v0.1.1rc1' is not a release tag" in result.stdout


@pytest.mark.usefixtures("released")
def test_release_notes_refuse_other_refs(bin_dir: Path, tmp_path: Path) -> None:
    result = run_action("release-notes", notes_env("main"), bin_dir, tmp_path)
    assert result.returncode == 1
    assert (
        "::error::'main' is not a release tag (vX.Y.Z, or vX.Y.0aN, bN or rcN)."
        in result.stdout
    )


def draft_env(tag: str, files: str) -> dict[str, str]:
    """Return the env: of the draft-release step."""
    return {
        "GH_TOKEN": "token",
        "GH_REPO": "Algorithmiq/demo",
        "TAG": tag,
        "NOTES": "notes.md",
        "PATTERNS": files,
        "GITHUB_REF_NAME": "v1.2.0rc3",
    }


@pytest.mark.parametrize("tag", ["v1.2.0a1", "v1.2.0b2", "v1.2.0rc3"])
def test_draft_release_marks_pre_releases(
    tmp_path: Path, bin_dir: Path, monkeypatch: pytest.MonkeyPatch, tag: str
) -> None:
    monkeypatch.chdir(tmp_path)
    result = run_action("draft-release", draft_env(tag, ""), bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "gh-args").read_text().splitlines()[-1] == "--prerelease"


@pytest.mark.parametrize("tag", ["v1.2.1rc1", "v1.2", "main"])
def test_draft_release_refuses_other_tags(
    tmp_path: Path, bin_dir: Path, monkeypatch: pytest.MonkeyPatch, tag: str
) -> None:
    monkeypatch.chdir(tmp_path)
    result = run_action("draft-release", draft_env(tag, ""), bin_dir, tmp_path)
    assert result.returncode == 1
    assert f"::error::'{tag}' is not a release tag" in result.stdout
    assert not (tmp_path / "gh-args").exists()


def test_draft_release_of_a_candidate_with_files(
    tmp_path: Path, bin_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("dist/a.whl", "dist/a.tar.gz", "sbom/a.cdx.json"):
        (tmp_path / name).parent.mkdir(exist_ok=True)
        (tmp_path / name).touch()
    files = "  dist/*\n\nsbom/*.json\n"
    result = run_action("draft-release", draft_env("", files), bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "gh-args").read_text().splitlines() == [
        "release",
        "create",
        "v1.2.0rc3",
        "dist/a.tar.gz",
        "dist/a.whl",
        "sbom/a.cdx.json",
        "--draft",
        "--verify-tag",
        "--title",
        "v1.2.0rc3",
        "--notes-file",
        "notes.md",
        "--prerelease",
    ]


def test_draft_release_of_a_final_release_without_files(
    tmp_path: Path, bin_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = run_action("draft-release", draft_env("v1.2.0", ""), bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "gh-args").read_text().splitlines() == [
        "release",
        "create",
        "v1.2.0",
        "--draft",
        "--verify-tag",
        "--title",
        "v1.2.0",
        "--notes-file",
        "notes.md",
    ]


def test_draft_release_of_a_candidate_without_files_explicit(
    tmp_path: Path, bin_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = run_action("draft-release", draft_env("v1.2.0rc3", ""), bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "gh-args").read_text().splitlines() == [
        "release",
        "create",
        "v1.2.0rc3",
        "--draft",
        "--verify-tag",
        "--title",
        "v1.2.0rc3",
        "--notes-file",
        "notes.md",
        "--prerelease",
    ]


def test_draft_release_refuses_a_glob_without_files(
    tmp_path: Path, bin_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = run_action(
        "draft-release", draft_env("v1.2.0", "dist/*"), bin_dir, tmp_path
    )
    assert result.returncode == 1
    assert "::error::No files match 'dist/*'." in result.stdout
    assert not (tmp_path / "gh-args").exists()


def test_publish_release(tmp_path: Path, bin_dir: Path) -> None:
    env = {
        "GH_TOKEN": "token",
        "GH_REPO": "x/y",
        "TAG": "",
        "GITHUB_REF_NAME": "v2.0.0",
    }
    result = run_action("publish-release", env, bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "gh-args").read_text().splitlines() == [
        "release",
        "edit",
        "v2.0.0",
        "--draft=false",
    ]

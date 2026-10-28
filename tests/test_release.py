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

"""Tests of the commands of release.py, run in-process against a scratch repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import release

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import Repo

PYPROJECT = """\
[build-system]
requires = ["hatchling"]
version = "build-system-is-not-the-project"

[project]
name = "demo"
description = "version = \\"0.0.0\\" in a string is not the version"
version = "0.0.0"
dependencies = []

[tool.other]
version = "9.9.9"
"""


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> dict[str, str]:
    """Run release.py with ARGV and return the key=value outputs it printed."""
    release.main(list(argv))
    lines = capsys.readouterr().out.splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line)


def fails(capsys: pytest.CaptureFixture[str], *argv: str) -> str:
    """Run release.py with ARGV, check it exits with status 1, return the error."""
    with pytest.raises(SystemExit) as exit_info:
        release.main(list(argv))
    assert exit_info.value.code == 1
    return capsys.readouterr().out


def tag(repo: Repo, *names: str) -> None:
    """Create lightweight tags NAMES on HEAD."""
    for name in names:
        repo.git("tag", name)


def on_release_branch(repo: Repo, series: str) -> None:
    """Check out release/SERIES from HEAD."""
    repo.git("checkout", "--quiet", "-b", f"release/{series}")


# start


def test_start_without_tags_opens_release_0_1(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    assert run(capsys, "start") == {"branch": "release/0.1", "version": "0.1.0"}


def test_start_follows_the_newest_final_tag(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    # Release candidates and later series' candidates don't count as releases.
    tag(repo, "v0.0.0", "v0.4.0", "v0.4.2", "v0.10.0rc1", "v0.3.9")
    assert run(capsys, "start", "--bump", "minor") == {
        "branch": "release/0.5",
        "version": "0.5.0",
    }


def test_start_major_bump(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.4.2")
    assert run(capsys, "start", "--bump", "major") == {
        "branch": "release/1.0",
        "version": "1.0.0",
    }


def test_start_major_bump_from_a_major_release(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v1.3.0")
    assert run(capsys, "start", "--bump", "major")["branch"] == "release/2.0"
    assert run(capsys, "start")["branch"] == "release/1.4"


def test_start_refuses_a_release_in_progress(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.4.2")
    repo.git("push", "--quiet", "origin", "HEAD:refs/heads/release/0.5")
    message = fails(capsys, "start")
    assert "::error::release/0.5 already exists" in message


def test_start_appends_to_github_output(
    repo: Repo,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.write_text("earlier=value\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    repo.commit("feat: first")
    run(capsys, "start")
    assert outputs.read_text(encoding="utf-8") == (
        "earlier=value\nbranch=release/0.1\nversion=0.1.0\n"
    )


# plan


def test_plan_tags_the_first_release_candidate(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.4.2")
    on_release_branch(repo, "0.5")
    assert run(capsys, "plan") == {
        "series": "0.5",
        "action": "rc",
        "tag_version": "0.5.0rc1",
        "pending": "0.5.0",
    }


def test_plan_numbers_release_candidates_within_the_series(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    # Candidates of other series, and of 0.5.0 lookalikes, don't count.
    tag(repo, "v0.5.0rc1", "v0.5.0rc2", "v0.4.0rc9", "v0.50.0rc7", "v1.5.0rc5")
    on_release_branch(repo, "0.5")
    outputs = run(capsys, "plan")
    assert outputs["action"] == "rc"
    assert outputs["tag_version"] == "0.5.0rc3"


def test_plan_numbers_release_candidates_numerically(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, *(f"v0.5.0rc{n}" for n in range(1, 11)))
    on_release_branch(repo, "0.5")
    assert run(capsys, "plan")["tag_version"] == "0.5.0rc11"


def test_plan_reads_the_branch_from_github_ref_name(
    repo: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Actions checks out the pushed commit detached; GITHUB_REF_NAME names the branch.
    repo.commit("feat: first")
    repo.git("checkout", "--quiet", "--detach")
    monkeypatch.setenv("GITHUB_REF_NAME", "release/2.3")
    assert run(capsys, "plan")["tag_version"] == "2.3.0rc1"


def test_plan_refuses_other_branches(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    assert "'main' is not a release branch" in fails(capsys, "plan")


def test_plan_tags_the_final_release_when_the_release_pr_is_merged(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.4.2", "v0.5.0rc1", "v0.5.0rc2")
    on_release_branch(repo, "0.5")
    repo.commit("chore: release v0.5.0 (#42)")
    assert run(capsys, "plan") == {
        "series": "0.5",
        "action": "final",
        "tag_version": "0.5.0",
        "pending": "0.5.0",
    }


def test_plan_accepts_a_release_commit_without_pr_number(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    on_release_branch(repo, "0.5")
    repo.commit("chore: release v0.5.0")
    assert run(capsys, "plan")["action"] == "final"


def test_plan_checks_the_version_of_the_release_pr(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.5.0")
    on_release_branch(repo, "0.5")
    repo.commit("chore: release v0.5.3 (#44)")
    message = fails(capsys, "plan")
    assert "Release PR says v0.5.3, but the next version is v0.5.1." in message


def test_plan_after_x_y_0_only_updates_the_patch_release_pr(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.5.0rc1", "v0.5.0", "v0.5.1", "v0.6.0rc1")
    on_release_branch(repo, "0.5")
    repo.commit("fix: backported (#50)")
    assert run(capsys, "plan") == {
        "series": "0.5",
        "action": "pr",
        "tag_version": "",
        "pending": "0.5.2",
    }


def test_plan_tags_a_patch_release(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.5.0", "v0.5.1")
    on_release_branch(repo, "0.5")
    repo.commit("chore: release v0.5.2 (#51)")
    outputs = run(capsys, "plan")
    assert (outputs["action"], outputs["tag_version"]) == ("final", "0.5.2")


# tag


def test_tag_without_version_files_tags_head(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    head = repo.commit("feat: first")
    assert run(capsys, "tag", "0.1.0rc1") == {"tag": "v0.1.0rc1"}
    assert repo.git("cat-file", "-t", "v0.1.0rc1") == "tag"  # annotated
    assert repo.git("rev-parse", "v0.1.0rc1^{commit}") == head
    assert repo.git("tag", "-l", "--format=%(contents:subject)", "v0.1.0rc1") == (
        "Release 0.1.0rc1"
    )
    assert repo.remote_tags() == ["v0.1.0rc1"]


def test_tag_release_candidate_records_the_version_off_the_branch(
    repo: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERSION_FILES", "VERSION pyproject.toml")
    head = repo.commit(
        "feat: first", {"VERSION": "0.0.0\n", "pyproject.toml": PYPROJECT}
    )
    on_release_branch(repo, "0.1")
    repo.git("push", "--quiet", "origin", "release/0.1")

    run(capsys, "tag", "0.1.0rc1")

    tagged = repo.git("rev-parse", "v0.1.0rc1^{commit}")
    assert tagged != head
    assert repo.git("rev-parse", f"{tagged}^") == head
    assert repo.git("log", "-1", "--format=%s", tagged) == "chore: set version 0.1.0rc1"
    assert repo.git("show", f"{tagged}:VERSION") == "0.1.0rc1"
    assert 'version = "0.1.0rc1"' in repo.git("show", f"{tagged}:pyproject.toml")
    # Neither the local nor the remote release branch moved.
    assert repo.git("rev-parse", "release/0.1") == head
    assert repo.git("ls-remote", "origin", "refs/heads/release/0.1").split()[0] == head
    assert repo.remote_tags() == ["v0.1.0rc1"]


def test_tag_final_release_tags_the_merged_release_pr(
    repo: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERSION_FILES", "VERSION")
    on_release_branch(repo, "0.1")
    head = repo.commit("chore: release v0.1.0 (#3)", {"VERSION": "0.1.0\n"})
    run(capsys, "tag", "0.1.0", "--final")
    assert repo.git("rev-parse", "v0.1.0^{commit}") == head
    assert repo.remote_tags() == ["v0.1.0"]


def test_tag_final_release_refuses_mismatched_version_files(
    repo: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERSION_FILES", "VERSION")
    on_release_branch(repo, "0.1")
    repo.commit("chore: release v0.1.0 (#3)", {"VERSION": "0.0.9\n"})
    message = fails(capsys, "tag", "0.1.0", "--final")
    assert "The version files don't say 0.1.0. Was the release PR edited?" in message
    assert repo.remote_tags() == []


def test_tag_refuses_an_existing_tag(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.1.0rc1")
    assert "Tag v0.1.0rc1 already exists." in fails(capsys, "tag", "0.1.0rc1")


# set-version


def test_set_version_updates_only_the_project_table(
    repo: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERSION_FILES", "pyproject.toml")
    (repo.path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    run(capsys, "set-version", "1.2.3")
    expected = PYPROJECT.replace('version = "0.0.0"\n', 'version = "1.2.3"\n')
    assert expected != PYPROJECT
    assert (repo.path / "pyproject.toml").read_text(encoding="utf-8") == expected


def test_set_version_overwrites_plain_files(
    repo: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERSION_FILES", "VERSION src/VERSION.txt")
    (repo.path / "src").mkdir()
    (repo.path / "VERSION").write_text("0.0.0\n", encoding="utf-8")
    run(capsys, "set-version", "0.2.0rc1")
    assert (repo.path / "VERSION").read_text(encoding="utf-8") == "0.2.0rc1\n"
    assert (repo.path / "src/VERSION.txt").read_text(encoding="utf-8") == "0.2.0rc1\n"


def test_set_version_refuses_a_toml_without_project_version(
    repo: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERSION_FILES", "pyproject.toml")
    (repo.path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndynamic = ["version"]\n\n[tool.x]\nversion = "1"\n',
        encoding="utf-8",
    )
    assert "No version in the [project] table of pyproject.toml" in fails(
        capsys, "set-version", "1.0.0"
    )


def test_set_version_without_version_files_does_nothing(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    run(capsys, "set-version", "1.0.0")
    assert repo.git("status", "--porcelain") == ""

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

import subprocess
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


# version model


def test_stage_of_a_series(repo: Repo) -> None:
    repo.commit("feat: first")
    assert release.stage_of((0, 5)) == "none"
    for name, stage in (
        ("v0.5.0a1", "alpha"),
        ("v0.5.0b1", "beta"),
        ("v0.5.0rc1", "rc"),
        ("v0.5.0", "released"),
    ):
        tag(repo, name)
        assert release.stage_of((0, 5)) == stage
    # Lookalikes of other series, and pre-releases of patch versions, don't count.
    tag(repo, "v0.50.0b1", "v0.6.1b1", "v0.6.1rc1")
    assert release.stage_of((0, 50)) == "beta"
    assert release.stage_of((0, 6)) == "none"


def test_next_prerelease_numbers_each_stage_numerically(repo: Repo) -> None:
    repo.commit("feat: first")
    tag(repo, *(f"v0.5.0b{n}" for n in range(1, 11)), "v0.5.0a3", "v1.5.0b20")
    assert release.next_prerelease((0, 5), "beta") == "0.5.0b11"
    assert release.next_prerelease((0, 5), "alpha") == "0.5.0a4"
    assert release.next_prerelease((0, 5), "rc") == "0.5.0rc1"


def test_release_branches_lists_the_series_on_origin(repo: Repo) -> None:
    repo.commit("feat: first")
    for branch in ("release/0.10", "release/0.9", "release/1.0", "release-pr/0.9"):
        repo.git("push", "--quiet", "origin", f"HEAD:refs/heads/{branch}")
    assert release.release_branches() == [(0, 9), (0, 10), (1, 0)]


def test_next_on_branch(repo: Repo) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.4.0", "v0.4.1", "v0.5.0b1", "v0.5.0b2", "v0.6.0a1")
    assert release.next_on_branch((0, 4)) == ("released", "0.4.2")
    assert release.next_on_branch((0, 5)) == ("beta", "0.5.0b3")
    # No beta or candidate yet (a branch cut by release-tools 1.1): candidates.
    assert release.next_on_branch((0, 6)) == ("rc", "0.6.0rc1")


# start


def test_start_without_tags_cuts_release_0_1_at_rc1(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    head = repo.commit("feat: first")
    assert run(capsys, "start") == {
        "action": "cut",
        "series": "0.1",
        "branch": "release/0.1",
        "version": "0.1.0",
        "tag_version": "0.1.0rc1",
        "head": head,
        "summary": "Started release/0.1 at v0.1.0rc1.",
    }
    assert repo.git("ls-remote", "origin", "refs/heads/release/0.1").split()[0] == head
    assert repo.remote_tags() == ["v0.1.0rc1"]


def test_start_follows_the_newest_final_tag(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    # Pre-releases and later series' candidates don't count as releases.
    tag(repo, "v0.0.0", "v0.4.0", "v0.4.2", "v0.10.0rc1", "v0.3.9")
    outputs = run(capsys, "start", "--bump", "minor")
    assert (outputs["branch"], outputs["tag_version"]) == ("release/0.5", "0.5.0rc1")


def test_start_major_bump(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.4.2")
    outputs = run(capsys, "start", "--bump", "major")
    assert (outputs["branch"], outputs["version"]) == ("release/1.0", "1.0.0")


def test_start_major_bump_from_a_major_release(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v1.3.0")
    assert run(capsys, "start", "--bump", "major")["branch"] == "release/2.0"


def test_start_minor_bump_from_a_major_release(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v1.3.0")
    assert run(capsys, "start")["branch"] == "release/1.4"


def test_start_alpha_tags_main_without_a_branch(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    head = repo.commit("feat: first")
    tag(repo, "v0.4.2")
    assert run(capsys, "start", "--stage", "alpha") == {
        "action": "alpha",
        "series": "0.5",
        "branch": "",
        "version": "0.5.0",
        "tag_version": "0.5.0a1",
        "head": head,
        "summary": "Tagged v0.5.0a1 on main.",
    }
    repo.commit("feat: second")
    assert run(capsys, "start", "--stage", "alpha")["tag_version"] == "0.5.0a2"
    assert repo.remote_tags() == ["v0.5.0a1", "v0.5.0a2"]
    assert release.release_branches() == []


def test_start_beta_cuts_the_branch_after_the_alphas(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.4.2", "v0.5.0a1", "v0.5.0a2")
    head = repo.commit("feat: second")
    outputs = run(capsys, "start", "--stage", "beta")
    assert (outputs["action"], outputs["branch"], outputs["tag_version"]) == (
        "cut",
        "release/0.5",
        "0.5.0b1",
    )
    assert repo.git("ls-remote", "origin", "refs/heads/release/0.5").split()[0] == head
    assert repo.remote_tags() == ["v0.5.0b1"]


def test_start_rc_promotes_a_release_in_beta(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.4.2")
    run(capsys, "start", "--stage", "beta")
    # A backport merged into the branch, and the beta the update job tagged for it.
    repo.git("fetch", "--quiet", "origin")
    repo.git("checkout", "--quiet", "-b", "release/0.5", "origin/release/0.5")
    head = repo.commit("fix: backported (#7)")
    repo.git("push", "--quiet", "origin", "release/0.5")
    tag(repo, "v0.5.0b2")
    repo.git("checkout", "--quiet", "main")

    assert run(capsys, "start", "--stage", "rc") == {
        "action": "promote",
        "series": "0.5",
        "branch": "release/0.5",
        "version": "0.5.0",
        "tag_version": "0.5.0rc1",
        "head": head,
        "summary": "Promoted release/0.5 to release candidates: v0.5.0rc1.",
    }
    assert repo.git("rev-parse", "v0.5.0rc1^{commit}") == head
    assert "v0.5.0rc1" in repo.remote_tags()


def test_promotion_without_new_commits_describes_as_the_candidate(
    repo: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # setuptools-scm uses `git describe`: with two tags on one commit, the newer wins.
    repo.commit("feat: first")
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-01-01T12:00:00")
    run(capsys, "start", "--stage", "beta")
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-01-02T12:00:00")
    run(capsys, "start", "--stage", "rc")
    commit = repo.git("rev-parse", "v0.1.0rc1^{commit}")
    assert repo.git("rev-parse", "v0.1.0b1^{commit}") == commit
    assert repo.git("describe", "--tags", commit) == "v0.1.0rc1"


_BETA_MSG = (
    "release/0.5 is already in beta: every backport merged into it tags the"
    " next beta. Run Release with stage rc to move it to release candidates."
)
_RC_MSG = (
    "release/0.5 is already at release candidates: merge its release PR to"
    " release v0.5.0."
)


@pytest.mark.parametrize(
    ("tags", "stage", "message"),
    [
        (
            ["v0.5.0b1"],
            "alpha",
            "release/0.5 exists: v0.5.0 is past its alphas. Run Release with stage rc to promote it.",
        ),
        (["v0.5.0b1"], "beta", _BETA_MSG),
        (["v0.5.0b1", "v0.5.0rc1"], "beta", _RC_MSG),
        (["v0.5.0rc1"], "rc", _RC_MSG),
        (
            [],
            "rc",
            "release/0.5 already exists: that release is already in progress. Merge its release PR to release v0.5.0.",
        ),
    ],
)
def test_start_refuses_to_go_backwards(
    repo: Repo,
    capsys: pytest.CaptureFixture[str],
    tags: list[str],
    stage: str,
    message: str,
) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.4.2", *tags)
    repo.git("push", "--quiet", "origin", "HEAD:refs/heads/release/0.5")
    assert f"::error::{message}" in fails(capsys, "start", "--stage", stage)
    assert repo.remote_tags() == []


def test_start_refuses_a_second_release_in_progress(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.4.2", "v0.5.0rc1")
    repo.git("push", "--quiet", "origin", "HEAD:refs/heads/release/0.5")
    message = fails(capsys, "start", "--bump", "major", "--stage", "beta")
    error_msg = (
        "::error::release/0.5 has no final release yet: release it, or delete the"
        " branch, before starting release/1.0."
    )
    assert error_msg in message
    # Alphas don't create a branch, so they may start meanwhile.
    outputs = run(capsys, "start", "--bump", "major", "--stage", "alpha")
    assert outputs["tag_version"] == "1.0.0a1"


def test_start_appends_to_github_output(
    repo: Repo,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.write_text("earlier=value\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    head = repo.commit("feat: first")
    run(capsys, "start")
    assert outputs.read_text(encoding="utf-8") == (
        "earlier=value\naction=cut\nseries=0.1\nbranch=release/0.1\nversion=0.1.0\n"
        f"tag_version=0.1.0rc1\nhead={head}\n"
        "summary=Started release/0.1 at v0.1.0rc1.\n"
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
        "action": "prerelease",
        "tag_version": "0.5.0rc1",
        "pending": "0.5.0",
        "stage": "rc",
        "previous": "",
    }


def test_plan_numbers_release_candidates_within_the_series(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    # Candidates of other series, and of 0.5.0 lookalikes, don't count.
    tag(repo, "v0.5.0rc1", "v0.5.0rc2", "v0.4.0rc9", "v0.50.0rc7", "v1.5.0rc5")
    on_release_branch(repo, "0.5")
    repo.commit("fix: backported (#7)")
    outputs = run(capsys, "plan")
    assert outputs["action"] == "prerelease"
    assert outputs["tag_version"] == "0.5.0rc3"


def test_plan_numbers_release_candidates_numerically(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, *(f"v0.5.0rc{n}" for n in range(1, 11)))
    on_release_branch(repo, "0.5")
    repo.commit("fix: backported (#7)")
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
        "stage": "released",
        "previous": "",
    }


def test_plan_accepts_a_release_commit_without_pr_number(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.5.0rc1")
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
        "stage": "released",
        "previous": "",
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


def test_plan_tags_the_next_beta(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.5.0b1")
    on_release_branch(repo, "0.5")
    repo.commit("fix: backported (#7)")
    outputs = run(capsys, "plan")
    assert (outputs["action"], outputs["tag_version"], outputs["stage"]) == (
        "prerelease",
        "0.5.0b2",
        "beta",
    )


def test_plan_only_updates_the_pr_when_start_tagged_head(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    # `start` tags the first beta when it cuts the branch: the push of the branch
    # only opens the release PR.
    repo.commit("feat: first")
    tag(repo, "v0.5.0b1")
    on_release_branch(repo, "0.5")
    assert run(capsys, "plan") == {
        "series": "0.5",
        "action": "pr",
        "tag_version": "",
        "pending": "0.5.0",
        "stage": "beta",
        "previous": "",
    }


def test_plan_sees_the_tag_of_start_on_a_version_commit(
    repo: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERSION_FILES", "VERSION")
    repo.commit("feat: first", {"VERSION": "0.0.0\n"})
    on_release_branch(repo, "0.5")
    release.create_tag("0.5.0rc1")  # on a commit on top of HEAD that sets VERSION
    repo.git("checkout", "--quiet", "release/0.5")
    capsys.readouterr()
    outputs = run(capsys, "plan")
    assert (outputs["action"], outputs["stage"]) == ("pr", "rc")


def test_plan_ignores_alpha_tags_on_head(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.5.0a2")
    on_release_branch(repo, "0.5")
    outputs = run(capsys, "plan")
    assert (outputs["action"], outputs["tag_version"]) == ("prerelease", "0.5.0rc1")


def test_plan_refuses_a_final_without_a_release_candidate(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    tag(repo, "v0.5.0b1", "v0.5.0b2")
    on_release_branch(repo, "0.5")
    repo.commit("chore: release v0.5.0 (#9)")
    message = fails(capsys, "plan")
    assert (
        "::error::v0.5.0 has no release candidate: run Release with stage rc first."
        in message
    )


def test_plan_names_the_previous_line_on_an_x_y_0_final(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    for branch in ("release/0.3", "release/0.4"):
        repo.git("push", "--quiet", "origin", f"HEAD:refs/heads/{branch}")
    tag(repo, "v0.3.0", "v0.4.0", "v0.4.1", "v0.5.0rc1")
    on_release_branch(repo, "0.5")
    repo.commit("chore: release v0.5.0 (#9)")
    assert run(capsys, "plan")["previous"] == "0.4"
    # Patch releases don't end the support of anything.
    tag(repo, "v0.5.0")
    repo.commit("chore: release v0.5.1 (#10)")
    assert run(capsys, "plan")["previous"] == ""


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


def test_tag_with_a_branch_pushes_both(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VERSION_FILES", "VERSION")
    head = repo.commit("feat: first", {"VERSION": "0.0.0\n"})
    assert release.create_tag("0.1.0b1", branch="release/0.1") == "v0.1.0b1"
    # The branch is HEAD; the tag is the commit that records the version on top of it.
    assert repo.git("ls-remote", "origin", "refs/heads/release/0.1").split()[0] == head
    tagged = repo.git("rev-parse", "v0.1.0b1^{commit}")
    assert repo.git("rev-parse", f"{tagged}^") == head
    assert repo.remote_tags() == ["v0.1.0b1"]


def test_tag_with_a_branch_pushes_nothing_if_the_branch_fails(repo: Repo) -> None:
    first = repo.commit("feat: first")
    repo.commit("feat: second")
    repo.git("push", "--quiet", "origin", "HEAD:refs/heads/release/0.1")
    repo.git("checkout", "--quiet", "--detach", first)
    # Not a fast-forward: the atomic push rejects the branch, and so the tag.
    with pytest.raises(subprocess.CalledProcessError):
        release.create_tag("0.1.0b1", branch="release/0.1")
    assert repo.remote_tags() == []


# create_tag (replaces cmd_tag for direct calls)


# backport-targets


def push_branches(repo: Repo, *series: str) -> None:
    """Create release/SERIES on origin at HEAD for each of SERIES."""
    for s in series:
        repo.git("push", "--quiet", "origin", f"HEAD:refs/heads/release/{s}")


def test_backport_targets_without_release_branches(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    assert run(capsys, "backport-targets") == {"branches": "", "versions": ""}


def test_backport_targets_the_newest_released_line(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    push_branches(repo, "0.3", "0.4")
    # Alphas of the next release don't create a branch.
    tag(repo, "v0.3.0", "v0.4.0", "v0.4.1", "v0.5.0a1")
    assert run(capsys, "backport-targets") == {
        "branches": "release/0.4",
        "versions": "v0.4.2",
    }


def test_backport_targets_both_lines_during_a_pre_release(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    push_branches(repo, "0.3", "0.4", "0.5")
    tag(repo, "v0.3.0", "v0.4.0", "v0.5.0b1", "v0.5.0b2")
    assert run(capsys, "backport-targets") == {
        "branches": "release/0.5 release/0.4",
        "versions": "v0.5.0b3 v0.4.1",
    }


def test_backport_targets_the_first_release(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("feat: first")
    push_branches(repo, "0.1")
    tag(repo, "v0.1.0rc1")
    assert run(capsys, "backport-targets") == {
        "branches": "release/0.1",
        "versions": "v0.1.0rc2",
    }


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


# sync-changelog

CHANGELOG_HEADER = (
    "# Changelog\n\nAll notable changes to this project are listed here.\n"
)


def section(version: str, entry: str) -> str:
    """Return a changelog section as git-cliff writes it."""
    return f"## {version} (2026-01-01)\n\n### Fixes\n\n- {entry}\n"


def changelog(*sections: str) -> str:
    """Return a CHANGELOG.md with SECTIONS, as git-cliff writes it."""
    return "\n".join([CHANGELOG_HEADER, *sections])


def tag_changelog(repo: Repo, name: str, text: str) -> None:
    """Tag NAME on a commit off main whose CHANGELOG.md is TEXT; back to main."""
    repo.git("checkout", "--quiet", "-b", f"line/{name}")
    repo.commit(f"chore: release {name}", {"CHANGELOG.md": text})
    repo.git("tag", "-a", name, "-m", name)
    repo.git("checkout", "--quiet", "main")


@pytest.mark.parametrize(
    ("main", "tag_name", "released", "expected"),
    [
        pytest.param(
            [section("0.2.0", "B"), section("0.1.0", "A")],
            "v0.1.1",
            [section("0.1.1", "F"), section("0.1.0", "A")],
            [section("0.2.0", "B"), section("0.1.1", "F"), section("0.1.0", "A")],
            id="patch-of-the-previous-line",
        ),
        pytest.param(
            [section("0.1.1", "F"), section("0.1.0", "A")],
            "v0.2.0",
            [section("0.2.0", "B"), section("0.1.0", "A")],  # a stale release PR
            [section("0.2.0", "B"), section("0.1.1", "F"), section("0.1.0", "A")],
            id="stale-release-pr",
        ),
        pytest.param(
            [section("0.2.0", "B")],
            "v0.1.0",
            [section("0.1.0", "A")],
            [section("0.2.0", "B"), section("0.1.0", "A")],
            id="at-the-end",
        ),
    ],
)
def test_sync_changelog_inserts_the_section_in_version_order(  # noqa: PLR0913, PLR0917
    repo: Repo,
    capsys: pytest.CaptureFixture[str],
    main: list[str],
    tag_name: str,
    released: list[str],
    expected: list[str],
) -> None:
    repo.commit("chore: start")
    tag_changelog(repo, tag_name, changelog(*released))
    path = repo.path / "CHANGELOG.md"
    path.write_text(changelog(*main), encoding="utf-8")
    run(capsys, "sync-changelog", tag_name)
    assert path.read_text(encoding="utf-8") == changelog(*expected)


def test_sync_changelog_keeps_a_present_section(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("chore: start")
    tag_changelog(repo, "v0.1.0", changelog(section("0.1.0", "reworded later")))
    path = repo.path / "CHANGELOG.md"
    text = changelog(section("0.2.0", "B"), section("0.1.0", "A"))
    path.write_text(text, encoding="utf-8")
    run(capsys, "sync-changelog", "v0.1.0")
    assert path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize(
    "existing", [None, "", "\n"], ids=["missing", "empty", "blank"]
)
def test_sync_changelog_copies_the_whole_file_to_a_new_changelog(
    repo: Repo, capsys: pytest.CaptureFixture[str], existing: str | None
) -> None:
    repo.commit("chore: start")
    text = changelog(section("0.1.0", "A"), section("0.0.1", "Z"))
    tag_changelog(repo, "v0.1.0", text)
    path = repo.path / "CHANGELOG.md"
    if existing is not None:
        path.write_text(existing, encoding="utf-8")
    run(capsys, "sync-changelog", "v0.1.0")
    assert path.read_text(encoding="utf-8") == text


def test_sync_changelog_refuses_pre_releases(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("chore: start")
    message = fails(capsys, "sync-changelog", "v0.2.0rc1")
    assert "::error::v0.2.0rc1 is not a final release tag (vX.Y.Z)." in message


def test_sync_changelog_does_nothing_when_tag_has_no_section(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("chore: start")
    tag_changelog(repo, "v0.2.0", changelog(section("0.1.0", "A")))
    path = repo.path / "CHANGELOG.md"
    original = changelog(section("0.1.0", "A"))
    path.write_text(original, encoding="utf-8")
    release.main(["sync-changelog", "v0.2.0"])
    output = capsys.readouterr().out
    assert path.read_text(encoding="utf-8") == original
    assert (
        "::notice::CHANGELOG.md at v0.2.0 has no section for 0.2.0: nothing to add."
        in output
    )


def test_sync_changelog_refuses_a_tag_without_changelog(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("chore: start")
    tag(repo, "v0.1.0")
    assert "::error::v0.1.0 has no CHANGELOG.md." in fails(
        capsys, "sync-changelog", "v0.1.0"
    )

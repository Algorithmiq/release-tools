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

"""Tests of the develop and tag-development commands: main after a final release."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from release import development
from release.cli import main

if TYPE_CHECKING:
    from conftest import Repo

PYPROJECT = '[project]\nname = "demo"\nversion = "0.0.0"\n'


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[dict[str, str], str]:
    """Run the release package with ARGV; return its key=value outputs and the log.

    Standard output holds only the outputs; the annotations go to standard error.
    """
    main(list(argv))
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert all("=" in line and "::" not in line for line in lines), captured.out
    return dict(line.split("=", 1) for line in lines), captured.err


def released(repo: Repo, *finals: str) -> None:
    """Tag each of FINALS on its own commit off main, as release/X.Y does."""
    for name in finals:
        repo.git("checkout", "--quiet", "--detach", "main")
        repo.commit(f"chore: release {name}")
        repo.git("tag", "-a", name, "-m", name)
    repo.git("checkout", "--quiet", "main")


@pytest.mark.parametrize(
    ("finals", "tag", "expected"),
    [
        pytest.param(["v1.2.0"], "v1.2.0", "1.3.0.dev0", id="minor"),
        pytest.param(["v1.2.0", "v2.0.0"], "v2.0.0", "2.1.0.dev0", id="major"),
        pytest.param(["v0.9.0", "v0.10.0"], "v0.10.0", "0.11.0.dev0", id="two-digits"),
        pytest.param(["v1.2.0", "v1.2.1"], "v1.2.1", "", id="patch"),
        pytest.param(["v1.1.0", "v1.2.0", "v1.1.1"], "v1.1.1", "", id="older-line"),
        # A final of an older line tagged after a newer one: impossible today, but main
        # must never move back.
        pytest.param(["v1.2.0", "v1.1.0"], "v1.1.0", "", id="older-x-y-0"),
    ],
)
def test_development_version(
    repo: Repo, finals: list[str], tag: str, expected: str
) -> None:
    repo.commit("chore: start")
    released(repo, *finals)
    assert development.development_version(tag) == expected


@pytest.mark.parametrize("tag", ["v1.3.0rc1", "v1.3.0.dev0", "main"])
def test_development_version_refuses_other_tags(
    repo: Repo, capsys: pytest.CaptureFixture[str], tag: str
) -> None:
    repo.commit("chore: start")
    with pytest.raises(SystemExit):
        main(["develop", tag])
    assert f"::error::{tag} is not a final release tag (vX.Y.Z)." in (
        capsys.readouterr().err
    )


def test_develop_writes_the_version_files(
    repo: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo.commit("chore: start", {"VERSION": "0.0.0\n", "pyproject.toml": PYPROJECT})
    released(repo, "v1.2.0")
    monkeypatch.setenv("VERSION_FILES", "VERSION pyproject.toml")
    outputs, _ = run(capsys, "develop", "v1.2.0")
    assert outputs == {"version": "1.3.0.dev0"}
    assert (repo.path / "VERSION").read_text() == "1.3.0.dev0\n"
    assert 'version = "1.3.0.dev0"' in (repo.path / "pyproject.toml").read_text()


def test_develop_leaves_the_version_files_after_a_patch(
    repo: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo.commit("chore: start", {"VERSION": "1.3.0.dev0\n"})
    released(repo, "v1.2.0", "v1.2.1")
    monkeypatch.setenv("VERSION_FILES", "VERSION")
    outputs, _ = run(capsys, "develop", "v1.2.1")
    assert outputs == {"version": ""}
    assert not repo.git("status", "--porcelain")


def test_develop_without_version_files(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("chore: start")
    released(repo, "v1.2.0")
    outputs, _ = run(capsys, "develop", "v1.2.0")
    assert outputs == {"version": "1.3.0.dev0"}
    assert not repo.git("status", "--porcelain")


def merge_changelog(repo: Repo, tag: str) -> str:
    """Squash-merge TAG's changelog PR into main on origin, then a later change."""
    commit = repo.commit(f"chore: update changelog for {tag} (#7)")
    repo.commit("feat: later (#8)")
    repo.git("push", "--quiet", "origin", "HEAD:refs/heads/main")
    return commit


def test_tag_development_tags_the_changelog_commit(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("chore: update changelog for v1.1.0 (#3)")
    released(repo, "v1.1.0", "v1.2.0")
    commit = merge_changelog(repo, "v1.2.0")
    outputs, _ = run(capsys, "tag-development", "v1.2.0")
    assert outputs == {"tag": "v1.3.0.dev0"}
    assert "v1.3.0.dev0" in repo.remote_tags()
    assert repo.git("rev-parse", "v1.3.0.dev0^{commit}") == commit
    assert repo.git("tag", "-l", "--format=%(contents:subject)", "v1.3.0.dev0") == (
        "Development of 1.3"
    )
    # git describe, and so setuptools-scm, hatch-vcs and copier, now see main above
    # v1.2.0.
    assert repo.git("describe", "--tags", "main").startswith("v1.3.0.dev0-1-g")


def test_tag_development_finds_the_commit_of_a_direct_push(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("chore: start")
    released(repo, "v1.2.0")
    commit = repo.commit("chore: update changelog for v1.2.0")
    repo.git("push", "--quiet", "origin", "HEAD:refs/heads/main")
    outputs, _ = run(capsys, "tag-development", "v1.2.0")
    assert outputs == {"tag": "v1.3.0.dev0"}
    assert repo.git("rev-parse", "v1.3.0.dev0^{commit}") == commit


def test_tag_development_skips_patches(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("chore: start")
    released(repo, "v1.2.0", "v1.2.1")
    merge_changelog(repo, "v1.2.1")
    outputs, _ = run(capsys, "tag-development", "v1.2.1")
    assert outputs == {"tag": ""}
    assert repo.remote_tags() == []


def test_tag_development_keeps_an_existing_tag(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("chore: start")
    released(repo, "v1.2.0")
    merge_changelog(repo, "v1.2.0")
    repo.git("tag", "-a", "v1.3.0.dev0", "-m", "earlier", "main~1")
    outputs, log = run(capsys, "tag-development", "v1.2.0")
    assert outputs == {"tag": ""}
    assert "::notice::v1.3.0.dev0 already exists." in log
    assert repo.remote_tags() == []


def test_tag_development_warns_until_the_changelog_is_on_main(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("chore: start")
    released(repo, "v1.2.0")
    repo.git("push", "--quiet", "origin", "HEAD:refs/heads/main")
    # The changelog PR waits for auto-merge: only its branch has the commit.
    repo.git("checkout", "--quiet", "-b", "changelog/v1.2.0")
    repo.commit("chore: update changelog for v1.2.0")
    outputs, log = run(capsys, "tag-development", "v1.2.0")
    assert outputs == {"tag": ""}
    assert "::warning::main doesn't have the changelog of v1.2.0 yet" in log
    assert "Re-run this job after the changelog PR merges." in log
    assert "v1.3.0.dev0" not in repo.git("tag", "--list")


def test_tag_development_ignores_other_changelog_commits(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("chore: update changelog for v1.2.0rc1")
    repo.commit("chore: update changelog for v1.2.00 (#2)")
    released(repo, "v1.2.0")
    repo.git("push", "--quiet", "origin", "HEAD:refs/heads/main")
    outputs, _ = run(capsys, "tag-development", "v1.2.0")
    assert outputs == {"tag": ""}

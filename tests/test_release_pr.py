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

"""Tests of the release-pr command, run in-process with a stand-in for gh."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from release.cli import main

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import Repo

VERSION_FILES = "VERSION pyproject.toml"
PYPROJECT = '[project]\nname = "demo"\nversion = "0.0.0"\n'


@dataclass(frozen=True)
class Result:
    """What the release-pr command did: the gh calls and the body it passed."""

    calls: list[str]
    body: str


def release_pr(  # noqa: PLR0913
    repo: Repo,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    pending: str,
    stage: str,
    pr_list: str = "",
) -> Result:
    """Run release-pr for release/0.1 at HEAD; gh finds the open PR PR_LIST.

    PR_LIST is what the real gh prints for the script's --jq filter: "<number>
    <isDraft>", or nothing when there is no open PR.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$*" >> "{tmp_path}/gh-calls"\n'
        'previous=""\n'
        'for arg in "$@"; do\n'
        f'  if [[ "$previous" == --body-file ]]; then cp "$arg" '
        f'"{tmp_path}/body.md"; fi\n'
        '  previous="$arg"\n'
        "done\n"
        'if [[ "$1 $2" == "pr list" ]]; then printf "%s" "$GH_PR_LIST"; fi\n',
        encoding="utf-8",
    )
    gh.chmod(0o755)
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir(exist_ok=True)
    monkeypatch.chdir(repo.path)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))
    monkeypatch.setenv("VERSION_FILES", VERSION_FILES)
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setenv("GH_PR_LIST", pr_list)
    main(
        [
            "release-pr",
            "--series",
            "0.1",
            "--version",
            pending,
            "--stage",
            stage,
            "--head",
            repo.git("rev-parse", "HEAD"),
        ]
    )
    return Result(
        calls=(tmp_path / "gh-calls").read_text(encoding="utf-8").splitlines(),
        body=(tmp_path / "body.md").read_text(encoding="utf-8"),
    )


@pytest.fixture
def branch(repo: Repo) -> Repo:
    """Return a repository with release/0.1 on origin: a breaking change and a fix."""
    repo.commit("chore: start", {"VERSION": "0.0.0\n", "pyproject.toml": PYPROJECT})
    repo.git("tag", "-a", "v0.0.0", "-m", "start")
    repo.commit("feat!: 💥 drop the old API (#1)\n\n## Migration\n\nUse `new()`.\n")
    repo.commit("fix: 🐛 a fix (#2)")
    repo.git(
        "push", "--quiet", "--follow-tags", "origin", "HEAD:refs/heads/release/0.1"
    )
    return repo


def test_opens_the_release_pr(
    branch: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = branch.git("rev-parse", "HEAD")
    result = release_pr(branch, tmp_path, monkeypatch, pending="0.1.0", stage="rc")

    pr_head = "origin/release-pr/0.1"
    branch.git("fetch", "--quiet", "origin")
    assert branch.git("log", "-1", "--format=%s", pr_head) == "chore: release v0.1.0"
    assert branch.git("rev-parse", f"{pr_head}^") == sha
    assert branch.git("show", f"{pr_head}:VERSION") == "0.1.0"
    changelog = branch.git("show", f"{pr_head}:CHANGELOG.md")
    assert changelog.startswith("# Changelog\n\nAll notable changes")
    assert (
        "### Breaking changes\n\n- Drop the old API (#1)\n\n  Use `new()`." in changelog
    )
    assert branch.git("status", "--porcelain") == ""  # nothing left in the work tree
    assert result.calls[0].startswith(
        "pr list --head release-pr/0.1 --base release/0.1 --state open"
    )
    assert result.calls[1].startswith(
        "pr create --head release-pr/0.1 --base release/0.1 "
        "--title chore: release v0.1.0 --body-file "
    )
    assert len(result.calls) == 2
    assert result.body.startswith("Merging this PR releases **v0.1.0**.")
    assert "- A fix (#2)" in result.body
    assert "Patch releases have no release candidates." not in result.body


def test_starts_from_the_changelog_of_main(
    branch: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # main has a section the release branch lacks (a patch of another line).
    main_changelog = (
        "# Changelog\n\nAll notable changes to this project are listed here.\n\n"
        "## 0.0.1 (2026-01-01)\n\n### Fixes\n\n- Old fix (#0)\n"
    )
    # The fixture's commits are on the local main: add main's changelog on top of
    # them, then go back to the release branch.
    branch.commit("chore: update changelog", {"CHANGELOG.md": main_changelog})
    branch.git("push", "--quiet", "origin", "HEAD:refs/heads/main")
    branch.git("fetch", "--quiet", "origin")
    branch.git("checkout", "--quiet", "--detach", "origin/release/0.1")

    release_pr(branch, tmp_path, monkeypatch, pending="0.1.0", stage="rc")

    branch.git("fetch", "--quiet", "origin")
    changelog = branch.git("show", "origin/release-pr/0.1:CHANGELOG.md")
    assert changelog.index("## 0.1.0 (") < changelog.index("## 0.0.1 (")
    assert changelog.count("# Changelog") == 1


def test_opens_a_draft_during_beta(
    branch: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = release_pr(branch, tmp_path, monkeypatch, pending="0.1.0", stage="beta")
    assert result.calls[1].startswith("pr create --draft --head release-pr/0.1 ")
    assert result.body.startswith(
        "Draft while v0.1.0 is in beta. To move to release candidates, run Release"
        " with stage `rc`.\n\nMerging this PR releases **v0.1.0**."
    )


@pytest.mark.parametrize(
    ("stage", "pr_list", "ready"),
    [
        ("beta", "7 false", ["pr ready 7 --undo"]),
        ("beta", "7 true", []),
        ("rc", "7 true", ["pr ready 7"]),
        ("rc", "7 false", []),
        ("released", "7 true", ["pr ready 7"]),
    ],
)
def test_updates_the_open_pr_and_its_draft_state(  # noqa: PLR0913, PLR0917
    branch: Repo,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    pr_list: str,
    ready: list[str],
) -> None:
    result = release_pr(
        branch, tmp_path, monkeypatch, pending="0.1.0", stage=stage, pr_list=pr_list
    )
    assert result.calls[1].startswith(
        "pr edit 7 --title chore: release v0.1.0 --body-file "
    )
    assert result.calls[2:] == ready


def test_patch_release_pr_explains_patches(
    branch: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    branch.git("tag", "-a", "v0.1.0", "-m", "Release 0.1.0")
    branch.commit("fix: 🐛 another fix (#3)")
    branch.git(
        "push", "--quiet", "--follow-tags", "origin", "HEAD:refs/heads/release/0.1"
    )
    result = release_pr(
        branch, tmp_path, monkeypatch, pending="0.1.1", stage="released"
    )
    assert (
        "Every fix backported to `release/0.1` is added to this PR. Merge it when the"
        " fixes\nshould ship. Patch releases have no release candidates." in result.body
    )
    assert "- Another fix (#3)" in result.body


def test_release_pr_needs_every_argument(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["release-pr", "--series", "0.1"])
    assert "--version" in capsys.readouterr().err

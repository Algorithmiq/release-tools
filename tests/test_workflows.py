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

"""Tests of the contracts between the reusable workflows and the release package.

actionlint checks the workflows themselves; these check that they only read the
outputs the release package writes and pass the arguments release-pr needs.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import TYPE_CHECKING, Any

import pytest
import yaml
from conftest import ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import Repo

WORKFLOWS = ROOT / ".github" / "workflows"

# The outputs of the release package commands, by the id of the step that runs them; the
# tests of the release package pin each command's outputs exactly.
OUTPUTS = {
    "start": {
        "action",
        "series",
        "branch",
        "version",
        "tag_version",
        "head",
        "summary",
    },
    "plan": {"series", "action", "tag_version", "pending", "stage", "previous"},
    "targets": {"branches", "versions"},
}


def load(name: str) -> dict[Any, Any]:
    """Load a workflow; PyYAML reads its `on:` key as True."""
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["release.yml", "backport.yml"])
def test_steps_read_only_outputs_that_the_package_writes(name: str) -> None:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    used = re.findall(r"steps\.(start|plan|targets)\.outputs\.(\w+)", text)
    assert used
    for step_id, key in used:
        assert key in OUTPUTS[step_id], (step_id, key)


def test_every_release_pr_step_passes_its_arguments() -> None:
    workflow = load("release.yml")
    assert {"RELEASE_TOOLS", "VERSION_FILES"} <= set(workflow["env"])
    steps = [
        (job, step)
        for job, spec in workflow["jobs"].items()
        for step in spec["steps"]
        if " release-pr " in step.get("run", "")
    ]
    assert sorted(job for job, _ in steps) == ["start", "update"]
    for _, step in steps:
        run = " ".join(step["run"].split())
        for flag, variable in (
            ("--series", "SERIES"),
            ("--version", "PENDING"),
            ("--stage", "STAGE"),
            ("--head", "HEAD_SHA"),
        ):
            assert f'{flag} "${variable}"' in run
            assert variable in step["env"]
        assert "GH_TOKEN" in step["env"]


def test_stage_input_defaults_to_release_candidates() -> None:
    stage = load("release.yml")[True]["workflow_call"]["inputs"]["stage"]
    assert (stage["type"], stage["default"]) == ("string", "rc")


def test_changelog_reaches_main_for_final_releases_only() -> None:
    condition = load("release.yml")["jobs"]["sync-changelog"]["if"]
    for suffix in ("'a'", "'b'", "'rc'", "'dev'"):
        assert f"!contains(github.ref_name, {suffix})" in condition


def test_changelog_job_tags_the_development_of_main_last() -> None:
    steps = load("release.yml")["jobs"]["sync-changelog"]["steps"]
    assert steps[-2]["name"] == "Open the changelog PR and merge it"
    assert steps[-1]["name"] == "Tag the development of the next release on main"
    assert " tag-development " in steps[-1]["run"]
    assert steps[-1]["env"] == {"TAG": "${{ github.ref_name }}"}


def step_script(workflow: str, job: str, name: str) -> str:
    """Return the run: script of the step NAME of JOB in WORKFLOW."""
    (step,) = [s for s in load(workflow)["jobs"][job]["steps"] if s.get("name") == name]
    return step["run"]


@pytest.mark.parametrize(
    ("versions", "ships"),
    [
        ("v1.1.1", "**v1.1.1**"),
        ("v1.2.0b3 v1.1.1", "**v1.2.0b3** and **v1.1.1**"),
    ],
)
def test_backport_suggestion(tmp_path: Path, versions: str, ships: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        f'#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "{tmp_path}/gh-args"\n',
        encoding="utf-8",
    )
    gh.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GH_TOKEN": "token",
        "GH_REPO": "Algorithmiq/demo",
        "NUMBER": "12",
        "VERSIONS": versions,
    }
    script = step_script("backport.yml", "suggest", "Suggest the backport label")
    subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert (tmp_path / "gh-args").read_text(encoding="utf-8").splitlines() == [
        "pr",
        "comment",
        "12",
        "--body",
        (
            f"This fix isn't in a release yet. To ship it in {ships}, add the "
            "`backport` label; it works after merging too."
        ),
    ]


def test_suggestion_is_only_for_fixes_merged_into_the_default_branch() -> None:
    condition = load("backport.yml")["jobs"]["suggest"]["if"]
    for part in (
        "github.event.action == 'closed'",
        "github.event.pull_request.merged == true",
        "github.event.pull_request.base.ref == github.event.repository.default_branch",
        "!contains(github.event.pull_request.labels.*.name, 'backport')",
        "!contains(github.event.pull_request.title, '!:')",
        "startsWith(github.event.pull_request.title, 'fix:')",
        "startsWith(github.event.pull_request.title, 'perf(')",
    ):
        assert part in condition


def test_backport_pr_carries_the_description_of_the_original() -> None:
    # The changelog of the release line takes the migration notes from the description
    # of the backport PR that was squash-merged there.
    steps = load("backport.yml")["jobs"]["backport"]["steps"]
    (step,) = [s for s in steps if s.get("uses", "").startswith("korthout/")]
    assert step["with"]["pull_description"] == (
        "Backport of #${pull_number} to `${target_branch}`.\n\n${pull_description}"
    )


@pytest.mark.parametrize("workflow", ["release.yml", "backport.yml"])
def test_release_tools_checkout_is_excluded_from_git(
    workflow: str,
) -> None:
    """Every job that checks out .release-tools excludes it via .git/info/exclude."""
    jobs = load(workflow)["jobs"]
    for job_name, job_spec in jobs.items():
        steps = job_spec["steps"]
        has_release_tools_checkout = any(
            step.get("with", {}).get("path") == ".release-tools" for step in steps
        )
        if not has_release_tools_checkout:
            continue
        # Find the index of the checkout step.
        checkout_idx = next(
            i
            for i, s in enumerate(steps)
            if s.get("with", {}).get("path") == ".release-tools"
        )
        # The next step must be the exclude step.
        next_step = steps[checkout_idx + 1]
        assert "run" in next_step, (
            f"{workflow}::{job_name} checkout of .release-tools must be followed by "
            "the exclude step"
        )
        assert ".git/info/exclude" in next_step["run"], (
            f"{workflow}::{job_name} checkout of .release-tools must be followed by "
            "a step that adds it to .git/info/exclude"
        )


def deploy(repo: Repo, tmp_path: Path, tag: str) -> list[str]:
    """Run the docs deploy step for TAG in REPO with a stand-in uv; return calls."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    uv = bin_dir / "uv"
    uv.write_text(
        f'#!/usr/bin/env bash\necho "$*" >> "{tmp_path}/mike-calls"\n',
        encoding="utf-8",
    )
    uv.chmod(0o755)
    script = step_script("self-publish.yml", "docs", "Deploy this version")
    subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        cwd=repo.path,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "TAG": tag,
        },
        check=True,
        capture_output=True,
        text=True,
    )
    calls = tmp_path / "mike-calls"
    return calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []


def tag(repo: Repo, *names: str) -> None:
    """Create lightweight tags NAMES on HEAD."""
    for name in names:
        repo.git("tag", name)


def test_docs_first_final_release(repo: Repo, tmp_path: Path) -> None:
    repo.commit("chore: start")
    tag(repo, "v1.0.0", "v1.1.0", "v1.2.0")
    assert deploy(repo, tmp_path, "v1.2.0") == [
        "run --no-sync mike deploy --push --update-aliases --title 1.2 1.2 latest",
        "run --no-sync mike set-default --push latest",
    ]


def test_docs_final_release_of_the_newest_line(repo: Repo, tmp_path: Path) -> None:
    repo.commit("chore: start")
    tag(repo, "v1.2.0", "v1.3.0")
    # gh-pages already has its root redirect.
    repo.git("checkout", "--quiet", "--orphan", "gh-pages")
    repo.commit("Deployed", {"index.html": "redirect"})
    repo.git("update-ref", "refs/remotes/origin/gh-pages", "HEAD")
    assert deploy(repo, tmp_path, "v1.3.0") == [
        "run --no-sync mike deploy --push --update-aliases --title 1.3 1.3 latest",
        "run --no-sync mike set-default --push latest",
    ]


def test_docs_patch_of_an_older_line(repo: Repo, tmp_path: Path) -> None:
    repo.commit("chore: start")
    tag(repo, "v1.2.0", "v1.3.0", "v1.2.3")
    assert deploy(repo, tmp_path, "v1.2.3") == [
        "run --no-sync mike deploy --push --title 1.2 1.2",
    ]


def test_docs_pre_release(repo: Repo, tmp_path: Path) -> None:
    repo.commit("chore: start")
    tag(repo, "v1.2.0", "v1.3.0b1")
    # gh-pages already exists from v1.2.0.
    repo.git("checkout", "--quiet", "--orphan", "gh-pages")
    repo.commit("Deployed", {"index.html": "redirect"})
    repo.git("update-ref", "refs/remotes/origin/gh-pages", "HEAD")
    assert deploy(repo, tmp_path, "v1.3.0b1") == [
        "run --no-sync mike deploy --push --title 1.3 (pre-release) 1.3",
    ]


def test_docs_first_pre_release(repo: Repo, tmp_path: Path) -> None:
    repo.commit("chore: start")
    tag(repo, "v1.2.0b1")
    assert deploy(repo, tmp_path, "v1.2.0b1") == [
        "run --no-sync mike deploy --push --title 1.2 (pre-release) 1.2",
        "run --no-sync mike set-default --push 1.2",
    ]


def sync_changelog(
    repo: Repo,
    tmp_path: Path,
    failing: str = "",
    version_files: str = "",
    open_pr: str = "",
) -> tuple[str, list[str]]:
    """Run the changelog job's PR step for v0.1.0 with a stand-in gh.

    The stand-in fails the `gh pr merge` calls whose arguments contain FAILING, and
    answers `gh pr list` with the number OPEN_PR of an open changelog PR (none if
    empty). Returns the step's output and the gh calls (the `gh pr create` and
    `gh pr merge` calls, and the PR's body).
    """
    repo.commit("chore: start", {"VERSION": "0.0.0\n"} if version_files else None)
    repo.git("push", "--quiet", "origin", "HEAD:refs/heads/main")
    repo.git("checkout", "--quiet", "-b", "release/0.1")
    section = "## 0.1.0 (2026-01-01)\n\n### Fixes\n\n- A fix (#1)\n"
    repo.commit(
        "chore: release v0.1.0 (#2)", {"CHANGELOG.md": f"# Changelog\n\n{section}"}
    )
    repo.git("tag", "-a", "v0.1.0", "-m", "Release 0.1.0")
    repo.git("checkout", "--quiet", "main")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$*" >> "{tmp_path}/gh-calls"\n'
        'if [[ "$1 $2" == "pr list" ]]; then\n'
        '  echo "$OPEN_PR"\n'
        "fi\n"
        'if [[ "$1 $2" == "pr merge" && -n "$FAILING" &&'
        ' "$*" == *"$FAILING"* ]]; then\n'
        "  exit 1\n"
        "fi\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    script = step_script(
        "release.yml", "sync-changelog", "Open the changelog PR and merge it"
    )
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        cwd=repo.path,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "RELEASE_TOOLS": str(ROOT),
            "TAG": "v0.1.0",
            "FAILING": failing,
            "OPEN_PR": open_pr,
            "VERSION_FILES": version_files,
        },
        capture_output=True,
        text=True,
        check=True,
    )
    calls = (tmp_path / "gh-calls").read_text(encoding="utf-8").splitlines()
    return result.stdout, [
        call for call in calls if call.startswith(("pr merge", "pr create"))
    ]


def test_changelog_pr_is_merged_with_the_bypass(repo: Repo, tmp_path: Path) -> None:
    _, calls = sync_changelog(repo, tmp_path)
    assert calls == [
        (
            "pr create --head changelog/v0.1.0 --base main --title chore: update"
            " changelog for v0.1.0 --body Adds the v0.1.0 section of `CHANGELOG.md` to"
            " `main`."
        ),
        "pr merge changelog/v0.1.0 --squash --admin --delete-branch",
    ]
    assert "## 0.1.0" in repo.git("show", "origin/changelog/v0.1.0:CHANGELOG.md")


def test_changelog_pr_moves_the_version_files_on(repo: Repo, tmp_path: Path) -> None:
    _, calls = sync_changelog(repo, tmp_path, version_files="VERSION")
    assert calls[0].endswith(
        " Sets the version files to 0.2.0.dev0: `main` develops the next release."
    )
    changed = repo.git("show", "--name-only", "--format=", "origin/changelog/v0.1.0")
    assert changed.split() == ["CHANGELOG.md", "VERSION"]
    assert repo.git("show", "origin/changelog/v0.1.0:VERSION") == "0.2.0.dev0"


def test_changelog_pr_falls_back_to_auto_merge(repo: Repo, tmp_path: Path) -> None:
    output, calls = sync_changelog(repo, tmp_path, failing="--admin")
    assert calls[1:] == [
        "pr merge changelog/v0.1.0 --squash --admin --delete-branch",
        "pr merge changelog/v0.1.0 --squash --auto --delete-branch",
    ]
    assert "::warning::" in output


def test_changelog_pr_left_for_a_maintainer(repo: Repo, tmp_path: Path) -> None:
    output, calls = sync_changelog(repo, tmp_path, failing="--squash")
    assert len(calls) == 3
    assert "::warning::Could not merge the changelog PR; merge it by hand." in output


def test_rerun_with_the_changelog_pr_open_only_merges_it(
    repo: Repo, tmp_path: Path
) -> None:
    _, calls = sync_changelog(repo, tmp_path, open_pr="7")
    assert calls == ["pr merge changelog/v0.1.0 --squash --admin --delete-branch"]
    # The job rebuilt the branch from the current main and force-pushed it.
    assert "## 0.1.0" in repo.git("show", "origin/changelog/v0.1.0:CHANGELOG.md")


def test_changelog_pr_lookup_is_for_its_branch_into_main(
    repo: Repo, tmp_path: Path
) -> None:
    sync_changelog(repo, tmp_path)
    lists = [
        call
        for call in (tmp_path / "gh-calls").read_text(encoding="utf-8").splitlines()
        if call.startswith("pr list")
    ]
    assert len(lists) == 1
    assert lists[0].startswith(
        "pr list --head changelog/v0.1.0 --base main --state open"
    )


def run_wrong_branch_guard(ref_name: str) -> subprocess.CompletedProcess[str]:
    """Run the script of the guard job against a dispatch from the branch REF_NAME."""
    script = load("release.yml")["jobs"]["wrong-branch"]["steps"][0]["run"]
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        env={**os.environ, "REF_NAME": ref_name},
        capture_output=True,
        text=True,
        check=False,
    )


def test_dispatch_from_another_branch_fails_saying_to_start_from_main() -> None:
    result = run_wrong_branch_guard("feature/x")
    assert result.returncode == 1
    assert result.stdout.startswith("::error ")
    assert "Releases start from main" in result.stdout
    assert "'feature/x'" in result.stdout


def test_wrong_branch_guard_is_the_complement_of_the_start_job() -> None:
    jobs = load("release.yml")["jobs"]
    guard, start = jobs["wrong-branch"], jobs["start"]
    assert start["if"] == (
        "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'"
    )
    assert guard["if"] == (
        "github.event_name == 'workflow_dispatch' && github.ref != 'refs/heads/main'"
    )
    # It runs no action: no app token, no checkout.
    assert all("uses" not in step for step in guard["steps"])
    assert "needs" not in guard
    assert guard["steps"][0]["env"] == {"REF_NAME": "${{ github.ref_name }}"}

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
shellcheck here, and run in bash as the runner runs them, with a stand-in for gh
(recording its arguments). The git-cliff of the dev dependencies, on PATH, stands in for
the one taiki-e/install-action installs.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from datetime import datetime
from typing import TYPE_CHECKING, Any

import pytest
import yaml
from conftest import ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import FakeGitHub, Repo

ACTIONS = sorted((ROOT / "actions").glob("*/action.yml"))


def steps(action: str) -> list[dict[str, Any]]:
    """Return the steps of ACTION."""
    metadata = yaml.safe_load((ROOT / "actions" / action / "action.yml").read_text())
    return metadata["runs"]["steps"]


def scripts(action: str) -> list[str]:
    """Return the run: scripts of ACTION, in bash."""
    runs = [step for step in steps(action) if "run" in step]
    assert all(step["shell"] == "bash" for step in runs)
    return [step["run"] for step in runs]


def script(action: str) -> str:
    """Return the last run: script of ACTION: the one that does its work."""
    return scripts(action)[-1]


@pytest.fixture
def bin_dir(tmp_path: Path) -> Path:
    """Return a directory, first on PATH, with a stand-in for gh."""
    directory = tmp_path / "bin"
    directory.mkdir()
    assert shutil.which("git-cliff"), (
        "git-cliff is missing: run the tests with `just test`"
    )
    stand_ins = {
        "gh": (
            'if [[ "$1 $2" == "api graphql" ]]; then exec "$FAKE_GH" "$@"; fi\n'
            f'printf "%s\\n" "$@" > "{tmp_path}/gh-args"'
        )
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
    for run in scripts(path.parent.name):
        # Inputs reach the scripts through env:, never through ${{ }} in the script.
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
        "GITHUB_ACTION_PATH": str(ROOT / "actions/release-notes"),
        "GITHUB_REF_NAME": "v0.1.0",
    }


def test_release_notes_of_a_final_release_without_a_changelog(
    released: Repo, bin_dir: Path, tmp_path: Path
) -> None:
    released.git("checkout", "--quiet", "v0.1.0")
    result = run_action("release-notes", notes_env(""), bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        "::warning::CHANGELOG.md at v0.1.0 has no section for 0.1.0: the notes come"
        " from the commits instead (git-cliff)." in result.stdout
    )
    assert "v0.1.0 has no CHANGELOG.md." in result.stderr
    notes = tmp_path / "runner-temp/release-notes.md"
    assert (tmp_path / "github-output").read_text() == f"path={notes}\n"
    text = notes.read_text()
    assert text.lstrip().startswith("## 0.1.0 (")
    assert "- First feature (#1)" in text
    assert "A fix" not in text


@pytest.fixture
def changelog_released(repo: Repo) -> Repo:
    """Return a repository like `released`, but v0.1.0 has a reworded CHANGELOG.md.

    The release commit is made as the release PR makes it: the section comes from
    git-cliff, and a maintainer then rewords an entry.
    """
    repo.commit("chore: start")
    repo.git("tag", "-a", "v0.0.0", "-m", "start")
    repo.commit("feat: ✨ first feature (#1)")
    path = repo.path / "CHANGELOG.md"
    path.touch()
    cliff_command("--unreleased", "--tag", "v0.1.0", "--prepend", "CHANGELOG.md")
    text = path.read_text(encoding="utf-8")
    assert "- First feature (#1)" in text
    path.write_text(
        text.replace("- First feature (#1)", "- First feature, reworded by hand (#1)"),
        encoding="utf-8",
    )
    repo.git("add", "CHANGELOG.md")
    repo.commit("chore: release v0.1.0 (#3)")
    repo.git("tag", "-a", "v0.1.0", "-m", "Release 0.1.0")
    repo.commit("fix: 🐛 a fix (#2)")
    repo.git("tag", "-a", "v0.2.0rc1", "-m", "Release 0.2.0rc1")
    repo.git("checkout", "--quiet", "v0.1.0")
    return repo


def cliff_command(*args: str) -> str:
    """Run git-cliff with the central cliff.toml in the current directory."""
    return subprocess.run(
        ["git-cliff", "--config", str(ROOT / "cliff.toml"), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@pytest.mark.usefixtures("changelog_released")
def test_release_notes_of_a_final_release_are_the_changelog_section(
    bin_dir: Path, tmp_path: Path
) -> None:
    # What the release PR reviewers fixed in CHANGELOG.md reaches the notes.
    expected = cliff_command("--current", "--strip", "header")
    assert "- First feature (#1)" in expected
    result = run_action("release-notes", notes_env("v0.1.0"), bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "::warning::" not in result.stdout
    # Otherwise as git-cliff writes them: the section without the file's header.
    notes = (tmp_path / "runner-temp/release-notes.md").read_text()
    assert notes.startswith("## 0.1.0 (")
    assert notes == expected.lstrip("\n").replace(
        "- First feature (#1)", "- First feature, reworded by hand (#1)"
    )


def test_release_notes_fall_back_to_git_cliff_without_the_section(
    changelog_released: Repo, bin_dir: Path, tmp_path: Path
) -> None:
    path = changelog_released.path / "CHANGELOG.md"
    path.write_text("# Changelog\n\n## 0.0.9 (2026-01-01)\n", encoding="utf-8")
    changelog_released.git("commit", "--quiet", "-a", "-m", "docs: drop the section")
    changelog_released.git("tag", "-a", "-f", "v0.1.0", "-m", "Release 0.1.0")
    result = run_action("release-notes", notes_env("v0.1.0"), bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "::warning::CHANGELOG.md at v0.1.0 has no section for 0.1.0" in result.stdout
    assert "CHANGELOG.md at v0.1.0 has no section for 0.1.0." in result.stderr
    text = (tmp_path / "runner-temp/release-notes.md").read_text()
    assert "- First feature (#1)" in text
    assert "reworded" not in text


def test_release_notes_of_a_release_candidate_ignore_the_changelog(
    changelog_released: Repo, bin_dir: Path, tmp_path: Path
) -> None:
    changelog_released.git("checkout", "--quiet", "v0.2.0rc1")
    result = run_action("release-notes", notes_env("v0.2.0rc1"), bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "::warning::" not in result.stdout


def test_release_notes_install_the_pinned_git_cliff() -> None:
    install, notes = steps("release-notes")
    assert install["uses"].startswith("taiki-e/install-action@")
    # Without a fallback, a version without a release binary fails instead of building.
    assert install["with"] == {"tool": "git-cliff@2.14.2", "fallback": "none"}
    assert notes["id"] == "notes"


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


def wrapped_breaking_change(repo: Repo) -> str:
    """Commit a breaking change whose body the web UI wrapped; return its sha."""
    repo.git("checkout", "--quiet", "v0.2.0rc1")
    body = (
        "## Migration\n\nCall `new(x)`, which takes the arguments of `old` in the\n"
        "order below:\n\n```python\nnew(x)\n```\n"
    )
    return repo.commit(f"feat!: 💥 replace old (#3)\n\n{body}")


def test_release_notes_of_a_pre_release_use_the_pr_descriptions(
    released: Repo, github: FakeGitHub, bin_dir: Path, tmp_path: Path
) -> None:
    sha = wrapped_breaking_change(released)
    released.git("tag", "-a", "v0.2.0rc2", "-m", "Release 0.2.0rc2")
    description = (
        "## Migration\r\n\r\nCall `new(x)`, which takes the arguments of `old` in the "
        "order below:\r\n\r\n```python\r\n    new(x)\r\n```\r\n"
    )
    github.add(3, description, sha)
    github.add(2, "A fix", released.git("rev-parse", "v0.2.0rc2~1"))
    env = notes_env("v0.2.0rc2") | {"NOTES": str(tmp_path / "rc.md"), "GH_TOKEN": "t"}
    result = run_action("release-notes", env, bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert github.calls == [[2, 3]]
    text = (tmp_path / "rc.md").read_text()
    assert text.lstrip().startswith("## 0.2.0rc2 (")
    link = "[#3](https://github.com/Algorithmiq/example/pull/3)"
    assert (
        f"- Replace old ({link})\n\n  Call `new(x)`, which takes the arguments of "
        "`old` in the order below:\n\n  ```python\n      new(x)\n  ```\n"
    ) in text
    assert "- A fix (" in text


def test_release_notes_of_a_pre_release_survive_an_api_failure(
    released: Repo, github: FakeGitHub, bin_dir: Path, tmp_path: Path
) -> None:
    wrapped_breaking_change(released)
    released.git("tag", "-a", "v0.2.0rc2", "-m", "Release 0.2.0rc2")
    github.fail("API rate limit exceeded")
    env = notes_env("v0.2.0rc2") | {"NOTES": str(tmp_path / "rc.md")}
    result = run_action("release-notes", env, bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "::warning::Could not read the description of PR #3 for commit " in (
        result.stderr
    )
    text = (tmp_path / "rc.md").read_text()
    assert "- Replace old (" in text
    assert "  Call `new(x)`, which takes the arguments of `old` in the\n  order" in text


def test_release_notes_pass_their_token_to_the_pr_descriptions() -> None:
    metadata = yaml.safe_load((ROOT / "actions/release-notes/action.yml").read_text())
    assert metadata["inputs"]["token"]["default"] == "${{ github.token }}"
    (notes,) = [step for step in steps("release-notes") if step.get("id") == "notes"]
    assert notes["env"]["GH_TOKEN"] == "${{ inputs.token }}"  # noqa: S105


@pytest.mark.usefixtures("released")
def test_release_notes_refuse_pre_releases_of_patches(
    bin_dir: Path, tmp_path: Path
) -> None:
    result = run_action("release-notes", notes_env("v0.1.1rc1"), bin_dir, tmp_path)
    assert result.returncode == 1
    assert "::error::'v0.1.1rc1' is not a release tag" in result.stdout


@pytest.mark.usefixtures("released")
def test_release_notes_explain_development_tags(bin_dir: Path, tmp_path: Path) -> None:
    result = run_action("release-notes", notes_env("v0.3.0.dev0"), bin_dir, tmp_path)
    assert result.returncode == 1
    assert (
        "::error::v0.3.0.dev0 marks the development of the next release on main and is"
        ' never published: add "!v*.dev*" to the tags of this workflow\'s push trigger.'
    ) in result.stdout


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


@pytest.mark.parametrize("tag", ["v1.2.1rc1", "v1.2", "main"])
def test_publish_release_refuses_other_tags(
    tmp_path: Path, bin_dir: Path, tag: str
) -> None:
    env = {"GH_TOKEN": "token", "GH_REPO": "x/y", "TAG": tag, "GITHUB_REF_NAME": tag}
    result = run_action("publish-release", env, bin_dir, tmp_path)
    assert result.returncode == 1
    assert f"::error::'{tag}' is not a release tag" in result.stdout
    assert not (tmp_path / "gh-args").exists()


# sbom


def test_sbom_sets_up_uv_without_a_cache() -> None:
    setup, sbom = steps("sbom")
    assert setup["uses"].startswith("astral-sh/setup-uv@")
    assert setup["with"] == {"enable-cache": False}
    assert sbom["id"] == "sbom"


def test_sbom_pins_cyclonedx_bom_as_the_dev_dependencies() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    (pin,) = re.findall(r'"(cyclonedx-bom==[\d.]+)"', pyproject)
    assert f"uvx --from {pin} cyclonedx-py environment" in script("sbom")


DEMO_PYPROJECT = """\
[project]
name = "demo"
version = "1.1.0"
license = "Apache-2.0"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
viz = []

[tool.uv]
package = false
"""


@pytest.fixture
def uv_project(repo: Repo) -> Repo:
    """Return a uv project without dependencies whose version is dynamic, committed.

    It is locked offline with a static version first: a dynamic one would make uv build
    the project, which needs a build backend. `uv sync --frozen --no-install-project`
    only reads the lock.
    """
    pyproject = repo.path / "pyproject.toml"
    pyproject.write_text(DEMO_PYPROJECT, encoding="utf-8")
    subprocess.run(
        ["uv", "lock", "--offline", "--quiet"],
        cwd=repo.path,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        check=True,
    )
    dynamic = DEMO_PYPROJECT.replace('version = "1.1.0"', 'dynamic = ["version"]')
    pyproject.write_text(dynamic, encoding="utf-8")
    repo.git("add", "pyproject.toml", "uv.lock")
    repo.git("commit", "--quiet", "-m", "chore: start")
    return repo


@pytest.fixture
def sbom_bin_dir(bin_dir: Path, tmp_path: Path) -> Path:
    """Add a stand-in for uvx that runs the cyclonedx-py of the dev dependencies."""
    cyclonedx = shutil.which("cyclonedx-py")
    assert cyclonedx, "cyclonedx-py is missing: run the tests with `just test`"
    uvx = bin_dir / "uvx"
    # uvx --from cyclonedx-bom==X cyclonedx-py ARGS...
    uvx.write_text(
        f'#!/usr/bin/env bash\necho "$@" >> "{tmp_path}/uvx-args"\n'
        f'shift 3\nexec "{cyclonedx}" "$@"\n',
        encoding="utf-8",
    )
    uvx.chmod(0o755)
    return bin_dir


def sbom_env(flavours: str = "", **extra: str) -> dict[str, str]:
    """Return the env: of the sbom step."""
    env = {
        "FLAVOURS": flavours,
        "SBOM_PATH": "sbom",
        "COMPONENT_TYPE": "library",
        "VERSION": "",
        "GITHUB_REF_TYPE": "tag",
        "GITHUB_REF_NAME": "v1.2.0",
        "VIRTUAL_ENV": "",
    }
    return env | extra


def bom(path: Path) -> dict[str, Any]:
    """Return the CycloneDX document at PATH."""
    return json.loads(path.read_text(encoding="utf-8"))


def test_sbom_of_the_runtime_dependencies(
    uv_project: Repo, sbom_bin_dir: Path, tmp_path: Path
) -> None:
    result = run_action("sbom", sbom_env(), sbom_bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "github-output").read_text() == "path=sbom\n"
    assert sorted(path.name for path in (uv_project.path / "sbom").iterdir()) == [
        "demo.cdx.json"
    ]
    document = bom(uv_project.path / "sbom/demo.cdx.json")
    root = document["metadata"]["component"]
    # The project is the root component, with the tag's version: it's dynamic here.
    assert (root["name"], root["version"], root["type"]) == ("demo", "1.2.0", "library")
    assert document.get("components", []) == []
    # The timestamp is the commit's, not the run's.
    commit_time = int(uv_project.git("log", "-1", "--format=%ct"))
    timestamp = datetime.fromisoformat(document["metadata"]["timestamp"])
    assert timestamp.timestamp() == commit_time
    (args,) = (tmp_path / "uvx-args").read_text().splitlines()
    assert args.startswith("--from cyclonedx-bom==8.0.1 cyclonedx-py environment ")
    assert args.endswith(
        " --pyproject pyproject.toml --mc-type library --output-reproducible"
        " --output-file sbom/demo.cdx.json"
    )


def test_sbom_of_each_flavour(
    uv_project: Repo, sbom_bin_dir: Path, tmp_path: Path
) -> None:
    env = sbom_env("core\n\n  viz --extra viz\n", COMPONENT_TYPE="application")
    env |= {"SBOM_PATH": "out/sboms", "VERSION": "1.2.0.post1"}
    result = run_action("sbom", env, sbom_bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    out = uv_project.path / "out/sboms"
    assert sorted(path.name for path in out.iterdir()) == [
        "demo-core.cdx.json",
        "demo-viz.cdx.json",
    ]
    root = bom(out / "demo-viz.cdx.json")["metadata"]["component"]
    assert (root["version"], root["type"]) == ("1.2.0.post1", "application")
    assert "--mc-type application" in (tmp_path / "uvx-args").read_text()


def test_sbom_keeps_a_static_version(
    uv_project: Repo, sbom_bin_dir: Path, tmp_path: Path
) -> None:
    (uv_project.path / "pyproject.toml").write_text(DEMO_PYPROJECT, encoding="utf-8")
    env = sbom_env(GITHUB_REF_TYPE="branch", GITHUB_REF_NAME="main")
    result = run_action("sbom", env, sbom_bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    root = bom(uv_project.path / "sbom/demo.cdx.json")["metadata"]["component"]
    assert root["version"] == "1.1.0"


@pytest.mark.parametrize(
    ("flavours", "error"),
    [
        ("core\nviz;rm --extra viz", "::error::'viz;rm' is not a flavour name"),
        ("core\ncore --extra viz", "::error::The flavour 'core' is listed twice."),
    ],
)
def test_sbom_refuses_bad_flavours(
    uv_project: Repo, sbom_bin_dir: Path, tmp_path: Path, flavours: str, error: str
) -> None:
    result = run_action("sbom", sbom_env(flavours), sbom_bin_dir, tmp_path)
    assert result.returncode == 1
    assert error in result.stdout
    assert not (uv_project.path / "sbom/demo-viz.cdx.json").exists()


@pytest.mark.usefixtures("repo")
def test_sbom_needs_a_uv_project(sbom_bin_dir: Path, tmp_path: Path) -> None:
    result = run_action("sbom", sbom_env(), sbom_bin_dir, tmp_path)
    assert result.returncode == 1
    assert (
        "::error::The sbom action needs a uv project: pyproject.toml and uv.lock."
        in result.stdout
    )


# license-check

PRESETS = ROOT / "actions/license-check/policies"


def test_license_check_installs_the_pinned_grant() -> None:
    install, _ = steps("license-check")
    assert install["env"] == {"GRANT_VERSION": "0.7.1"}
    hashes = re.findall(r"platform=(\w+) sha=([0-9a-f]{64}) ;;", install["run"])
    assert sorted(platform for platform, _ in hashes) == [
        "darwin_amd64",
        "darwin_arm64",
        "linux_amd64",
        "linux_arm64",
    ]
    assert 'echo "$sha  $dir/$archive" | sha256sum -c -' in install["run"]


def test_presets_leave_ignore_packages_to_the_repository() -> None:
    presets = sorted(PRESETS.glob("*.yaml"))
    assert [path.stem for path in presets] == ["open-source"]
    for path in presets:
        policy = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "ignore-packages" not in policy
        assert policy["require-license"] is True
        assert "Apache-2.0" in policy["allow"]


@pytest.fixture
def grant_bin_dir(bin_dir: Path, tmp_path: Path) -> Path:
    """Add a stand-in for grant that records its arguments and policy, and passes."""
    grant = bin_dir / "grant"
    grant.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$@" > "{tmp_path}/grant-args"\n'
        f'cp "$3" "{tmp_path}/grant-policy.yaml"\n'
        'exit "${GRANT_EXIT:-0}"\n',
        encoding="utf-8",
    )
    grant.chmod(0o755)
    return bin_dir


def check_env(**extra: str) -> dict[str, str]:
    """Return the env: of the license check step."""
    return {
        "PATTERNS": "sbom/*.cdx.json",
        "POLICY": "open-source",
        "IGNORE": "",
        "IGNORE_FILE": "",
        "PRESETS": str(PRESETS),
    } | extra


@pytest.fixture
def sboms(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return a working directory with two SBOMs in sbom/."""
    work = tmp_path / "work"
    (work / "sbom").mkdir(parents=True)
    for name in ("demo-core.cdx.json", "demo-viz.cdx.json"):
        (work / "sbom" / name).write_text("{}", encoding="utf-8")
    monkeypatch.chdir(work)
    return work


@pytest.mark.usefixtures("sboms")
def test_license_check_with_a_preset(grant_bin_dir: Path, tmp_path: Path) -> None:
    ignore = (
        "\n  block2: GPL-3.0-only, run as a separate program, never imported\n"
        "PySide6_Essentials:LGPL-3.0-only OR GPL: we take the LGPL\n"
    )
    result = run_action(
        "license-check", check_env(IGNORE=ignore), grant_bin_dir, tmp_path
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "grant-args").read_text().splitlines() == [
        "check",
        "--config",
        str(tmp_path / "runner-temp/license-policy.yaml"),
        "--disable-file-search",
        "sbom/demo-core.cdx.json",
        "sbom/demo-viz.cdx.json",
    ]
    policy = (tmp_path / "grant-policy.yaml").read_text()
    assert policy.startswith((PRESETS / "open-source.yaml").read_text())
    assert yaml.safe_load(policy)["ignore-packages"] == ["block2", "PySide6_Essentials"]
    assert (
        "Ignoring block2: GPL-3.0-only, run as a separate program, never imported"
        in result.stdout
    )
    assert "Ignoring PySide6_Essentials: LGPL-3.0-only OR GPL: we take the LGPL" in (
        result.stdout
    )
    assert "::group::License policy (open-source)" in result.stdout


def test_license_check_with_an_ignore_file(
    sboms: Path, grant_bin_dir: Path, tmp_path: Path
) -> None:
    exceptions = sboms / ".github/license-exceptions.yaml"
    exceptions.parent.mkdir()
    exceptions.write_text(
        "# Reviewed by legal.\nblock2: run as a separate program\n\n"
        "  # shiboken6 goes with PySide6\nshiboken6: we take the LGPL-3.0 option",
        encoding="utf-8",
    )
    env = check_env(IGNORE="numpy: a reason", IGNORE_FILE=str(exceptions))
    result = run_action("license-check", env, grant_bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    policy = yaml.safe_load((tmp_path / "grant-policy.yaml").read_text())
    assert policy["ignore-packages"] == ["numpy", "block2", "shiboken6"]
    # The file is a YAML mapping as well.
    assert list(yaml.safe_load(exceptions.read_text())) == ["block2", "shiboken6"]


def test_license_check_with_the_repository_policy(
    sboms: Path, grant_bin_dir: Path, tmp_path: Path
) -> None:
    (sboms / ".grant.yaml").write_text("allow: [MIT]\n", encoding="utf-8")
    env = check_env(POLICY=".grant.yaml", PATTERNS="sbom/demo-core.cdx.json")
    result = run_action("license-check", env, grant_bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    args = (tmp_path / "grant-args").read_text().splitlines()
    assert args[1:3] == ["--config", ".grant.yaml"]
    assert args[4:] == ["sbom/demo-core.cdx.json"]


@pytest.mark.usefixtures("sboms")
def test_license_check_fails_with_grant(grant_bin_dir: Path, tmp_path: Path) -> None:
    env = check_env(GRANT_EXIT="1")
    result = run_action("license-check", env, grant_bin_dir, tmp_path)
    assert result.returncode == 1
    assert "::error::A package's license is outside the policy open-source" in (
        result.stdout
    )


@pytest.mark.usefixtures("sboms")
@pytest.mark.parametrize(
    ("env", "error"),
    [
        ({"PATTERNS": "dist/*.json"}, "::error::No SBOMs match 'dist/*.json'."),
        ({"PATTERNS": "\n"}, "::error::No SBOMs to check: set sboms."),
        (
            {"POLICY": "proprietary"},
            (
                "::error::'proprietary' is not a preset (open-source) or a file in"
                " the repository."
            ),
        ),
        ({"POLICY": "../open-source"}, "::error::The policy ../open-source doesn't"),
        (
            {"POLICY": "policies/open-source.yaml"},
            "::error::The policy policies/open-source.yaml doesn't exist.",
        ),
        ({"IGNORE": "block2"}, "::error::'block2' needs its reason"),
        (
            {"IGNORE_FILE": "exceptions.yaml"},
            "::error::The ignore-packages-file exceptions.yaml doesn't exist.",
        ),
        ({"IGNORE": "block2:  "}, "::error::'block2:  ' needs its reason"),
        ({"IGNORE": 'a"b: quoted'}, "::error::'a\"b' is not a package name."),
    ],
)
def test_license_check_refuses(
    grant_bin_dir: Path, tmp_path: Path, env: dict[str, str], error: str
) -> None:
    result = run_action("license-check", check_env(**env), grant_bin_dir, tmp_path)
    assert result.returncode == 1
    assert error in result.stdout
    assert not (tmp_path / "grant-args").exists()


def test_license_check_keeps_ignores_in_the_repository_policy(
    sboms: Path, grant_bin_dir: Path, tmp_path: Path
) -> None:
    (sboms / ".grant.yaml").write_text("allow: [MIT]\n", encoding="utf-8")
    env = check_env(POLICY=".grant.yaml", IGNORE="block2: a reason")
    result = run_action("license-check", env, grant_bin_dir, tmp_path)
    assert result.returncode == 1
    assert (
        "::error::ignore-packages only goes with a preset: list them in .grant.yaml."
        in result.stdout
    )


def cyclonedx(*components: tuple[str, str]) -> str:
    """Return a CycloneDX SBOM of demo with COMPONENTS (name, SPDX identifier)."""
    return json.dumps(
        {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "component": {
                    "type": "library",
                    "bom-ref": "demo",
                    "name": "demo",
                    "version": "1.0.0",
                    "licenses": [{"license": {"id": "Apache-2.0"}}],
                }
            },
            "components": [
                {
                    "type": "library",
                    "bom-ref": f"{name}==1.0",
                    "name": name,
                    "version": "1.0",
                    "purl": f"pkg:pypi/{name}@1.0",
                    "licenses": [{"license": {"id": spdx}}],
                }
                for name, spdx in components
            ],
        }
    )


@pytest.mark.skipif(shutil.which("grant") is None, reason="grant is not installed")
def test_license_check_with_grant(sboms: Path, bin_dir: Path, tmp_path: Path) -> None:
    sbom = sboms / "sbom/demo-core.cdx.json"
    sbom.write_text(cyclonedx(("requests", "Apache-2.0")), encoding="utf-8")
    (sboms / "sbom/demo-viz.cdx.json").write_text(
        cyclonedx(("block2", "GPL-3.0-only"), ("idna", "BSD-3-Clause")),
        encoding="utf-8",
    )
    result = run_action("license-check", check_env(), bin_dir, tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "block2" in result.stdout
    env = check_env(IGNORE="block2: run as a separate program")
    result = run_action("license-check", env, bin_dir, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr

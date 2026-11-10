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

    from conftest import Repo

ACTIONS = sorted((ROOT / "actions").glob("*/action.yml"))


def steps(action: str) -> list[dict[str, Any]]:
    """Return the steps of ACTION."""
    metadata = yaml.safe_load((ROOT / "actions" / action / "action.yml").read_text())
    return metadata["runs"]["steps"]


def script(action: str) -> str:
    """Return the run: script of ACTION, which has exactly one."""
    (step,) = [step for step in steps(action) if "run" in step]
    assert step["shell"] == "bash"
    return step["run"]


@pytest.fixture
def bin_dir(tmp_path: Path) -> Path:
    """Return a directory, first on PATH, with a stand-in for gh."""
    directory = tmp_path / "bin"
    directory.mkdir()
    assert shutil.which("git-cliff"), (
        "git-cliff is missing: run the tests with `just test`"
    )
    stand_ins = {"gh": f'printf "%s\\n" "$@" > "{tmp_path}/gh-args"'}
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
dynamic = ["version"]
license = "Apache-2.0"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
viz = []
"""


@pytest.fixture
def uv_project(repo: Repo) -> Repo:
    """Return a uv project without dependencies, locked offline and committed."""
    (repo.path / "pyproject.toml").write_text(DEMO_PYPROJECT, encoding="utf-8")
    subprocess.run(
        ["uv", "lock", "--offline", "--quiet"],
        cwd=repo.path,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        check=True,
    )
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
    pyproject = uv_project.path / "pyproject.toml"
    pyproject.write_text(
        DEMO_PYPROJECT.replace('dynamic = ["version"]', 'version = "1.1.0"'),
        encoding="utf-8",
    )
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

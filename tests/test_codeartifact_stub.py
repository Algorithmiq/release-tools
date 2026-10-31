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

"""Tests of the upload step of examples/stubs/deploy-codeartifact.yml.

The step runs in bash with stand-ins for `aws` and `uv` that record what they get.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tomllib
from typing import TYPE_CHECKING, Any

import pytest
import yaml
from conftest import ROOT

if TYPE_CHECKING:
    from pathlib import Path

STUB = ROOT / "examples" / "stubs" / "deploy-codeartifact.yml"
TOKEN = "token-from-codeartifact"  # noqa: S105 (a stand-in's output)
ENDPOINT = "https://example.d.codeartifact.test/pypi/packages/"


def upload_job() -> dict[str, Any]:
    """Return the upload job of the stub."""
    return yaml.safe_load(STUB.read_text(encoding="utf-8"))["jobs"][
        "upload_codeartifact"
    ]


def upload_step() -> dict[str, Any]:
    """Return the step of the upload job that runs uv publish."""
    (step,) = [s for s in upload_job()["steps"] if "uv publish" in s.get("run", "")]
    return step


@pytest.fixture
def uploaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Run the upload step with stand-ins; return what uv got and the step's output."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "uv.json"
    stand_ins = {
        # aws codeartifact get-authorization-token | get-repository-endpoint ...
        "aws": (
            f'echo "$@" >> "{tmp_path}/aws-args"\n'
            f'case "$2" in get-authorization-token) echo "{TOKEN}" ;;'
            f' get-repository-endpoint) echo "{ENDPOINT}" ;; *) exit 1 ;; esac'
        ),
        # Record the arguments, the credentials and the config file uv was given.
        "uv": (
            'config=""; prev=""\n'
            'for a in "$@"; do\n'
            '  [ "$prev" = --config-file ] && config="$a"; prev="$a"\n'
            "done\n"
            f'python3 -c \'import json, os, sys; json.dump({{"args": sys.argv[2:], '
            '"username": os.environ.get("UV_INDEX_CODEARTIFACT_USERNAME"), '
            '"password": os.environ.get("UV_INDEX_CODEARTIFACT_PASSWORD"), '
            '"config": open(sys.argv[1]).read()}, '
            f'open("{record}", "w"))\' "$config" "$@"'
        ),
    }
    for name, body in stand_ins.items():
        path = bin_dir / name
        path.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    work = tmp_path / "work"
    (work / "dist").mkdir(parents=True)
    for name in ("demo-1.0.0-py3-none-any.whl", "demo-1.0.0.tar.gz"):
        (work / "dist" / name).write_text("", encoding="utf-8")
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    monkeypatch.chdir(work)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": str(runner_temp),
        "DOMAIN": "example",
        "DOMAIN_OWNER": "owner",
        "REPOSITORY": "packages",
    }
    result = subprocess.run(
        [
            "bash",
            "--noprofile",
            "--norc",
            "-eo",
            "pipefail",
            "-c",
            upload_step()["run"],
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return {**json.loads(record.read_text(encoding="utf-8")), "stdout": result.stdout}


def test_uploads_every_distribution_to_the_index_with_uv(
    uploaded: dict[str, Any],
) -> None:
    args = uploaded["args"]
    assert args[0] == "publish"
    assert args[args.index("--index") + 1] == "codeartifact"
    assert args[args.index("--trusted-publishing") + 1] == "never"
    assert "--no-attestations" in args
    assert sorted(a for a in args if a.startswith("dist/")) == [
        "dist/demo-1.0.0-py3-none-any.whl",
        "dist/demo-1.0.0.tar.gz",
    ]


def test_the_index_lets_uv_skip_files_already_uploaded(
    uploaded: dict[str, Any],
) -> None:
    # With --index, uv reads the index's url, with the index's credentials, and skips
    # files that are already there: a failed run can be re-run.
    (index,) = tomllib.loads(uploaded["config"])["index"]
    assert index["name"] == "codeartifact"
    assert index["publish-url"] == ENDPOINT
    assert index["url"] == f"{ENDPOINT}simple/"
    assert uploaded["username"] == "aws"
    assert uploaded["password"] == TOKEN


def test_the_token_is_masked_and_never_an_argument(uploaded: dict[str, Any]) -> None:
    assert f"::add-mask::{TOKEN}" in uploaded["stdout"]
    assert not any(TOKEN in arg for arg in uploaded["args"])
    assert TOKEN not in uploaded["config"]


def test_the_upload_job_attests_the_distributions() -> None:
    job = upload_job()
    assert job["permissions"]["attestations"] == "write"
    assert job["permissions"]["id-token"] == "write"
    (attest,) = [
        s
        for s in job["steps"]
        if s.get("uses", "").startswith("actions/attest-build-provenance@")
    ]
    assert attest["with"]["subject-path"] == "dist/*"


def test_the_upload_step_passes_shellcheck() -> None:
    run = upload_step()["run"]
    # Values reach the script through env:, never through ${{ }} in the script itself.
    assert "${{" not in run
    result = subprocess.run(
        ["shellcheck", "--shell=bash", "-"],
        input=run,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout

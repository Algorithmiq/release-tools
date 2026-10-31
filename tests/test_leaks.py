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

"""Tests that no tracked file identifies the AWS account or a non-public repository.

release-tools is public. These checks need no access to the organisation: they look for
AWS identifiers, and for `Algorithmiq/<name>` references outside an allowlist of public
names. The names of the organisation's non-public repositories, which only members can
list, are checked before each push by scripts/check_internal_names.py.
"""

from __future__ import annotations

import re
import subprocess
from typing import TYPE_CHECKING

import pytest
from conftest import ROOT

if TYPE_CHECKING:
    from pathlib import Path

# A 12-digit AWS account ID on its own, an ARN, or an AWS endpoint.
# Written so that this file doesn't match itself.
AWS_IDENTIFIERS = re.compile(r"(?<![\w.])\d{12}(?![\w.])|arn:aws[:]|amazonaws\.com")
# `Algorithmiq/<name>` in any case (GHCR is lower case), except in the organisation's
# settings URLs and API paths.
REPOSITORY_REFERENCE = re.compile(
    r"(?<!organizations/)(?<!orgs/)\bAlgorithmiq/([\w.-]+)", re.IGNORECASE
)
# Public repositories, and the made-up names the tests use.
PUBLIC_REPOSITORIES = {"release-tools", "demo", "example"}


def tracked_files() -> list[Path]:
    """Return the files git tracks here, except the lock file."""
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return [
        ROOT / name for name in result.stdout.split("\0") if name not in {"", "uv.lock"}
    ]


def referenced_repositories(text: str) -> set[str]:
    """Return the repository names that TEXT references as `Algorithmiq/<name>`."""
    return {
        name.removesuffix(".git").rstrip(".")
        for name in REPOSITORY_REFERENCE.findall(text)
    }


@pytest.mark.parametrize(
    "text",
    [
        "arn:" + "aws:iam::<account>:role/uploader",
        "--domain-owner 123456" + "789012 --region",
        "https://example.d.codeartifact.eu-west-1.amazonaws" + ".com/pypi/simple/",
    ],
)
def test_aws_identifiers_are_found(text: str) -> None:
    assert AWS_IDENTIFIERS.search(text)


@pytest.mark.parametrize(
    "text",
    ["sha256:0123456789012abc", "12345678901", "1234567890123", "v1.2.0", "2026-10-30"],
)
def test_other_numbers_are_not_aws_identifiers(text: str) -> None:
    assert not AWS_IDENTIFIERS.search(text)


def test_repository_references() -> None:
    text = (
        "https://github.com/Algorithmiq"
        "/secret-solver/pull/3, "
        "ghcr.io/algorithmiq"
        "/lab:latest, "
        "https://github.com/Algorithmiq/release-tools.git, "
        "uses Algorithmiq/release-tools/actions/draft-release@v1.2.0 and "
        "See https://github.com/organizations/Algorithmiq/settings/apps/new, "
        "gh api orgs/Algorithmiq/installations and "
        "REPO=Algorithmiq/<name>."
    )
    assert referenced_repositories(text) == {"secret-solver", "lab", "release-tools"}


def test_no_tracked_file_has_an_aws_identifier() -> None:
    found = [
        f"{path.relative_to(ROOT)}:{number}"
        for path in tracked_files()
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        )
        if AWS_IDENTIFIERS.search(line)
    ]
    assert found == []


def test_tracked_files_reference_only_public_repositories() -> None:
    found = {
        f"{path.relative_to(ROOT)}: Algorithmiq/{name}"
        for path in tracked_files()
        for name in referenced_repositories(
            path.read_text(encoding="utf-8", errors="replace")
        )
        if name not in PUBLIC_REPOSITORIES
    }
    assert found == set()

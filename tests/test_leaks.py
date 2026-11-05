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

import pytest
from conftest import ROOT

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


@pytest.fixture(scope="module")
def tracked_texts() -> dict[str, str]:
    """Return the text of each file git tracks here, by path, except the lock file.

    A tracked file deleted in the working tree, and not yet staged, is left out.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return {
        name: (ROOT / name).read_text(encoding="utf-8", errors="replace")
        for name in result.stdout.split("\0")
        if name not in {"", "uv.lock"} and (ROOT / name).is_file()
    }


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


def test_no_tracked_file_has_an_aws_identifier(tracked_texts: dict[str, str]) -> None:
    found = [
        f"{path}:{number}"
        for path, text in tracked_texts.items()
        for number, line in enumerate(text.splitlines(), start=1)
        if AWS_IDENTIFIERS.search(line)
    ]
    assert found == []


def test_tracked_files_reference_only_public_repositories(
    tracked_texts: dict[str, str],
) -> None:
    found = {
        f"{path}: Algorithmiq/{name}"
        for path, text in tracked_texts.items()
        for name in referenced_repositories(text)
        if name not in PUBLIC_REPOSITORIES
    }
    assert found == set()

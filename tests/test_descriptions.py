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

"""Tests of release/descriptions.py, with a fake GitHub API behind `gh`."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest
from conftest import ROOT

from release.descriptions import BATCH_SIZE, pr_descriptions

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import FakeGitHub

SHA = "a" * 40
WRAPPED_BODY = "## Migration\nwrapped\ntext"


def commit(number: int | None, sha: str = SHA, body: str = WRAPPED_BODY) -> dict:
    """Return a commit of git-cliff's context for the squash commit of PR NUMBER."""
    suffix = f" (#{number})" if number else ""
    return {
        "id": sha,
        "message": f"add x{suffix}",
        "raw_message": f"feat: add x{suffix}\n\n{body}",
    }


def context(*commits: dict) -> list[dict[str, Any]]:
    """Return a context with one unreleased release of COMMITS."""
    return [{"version": None, "commits": list(commits)}]


def raw_messages(result: list[dict[str, Any]]) -> list[str]:
    """Return the `raw_message` of every commit of RESULT."""
    return [c["raw_message"] for release in result for c in release["commits"]]


def test_description_replaces_the_body(github: FakeGitHub) -> None:
    description = "## Summary\n\nx\n\n## Migration\n\n    indented\n\n```py\n  a\n```\n"
    github.add(12, description, SHA)
    result = pr_descriptions(context(commit(12)))
    assert raw_messages(result) == [f"feat: add x (#12)\n\n{description.strip()}"]
    assert github.calls == [[12]]


def test_carriage_returns_and_comments_are_stripped(github: FakeGitHub) -> None:
    github.add(
        12,
        "\r\n## Migration\r\n<!-- Required for\r\n  breaking changes -->\r\nUse y.\r\n"
        "<!-- another --> And z.\r\n\r\n",
        SHA,
    )
    result = pr_descriptions(context(commit(12)))
    assert raw_messages(result) == [
        "feat: add x (#12)\n\n## Migration\n\nUse y.\n And z."
    ]


def test_an_empty_description_leaves_only_the_title(github: FakeGitHub) -> None:
    github.add(12, "<!-- only the template's comment -->\r\n", SHA)
    assert raw_messages(pr_descriptions(context(commit(12)))) == ["feat: add x (#12)"]


def test_a_commit_without_a_pr_number_keeps_its_body(github: FakeGitHub) -> None:
    original = context(commit(None))
    assert raw_messages(pr_descriptions(original)) == [f"feat: add x\n\n{WRAPPED_BODY}"]
    assert github.calls == []


def test_only_the_suffix_of_the_message_is_a_pr_number(github: FakeGitHub) -> None:
    mentions = commit(None)
    mentions["message"] = "fix #3 and (#4) in names"
    pr_descriptions(context(mentions))
    assert github.calls == []


def test_nothing_is_done_without_the_repository(
    github: FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY")
    github.add(12, "The description", SHA)
    result = pr_descriptions(context(commit(12)))
    assert raw_messages(result) == [f"feat: add x (#12)\n\n{WRAPPED_BODY}"]
    assert github.calls == []


@pytest.mark.parametrize(
    ("oid", "merged"),
    [("b" * 40, True), (SHA, False), (None, True)],
    ids=["other-merge-commit", "not-merged", "no-merge-commit"],
)
def test_a_pr_that_is_not_the_commit_keeps_the_body(
    github: FakeGitHub,
    capsys: pytest.CaptureFixture[str],
    oid: str | None,
    merged: bool,  # noqa: FBT001
) -> None:
    # A commit cherry-picked by hand keeps the title and number of the original.
    github.add(12, "The description", oid or "", merged=merged)
    result = pr_descriptions(context(commit(12)))
    assert raw_messages(result) == [f"feat: add x (#12)\n\n{WRAPPED_BODY}"]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "::warning::PR #12 is not the merge of commit aaaaaaa. The changelog"
        " uses the commit's own message.\n"
    )


def test_a_missing_pr_keeps_the_body_and_the_others_are_replaced(
    github: FakeGitHub, capsys: pytest.CaptureFixture[str]
) -> None:
    # gh exits with status 1 when a PR is not found, with the rest in the data.
    github.add(13, "Found", "c" * 40)
    result = pr_descriptions(context(commit(12), commit(13, "c" * 40)))
    assert raw_messages(result) == [
        f"feat: add x (#12)\n\n{WRAPPED_BODY}",
        "feat: add x (#13)\n\nFound",
    ]
    assert github.calls == [[12, 13]]
    assert capsys.readouterr().err == (
        "::warning::PR #12 of commit aaaaaaa was not found. The changelog"
        " uses the commit's own message.\n"
    )


def test_an_api_failure_keeps_the_bodies_and_warns(
    github: FakeGitHub, capsys: pytest.CaptureFixture[str]
) -> None:
    github.add(12, "The description", SHA)
    github.fail("API rate limit exceeded")
    result = pr_descriptions(context(commit(12), commit(13, "b" * 40)))
    assert raw_messages(result) == [
        f"feat: add x (#12)\n\n{WRAPPED_BODY}",
        f"feat: add x (#13)\n\n{WRAPPED_BODY}",
    ]
    tail = (
        " rate limit exceeded (HTTP 403). The changelog uses the commit's own message."
    )
    head = "::warning::Could not read the description of PR #"
    assert capsys.readouterr().err.splitlines() == [
        f"{head}12 for commit aaaaaaa: gh: API{tail}",
        f"{head}13 for commit bbbbbbb: gh: API{tail}",
    ]


def test_missing_gh_keeps_the_bodies_and_warns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("GITHUB_REPOSITORY", "Algorithmiq/example")
    result = pr_descriptions(context(commit(12)))
    assert raw_messages(result) == [f"feat: add x (#12)\n\n{WRAPPED_BODY}"]
    assert "::warning::Could not read the description of PR #12 for commit aaaaaaa" in (
        capsys.readouterr().err
    )


def test_queries_have_at_most_100_pull_requests(github: FakeGitHub) -> None:
    count = 2 * BATCH_SIZE + 50
    commits = []
    for number in range(1, count + 1):
        sha = f"{number:040x}"
        github.add(number, f"Description {number}", sha)
        commits.append(commit(number, sha))
    result = pr_descriptions(context(*commits))
    assert [len(call) for call in github.calls] == [100, 100, 50]
    assert (
        raw_messages(result)[count - 1]
        == f"feat: add x (#{count})\n\nDescription {count}"
    )
    assert all("Description" in message for message in raw_messages(result))


def test_a_pr_is_asked_once_and_every_release_is_read(github: FakeGitHub) -> None:
    github.add(12, "Once", SHA)
    github.add(13, "Other", "b" * 40)
    unreleased = {"version": "v1", "commits": [commit(12, SHA)]}
    older = {"version": "v0", "commits": [commit(12, SHA), commit(13, "b" * 40)]}
    result = pr_descriptions([unreleased, older])
    assert github.calls == [[12, 13]]
    assert raw_messages(result)[0] == "feat: add x (#12)\n\nOnce"
    assert raw_messages(result)[2] == "feat: add x (#13)\n\nOther"


def test_the_command_filters_the_context(github: FakeGitHub) -> None:
    github.add(12, "With é and 💥", SHA)
    result = subprocess.run(
        [sys.executable, str(ROOT / "release"), "pr-descriptions"],
        input=json.dumps(context(commit(12))),
        capture_output=True,
        text=True,
        check=True,
    )
    assert raw_messages(json.loads(result.stdout)) == [
        "feat: add x (#12)\n\nWith é and 💥"
    ]
    assert result.stderr == ""

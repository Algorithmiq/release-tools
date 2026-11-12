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

"""Changelog entries from PR descriptions instead of squash commit bodies.

GitHub's web UI hard-wraps a squash commit's body at 72 columns, which breaks the code
blocks and lists of a Migration section. The PR description is intact, so the changelog
context of git-cliff (`git cliff --context`) gets each commit's description in place of
its body, and `git cliff --from-context` renders it with the same cliff.toml.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Any

# The context of git-cliff, as parsed from JSON: a list of releases with their commits.
Context = list[dict[str, Any]]

# The PR number that GitHub appends to the title of a squash commit. cliff.toml turns
# the same suffix of the commit message into the link to the PR.
PR_SUFFIX = re.compile(r"\(#(\d+)\)\s*$")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
# GraphQL aliases are bounded by the node limit of the API, far above this.
BATCH_SIZE = 100


def warn(message: str) -> None:
    """Report MESSAGE as a GitHub Actions warning, on standard error.

    Standard output carries the context when the command runs as a filter.
    """
    print(f"::warning::{message}", file=sys.stderr)  # noqa: T201


def clean(description: str) -> str:
    """Return the PR DESCRIPTION without carriage returns and HTML comments, trimmed.

    The "Migration notes" check of pr-checks.yml reads the description the same way.
    """
    return HTML_COMMENT.sub("", description.replace("\r", "")).strip()


def query(numbers: list[int]) -> str:
    """Return the GraphQL query for the pull requests NUMBERS of a repository."""
    fields = " ".join(
        f"pr{n}: pullRequest(number: {n}) {{ body merged mergeCommit {{ oid }} }}"
        for n in numbers
    )
    return (
        "query($owner: String!, $name: String!) "
        f"{{ repository(owner: $owner, name: $name) {{ {fields} }} }}"
    )


def fetch(repository: str, numbers: list[int]) -> tuple[dict[int, dict[str, Any]], str]:
    """Return the pull requests NUMBERS of REPOSITORY (owner/name) that were found.

    The second value says why none of them could be read: it is empty if the API
    answered. A number that is missing from the first value was not found. `gh api
    graphql` exits with status 1 when the answer has errors, even if it also has data
    (a number that is not a pull request), so the data decides, not the status.
    """
    owner, name = repository.split("/", 1)
    try:
        result = subprocess.run(  # noqa: S603 - fixed executable, arguments are ours
            [  # noqa: S607 - gh comes from PATH on every runner
                "gh",
                "api",
                "graphql",
                "-f",
                f"owner={owner}",
                "-f",
                f"name={name}",
                "-f",
                f"query={query(numbers)}",
            ],
            check=False,
            text=True,
            capture_output=True,
        )
    except OSError as error:
        return {}, str(error)
    try:
        found = json.loads(result.stdout)["data"]["repository"]
        return {n: found[f"pr{n}"] for n in numbers if found.get(f"pr{n}")}, ""
    except (ValueError, KeyError, TypeError, AttributeError):
        reason = result.stderr.strip() or result.stdout.strip() or "no answer"
        return {}, reason.splitlines()[0]


def accepted(pull_request: dict[str, Any], commit_id: str) -> bool:
    """Return whether PULL_REQUEST was merged as the commit COMMIT_ID."""
    merge_commit = pull_request.get("mergeCommit") or {}
    return pull_request.get("merged") is True and (
        str(merge_commit.get("oid", "")).lower() == commit_id.lower()
    )


def pr_descriptions(context: Context) -> Context:
    """Return CONTEXT with each commit's PR description in place of its body.

    For every commit whose message ends with `(#N)`, the commit's `raw_message` becomes
    its title (the first line), a blank line and the description of PR N, which
    cliff.toml reads the Migration section from. The description counts only if PR N is
    merged and its merge commit is that commit: a commit that was cherry-picked by hand
    keeps its own body. If GitHub can't be asked, or doesn't know PR N, the commit keeps
    its body and a warning names it and the PR. Nothing is done, and GitHub isn't asked,
    without GITHUB_REPOSITORY.
    """
    repository = os.environ.get("GITHUB_REPOSITORY")
    commits = [
        (commit, int(m[1]))
        for release in context
        for commit in release.get("commits", [])
        if repository and (m := PR_SUFFIX.search(commit.get("message") or ""))
    ]
    numbers = sorted({number for _, number in commits})
    found: dict[int, dict[str, Any]] = {}
    failed: dict[int, str] = {}
    for start in range(0, len(numbers), BATCH_SIZE):
        batch = numbers[start : start + BATCH_SIZE]
        # `repository` is set: commits is empty otherwise.
        answered, reason = fetch(repository or "", batch)
        found |= answered
        if reason:
            failed |= dict.fromkeys(batch, reason)
    for commit, number in commits:
        short = commit["id"][:7]
        if number in failed:
            warn(
                f"Could not read the description of PR #{number} for commit {short}: "
                f"{failed[number]}. The changelog uses the commit's own message."
            )
        elif number not in found:
            warn(
                f"PR #{number} of commit {short} was not found. The changelog uses "
                "the commit's own message."
            )
        elif not accepted(found[number], commit["id"]):
            warn(
                f"PR #{number} is not the merge of commit {short}. The changelog uses "
                "the commit's own message."
            )
        else:
            title = commit["raw_message"].split("\n", 1)[0]
            description = clean(found[number]["body"] or "")
            commit["raw_message"] = (
                f"{title}\n\n{description}" if description else title
            )
    return context


def filter_context() -> None:
    """Read git-cliff's context on standard input, write it with descriptions."""
    json.dump(pr_descriptions(json.load(sys.stdin.buffer)), sys.stdout)

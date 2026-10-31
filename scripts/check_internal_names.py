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

"""Refuse a push that names a non-public repository of the Algorithmiq organisation.

release-tools is public; the organisation's private and internal repositories must not
be named in it. prek runs this before each push (see prek.toml and `just hooks`), with
the pushed range in PRE_COMMIT_FROM_REF and PRE_COMMIT_TO_REF. It lists the non-public
repositories with the GitHub CLI, so no list is ever stored here, and looks for their
names, as whole words in any case, in the lines the push adds, the paths it adds or
changes, and its commit messages.

A name that is fine to publish goes on its own line in .git/info/allowed-names, which is
never committed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ORGANISATION = "Algorithmiq"
# AEGISS is going public and is named in the history already; .github is also a path.
ALWAYS_ALLOWED = {"aegiss", ".github"}
NO_COMMIT = "0" * 40


def git(*args: str) -> str:
    """Run git and return its standard output."""
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout


def non_public_repositories() -> set[str]:
    """Return the organisation's non-public repositories; none if gh can't list them."""
    try:
        listing = subprocess.run(
            [
                "gh",
                "repo",
                "list",
                ORGANISATION,
                "--limit",
                "10000",
                "--json",
                "name,visibility",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return set()
    return {
        repo["name"] for repo in json.loads(listing) if repo["visibility"] != "PUBLIC"
    }


def allowed_names() -> set[str]:
    """Return the lower-case names that may be pushed."""
    path = Path(git("rev-parse", "--git-path", "info/allowed-names").strip())
    local = path.read_text(encoding="utf-8").split() if path.exists() else []
    return ALWAYS_ALLOWED | {name.lower() for name in local}


def pushed_range() -> str:
    """Return the pushed revisions as FROM..TO."""
    to_ref = os.environ.get("PRE_COMMIT_TO_REF") or "HEAD"
    from_ref = os.environ.get("PRE_COMMIT_FROM_REF", "")
    if not from_ref or from_ref == NO_COMMIT:
        from_ref = git("merge-base", "origin/main", to_ref).strip()
    return f"{from_ref}..{to_ref}"


def pushed_text(revisions: str) -> list[tuple[str, str]]:
    """Return (where, text) for every line, path and commit message REVISIONS add.

    The paths count on their own: a pure rename adds no lines.
    """
    found: list[tuple[str, str]] = []
    path = ""
    for line in git("diff", "--unified=0", "--no-color", revisions).splitlines():
        if line.startswith("+++ "):
            path = line.removeprefix("+++ ").removeprefix("b/")
        elif line.startswith("+"):
            found.append((path, line[1:]))
    found.extend(
        (name, name) for name in git("diff", "--name-only", revisions).splitlines()
    )
    found.extend(
        (f"commit {sha[:10]}", git("log", "-1", "--format=%B", sha))
        for sha in git("rev-list", revisions).split()
    )
    return found


def leaks(texts: list[tuple[str, str]], names: set[str]) -> list[str]:
    """Return "where: name" for every whole-word occurrence of NAMES in TEXTS."""
    if not names:
        return []
    alternatives = "|".join(map(re.escape, sorted(names, key=len, reverse=True)))
    pattern = re.compile(rf"(?<![\w-])({alternatives})(?![\w-])", re.IGNORECASE)
    return [f"{where}: {m[1]}" for where, text in texts for m in pattern.finditer(text)]


def main() -> int:
    """Check the push; return the exit status."""
    names = non_public_repositories()
    if not names:
        print(
            "check-internal-names: gh can't list the organisation's non-public "
            "repositories; skipped.",
            file=sys.stderr,
        )
        return 0
    allowed = allowed_names()
    found = leaks(
        pushed_text(pushed_range()), {n for n in names if n.lower() not in allowed}
    )
    for item in found:
        print(item, file=sys.stderr)
    if found:
        print(
            "These name non-public repositories of the organisation, and release-tools "
            "is public. Remove them, or add a name that is fine to publish to "
            ".git/info/allowed-names.",
            file=sys.stderr,
        )
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())

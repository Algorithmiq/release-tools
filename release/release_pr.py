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

"""The release PR of a release branch: open it, or update it and its draft state.

The branch release-pr/X.Y is the release branch's HEAD plus one commit that sets the
version files and adds the new section to CHANGELOG.md, which starts from main's.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from release.tagging import set_version, version_files

# cliff.toml sits next to the package, at the commit the caller pinned.
CLIFF_CONFIG = Path(__file__).resolve().parent.parent / "cliff.toml"


def run(*args: str) -> str:
    """Run a command (git cliff, gh) and return its standard output (unstripped).

    Stderr is inherited, so errors from gh, git push and git cliff reach the job log.
    """
    result = subprocess.run(  # noqa: S603 - fixed executables, arguments are ours
        list(args),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout


def body(version: str, base: str, stage: str, notes: str) -> str:
    """Return the description of the release PR for VERSION into BASE."""
    lines = []
    if stage == "beta":
        lines += [
            (
                f"Draft while v{version} is in beta. To move to release candidates, run"
                " Release with stage `rc`."
            ),
            "",
        ]
    lines += [
        f"Merging this PR releases **v{version}**.",
        "",
        f"It is updated automatically whenever a change lands on `{base}`.",
    ]
    if not version.endswith(".0"):
        lines += [
            (
                f"Every fix backported to `{base}` is added to this PR. Merge it "
                "when the fixes"
            ),
            "should ship. Patch releases have no release candidates.",
        ]
    lines += [
        "Wording fixes to `CHANGELOG.md` can be pushed to this PR, but make them",
        "just before merging: the next update overwrites them.",
        "",
        "---",
        "",
    ]
    return "\n".join(lines) + "\n" + notes


def release_pr(series: str, version: str, stage: str, head: str) -> None:
    """Open or update the release PR of release/SERIES, which releases VERSION.

    STAGE is beta, rc or released: the PR is a draft during beta. HEAD is the commit
    of the release branch to build the PR on.
    """
    base = f"release/{series}"
    pr_branch = f"release-pr/{series}"
    title = f"chore: release v{version}"
    run("git", "checkout", "--quiet", "-B", pr_branch, head)

    set_version(version)
    # Start from main's CHANGELOG.md: it has every release so far, including the patch
    # releases of the previous line made after this branch was created.
    changelog = Path("CHANGELOG.md")
    try:
        # Use run() to get the file byte for byte, without stripping.
        changelog.write_text(
            run("git", "show", "origin/main:CHANGELOG.md"), encoding="utf-8"
        )
    except subprocess.CalledProcessError:
        changelog.touch()
    cliff = ["git", "cliff", "--config", str(CLIFF_CONFIG), "--unreleased"]
    cliff += ["--tag", f"v{version}"]
    run(*cliff, "--prepend", "CHANGELOG.md")
    notes = run(*cliff, "--strip", "header")
    run("git", "add", "CHANGELOG.md", *version_files())
    run("git", "commit", "--quiet", "-m", title)
    run("git", "push", "--quiet", "--force", "origin", pr_branch)

    scratch = Path(os.environ.get("RUNNER_TEMP") or tempfile.mkdtemp())
    body_file = scratch / "body.md"
    body_file.write_text(body(version, base, stage, notes), encoding="utf-8")

    found = run(
        "gh",
        "pr",
        "list",
        "--head",
        pr_branch,
        "--base",
        base,
        "--state",
        "open",
        "--json",
        "number,isDraft",
        "--jq",
        '.[0] // empty | "\\(.number) \\(.isDraft)"',
    ).strip()
    if found:
        number, draft = found.split()
        run(
            "gh",
            "pr",
            "edit",
            number,
            "--title",
            title,
            "--body-file",
            str(body_file),
        )
        if stage == "beta" and draft == "false":
            run("gh", "pr", "ready", number, "--undo")
        elif stage != "beta" and draft == "true":
            run("gh", "pr", "ready", number)
    else:
        flags = ["--draft"] if stage == "beta" else []
        run(
            "gh",
            "pr",
            "create",
            *flags,
            "--head",
            pr_branch,
            "--base",
            base,
            "--title",
            title,
            "--body-file",
            str(body_file),
        )

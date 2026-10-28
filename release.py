#!/usr/bin/env python3

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

"""Release helper for the reusable workflow .github/workflows/release.yml.

Works out version numbers from branch names and existing tags, updates the files
that hold the version, and creates annotated release tags. "The release process" in
README.md describes the process this implements.

Runs in the root of the repository being released, with the system Python
(standard library only, Python 3.12 or later).

Commands:
  start --bump minor|major  Pick the next release branch (release/X.Y) from main.
  plan                      On a release branch: decide whether to tag a release
                            candidate, tag a final release, or only update the
                            release PR.
  set-version VERSION       Write VERSION into the files listed in VERSION_FILES.
  tag VERSION [--final]     Create and push the annotated tag vVERSION.

Environment:
  VERSION_FILES  Space-separated files that hold the version number. Plain files
                 (e.g. VERSION) are overwritten; *.toml files get the version in
                 their [project] table updated. Empty if the version comes from
                 the git tag (setuptools-scm, hatch-vcs).
  GITHUB_OUTPUT  Where `start`, `plan` and `tag` append their outputs, as in a
                 GitHub Actions step. They are printed to stdout as well.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

FINAL_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
RELEASE_BRANCH = re.compile(r"^release/(\d+)\.(\d+)$")
# Squash-merged release PRs: "chore: release v0.5.0 (#42)"
RELEASE_COMMIT = re.compile(r"^chore: release v(\S+?)(?: \(#\d+\))?$")
# `version = "..."` inside the [project] table of a pyproject.toml, and nowhere else.
PROJECT_VERSION = re.compile(
    r'(?ms)(^\[project\][^\n]*\n(?:(?!^\[).)*?^version\s*=\s*)"[^"]*"'
)


def git(*args: str) -> str:
    """Run git in the current directory and return its stripped standard output."""
    result = subprocess.run(  # noqa: S603 - fixed executable, arguments are ours
        ["git", *args],  # noqa: S607 - git comes from PATH on every runner
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def fail(message: str) -> NoReturn:
    """Report MESSAGE as a GitHub Actions error annotation and exit with status 1."""
    print(f"::error::{message}")  # noqa: T201 - the annotation goes to the job log
    sys.exit(1)


def output(**values: str) -> None:
    """Print VALUES as key=value lines and append them to $GITHUB_OUTPUT if set."""
    lines = [f"{key}={value}" for key, value in values.items()]
    print("\n".join(lines))  # noqa: T201 - the outputs are part of the CLI
    if path := os.environ.get("GITHUB_OUTPUT"):
        with Path(path).open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def all_tags() -> list[str]:
    """Return every tag starting with `v`."""
    return git("tag", "--list", "v*").split()


def final_versions() -> list[tuple[int, int, int]]:
    """Return the versions of the final release tags (vX.Y.Z), oldest first."""
    return sorted(
        (int(m[1]), int(m[2]), int(m[3]))
        for tag in all_tags()
        if (m := FINAL_TAG.match(tag))
    )


def version_files() -> list[str]:
    """Return the files listed in $VERSION_FILES."""
    return os.environ.get("VERSION_FILES", "").split()


def set_version(version: str) -> None:
    """Write VERSION into every file listed in $VERSION_FILES."""
    for name in version_files():
        path = Path(name)
        if path.suffix == ".toml":
            text, count = PROJECT_VERSION.subn(
                rf'\g<1>"{version}"', path.read_text(encoding="utf-8"), count=1
            )
            if count != 1:
                fail(f"No version in the [project] table of {path}")
            path.write_text(text, encoding="utf-8")
        else:
            path.write_text(version + "\n", encoding="utf-8")


def cmd_start(bump: str) -> None:
    """Pick the release branch that follows the newest final release."""
    finals = final_versions()
    major, minor = finals[-1][:2] if finals else (0, 0)
    if bump == "major":
        major, minor = major + 1, 0
    else:
        minor += 1
    branch = f"release/{major}.{minor}"
    if git("ls-remote", "--heads", "origin", branch):
        fail(f"{branch} already exists: that release is already in progress.")
    output(branch=branch, version=f"{major}.{minor}.0")


def cmd_plan() -> None:
    """Decide what a push to the checked-out release branch should produce."""
    branch = os.environ.get("GITHUB_REF_NAME") or git(
        "rev-parse", "--abbrev-ref", "HEAD"
    )
    if not (m := RELEASE_BRANCH.match(branch)):
        fail(f"'{branch}' is not a release branch (release/X.Y).")
    major, minor = int(m[1]), int(m[2])
    series = f"{major}.{minor}"

    patches = [p for (x, y, p) in final_versions() if (x, y) == (major, minor)]
    pending = f"{series}.{max(patches) + 1 if patches else 0}"

    subject = git("log", "-1", "--format=%s")
    if released := RELEASE_COMMIT.match(subject):
        # The release PR was just merged: tag the final release.
        if released[1] != pending:
            fail(f"Release PR says v{released[1]}, but the next version is v{pending}.")
        output(series=series, action="final", tag_version=pending, pending=pending)
    elif not patches:
        # X.Y.0 isn't out yet: every change gets a new release candidate.
        rcs = [
            int(rc[1])
            for tag in all_tags()
            if (rc := re.fullmatch(rf"v{major}\.{minor}\.0rc(\d+)", tag))
        ]
        output(
            series=series,
            action="rc",
            tag_version=f"{series}.0rc{max(rcs, default=0) + 1}",
            pending=pending,
        )
    else:
        # X.Y.0 is out: only open or update the release PR for the next patch.
        output(series=series, action="pr", tag_version="", pending=pending)


def cmd_tag(version: str, *, final: bool) -> None:
    """Create the annotated tag vVERSION and push it to origin."""
    tag = f"v{version}"
    if tag in all_tags():
        fail(f"Tag {tag} already exists.")
    if version_files():
        set_version(version)
        if git("status", "--porcelain", "--", *version_files()):
            if final:
                fail(
                    f"The version files don't say {version}. Was the release PR edited?"
                )
            # Release candidates: record the version in a commit that only the tag
            # points to, so the release branch itself is never pushed to.
            git("checkout", "--detach")
            git("add", "--", *version_files())
            git("commit", "--quiet", "-m", f"chore: set version {version}")
    git("tag", "-a", tag, "-m", f"Release {version}")
    git("push", "--quiet", "origin", f"refs/tags/{tag}")
    output(tag=tag)


def main(argv: list[str] | None = None) -> None:
    """Parse the command line and run the chosen command."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--bump", choices=["minor", "major"], default="minor")
    sub.add_parser("plan")
    set_v = sub.add_parser("set-version")
    set_v.add_argument("version")
    tag = sub.add_parser("tag")
    tag.add_argument("version")
    tag.add_argument("--final", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "start":
        cmd_start(args.bump)
    elif args.command == "plan":
        cmd_plan()
    elif args.command == "set-version":
        set_version(args.version)
    elif args.command == "tag":
        cmd_tag(args.version, final=args.final)


if __name__ == "__main__":
    main()

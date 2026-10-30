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

"""The command line: argparse subcommands and their handlers."""

from __future__ import annotations

import argparse

from release import changelog, tagging, workflow
from release.actions import output
from release.release_pr import release_pr
from release.versions import SUFFIXES

DESCRIPTION = """\
Release automation of release-tools: version numbers from tags and branches, release
tags, the release PR and CHANGELOG.md. Run it in the root of the repository being
released; the reusable workflows of release-tools call it at each step.
"""

EPILOG = """\
environment:
  VERSION_FILES    files that hold the version number, space-separated: plain files
                   (e.g. VERSION) are overwritten, *.toml files get their [project]
                   version updated; empty if the version comes from the git tag
  GITHUB_OUTPUT    where start, plan, backport-targets and tag append their outputs,
                   as in a GitHub Actions step (they are printed as well)
  GITHUB_REF_NAME  the release branch, for plan (default: the checked-out branch)
  RUNNER_TEMP      where release-pr writes the PR body (default: a temporary directory)
  GH_TOKEN         the token gh uses in release-pr
"""


def run_start(args: argparse.Namespace) -> None:
    """Start or promote a release and write its outputs."""
    output(**workflow.start(args.bump, args.stage))


def run_plan(_args: argparse.Namespace) -> None:
    """Decide what a push to a release branch produces and write the outputs."""
    output(**workflow.plan())


def run_backport_targets(_args: argparse.Namespace) -> None:
    """Write the branches a backport goes to and their next versions."""
    output(**workflow.backport_targets())


def run_tag(args: argparse.Namespace) -> None:
    """Create and push a release tag and write its name."""
    output(tag=tagging.create_tag(args.version, final=args.final))


def run_set_version(args: argparse.Namespace) -> None:
    """Write a version into the version files."""
    tagging.set_version(args.version)


def run_sync_changelog(args: argparse.Namespace) -> None:
    """Add a final release's section to CHANGELOG.md."""
    changelog.sync_changelog(args.tag)


def run_release_pr(args: argparse.Namespace) -> None:
    """Open or update the release PR."""
    release_pr(args.series, args.version, args.stage, args.head)


def build_parser() -> argparse.ArgumentParser:
    """Return the parser of every subcommand, each with its handler."""
    parser = argparse.ArgumentParser(
        prog="release",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    start = sub.add_parser(
        "start",
        help="from main: tag the next alpha, create release/X.Y, or promote it to"
        " release candidates",
        description="Start the release that follows the newest final release: tag the"
        " next alpha on HEAD (main), or create release/X.Y at HEAD with its first beta"
        " or release candidate. With --stage rc on a release in beta, promote it.",
    )
    start.add_argument(
        "--bump",
        choices=["minor", "major"],
        default="minor",
        help="which release follows the newest final release (default: minor)",
    )
    start.add_argument(
        "--stage",
        choices=list(SUFFIXES),
        default="rc",
        help="the stage to start at, or to promote to (default: rc)",
    )
    start.set_defaults(handler=run_start)

    plan = sub.add_parser(
        "plan",
        help="on a release branch: tag a pre-release or the final release, or only"
        " update the release PR",
        description="Decide what the push to the checked-out release branch produces:"
        " the next beta or release candidate, the final release (after the release PR"
        " is merged), or only an update of the release PR.",
    )
    plan.set_defaults(handler=run_plan)

    targets = sub.add_parser(
        "backport-targets",
        help="list the release branches a backport goes to, and their next versions",
        description="The newest release branch; while its X.Y.0 isn't out, also the"
        " newest released one.",
    )
    targets.set_defaults(handler=run_backport_targets)

    tag = sub.add_parser(
        "tag",
        help="create and push the annotated tag vVERSION",
        description="Create the annotated tag vVERSION on HEAD and push it. With"
        " version files, a pre-release's tag points to a commit on top of HEAD that"
        " records the version.",
    )
    tag.add_argument("version", metavar="VERSION", help="e.g. 1.2.0 or 1.2.0rc1")
    tag.add_argument(
        "--final",
        action="store_true",
        help="a final release: the version files must already say VERSION",
    )
    tag.set_defaults(handler=run_tag)

    set_version = sub.add_parser(
        "set-version",
        help="write VERSION into the files listed in VERSION_FILES",
        description="Write VERSION into the files listed in VERSION_FILES.",
    )
    set_version.add_argument("version", metavar="VERSION")
    set_version.set_defaults(handler=run_set_version)

    sync = sub.add_parser(
        "sync-changelog",
        help="add the section of the final release TAG to CHANGELOG.md",
        description="Add the section of the final release TAG to ./CHANGELOG.md, in"
        " version order (run in a checkout of main).",
    )
    sync.add_argument("tag", metavar="TAG", help="e.g. v1.2.0")
    sync.set_defaults(handler=run_sync_changelog)

    pr = sub.add_parser(
        "release-pr",
        help="open or update the release PR of release/X.Y",
        description="Build release-pr/X.Y (HEAD of the release branch plus a commit"
        " that sets the version files and adds the CHANGELOG.md section, which starts"
        " from main's), push it, and open or update the PR into release/X.Y. The PR"
        " is a draft during beta. Needs git-cliff and gh (GH_TOKEN) on PATH; writes"
        " the PR body to RUNNER_TEMP (or a temporary directory).",
    )
    pr.add_argument("--series", required=True, metavar="X.Y")
    pr.add_argument(
        "--version", required=True, metavar="X.Y.Z", help="the version the PR releases"
    )
    pr.add_argument("--stage", required=True, choices=["beta", "rc", "released"])
    pr.add_argument(
        "--head",
        required=True,
        metavar="SHA",
        help="the commit of release/X.Y to build on",
    )
    pr.set_defaults(handler=run_release_pr)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse the command line and run the chosen subcommand."""
    args = build_parser().parse_args(argv)
    args.handler(args)

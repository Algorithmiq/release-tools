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
import shlex
import subprocess
import sys

from release import changelog, descriptions, development, tagging, workflow
from release.actions import fail, output
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
  GITHUB_OUTPUT    where start, plan, backport-targets, tag, develop and
                   tag-development append their outputs, as in a GitHub Actions
                   step (they are printed as well)
  GITHUB_REF_NAME  the release branch, for plan (default: the checked-out branch)
  RUNNER_TEMP      where release-pr writes the PR body (default: a temporary directory)
  GH_TOKEN         the token gh uses in release-pr and pr-descriptions
"""

ENVIRONMENT = {
    "VERSION_FILES": "files that hold the version number, space-separated (see --help)",
    "GITHUB_OUTPUT": "where outputs are appended (they are printed as well)",
    "GITHUB_REF_NAME": "the release branch (default: the checked-out branch)",
    "RUNNER_TEMP": "where the PR body is written (default: a temporary directory)",
    "GH_TOKEN": "the token gh uses: it needs to read pull requests",
    "GITHUB_REPOSITORY": "the repository whose PRs to read, owner/name (set by GitHub\n"
    "Actions); without it the context is written as it was read",
}


def epilog(*names: str) -> str:
    """Return the help section that describes the environment variables NAMES."""
    width = max(map(len, names)) + 2
    indent = "\n" + " " * (width + 2)
    return "environment:\n" + "".join(
        f"  {name:<{width}}{ENVIRONMENT[name].replace('\n', indent)}\n"
        for name in names
    )


def run_changelog_section(args: argparse.Namespace) -> None:
    """Print a final release's section of CHANGELOG.md, or exit with status 1."""
    if (section := changelog.changelog_section(args.tag)) is None:
        sys.exit(1)
    print(section)  # noqa: T201 - the section is the output of the command


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
        epilog=epilog("VERSION_FILES", "GITHUB_OUTPUT"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    start.set_defaults(handler=lambda a: output(**workflow.start(a.bump, a.stage)))

    plan = sub.add_parser(
        "plan",
        help="on a release branch: tag a pre-release or the final release, or only"
        " update the release PR",
        description="Decide what the push to the checked-out release branch produces:"
        " the next beta or release candidate, the final release (after the release PR"
        " is merged), or only an update of the release PR.",
        epilog=epilog("GITHUB_REF_NAME", "VERSION_FILES", "GITHUB_OUTPUT"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    plan.set_defaults(handler=lambda _: output(**workflow.plan()))

    targets = sub.add_parser(
        "backport-targets",
        help="list the release branches a backport goes to, and their next versions",
        description="The newest release branch; while its X.Y.0 isn't out, also the"
        " newest released one.",
        epilog=epilog("GITHUB_OUTPUT"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    targets.set_defaults(handler=lambda _: output(**workflow.backport_targets()))

    tag = sub.add_parser(
        "tag",
        help="create and push the annotated tag vVERSION",
        description="Create the annotated tag vVERSION on HEAD and push it. With"
        " version files, a pre-release's tag points to a commit on top of HEAD that"
        " records the version.",
        epilog=epilog("VERSION_FILES", "GITHUB_OUTPUT"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    tag.add_argument("version", metavar="VERSION", help="e.g. 1.2.0 or 1.2.0rc1")
    tag.add_argument(
        "--final",
        action="store_true",
        help="a final release: the version files must already say VERSION",
    )
    tag.set_defaults(
        handler=lambda a: output(tag=tagging.create_tag(a.version, final=a.final))
    )

    set_version = sub.add_parser(
        "set-version",
        help="write VERSION into the files listed in VERSION_FILES",
        description="Write VERSION into the files listed in VERSION_FILES.",
        epilog=epilog("VERSION_FILES"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    set_version.add_argument("version", metavar="VERSION")
    set_version.set_defaults(handler=lambda a: tagging.set_version(a.version))

    sync = sub.add_parser(
        "sync-changelog",
        help="add the section of the final release TAG to CHANGELOG.md",
        description="Add the section of the final release TAG to ./CHANGELOG.md, in"
        " version order (run in a checkout of main).",
    )
    sync.add_argument("tag", metavar="TAG", help="e.g. v1.2.0")
    sync.set_defaults(handler=lambda a: changelog.sync_changelog(a.tag))

    section = sub.add_parser(
        "changelog-section",
        help="print the section of the final release TAG in CHANGELOG.md",
        description="Print the section of the final release TAG in CHANGELOG.md as"
        " tagged, without the header of the file. If TAG has no CHANGELOG.md or no"
        " section in it, print the reason on standard error and exit with status 1.",
    )
    section.add_argument("tag", metavar="TAG", help="e.g. v1.2.0")
    section.set_defaults(handler=run_changelog_section)

    pr_descriptions = sub.add_parser(
        "pr-descriptions",
        help="filter git-cliff's context: PR descriptions in place of commit bodies",
        description="Read the changelog context that `git cliff --context` writes on"
        " standard input, and write it with the description of each commit's pull"
        " request in place of the commit's body, for `git cliff --from-context -`."
        " The description counts only if the PR is merged as that commit; otherwise,"
        " and if GitHub can't be asked, the commit keeps its body and a warning names"
        " the commit and the PR.",
        epilog=epilog("GITHUB_REPOSITORY", "GH_TOKEN"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pr_descriptions.set_defaults(handler=lambda _: descriptions.filter_context())

    develop = sub.add_parser(
        "develop",
        help="after the final release TAG, write the version main develops next into"
        " the version files",
        description="After X.Y.0 of the newest series, main develops X.(Y+1).0.dev0:"
        " write it into the files listed in VERSION_FILES (run in a checkout of main)"
        " and output it. Patch releases and older lines output an empty version.",
        epilog=epilog("VERSION_FILES", "GITHUB_OUTPUT"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    develop.add_argument("tag", metavar="TAG", help="e.g. v1.2.0")
    develop.set_defaults(handler=lambda a: output(**development.develop(a.tag)))

    tag_development = sub.add_parser(
        "tag-development",
        help="after the final release TAG, tag main's changelog commit with"
        " vX.(Y+1).0.dev0",
        description="After X.Y.0 of the newest series, tag the commit on origin's main"
        " that added its changelog with vX.(Y+1).0.dev0 and push it, so that versions"
        " derived from main sort above X.Y.0. Nothing publishes it. Warns if main"
        " doesn't have that commit yet.",
        epilog=epilog("GITHUB_OUTPUT"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    tag_development.add_argument("tag", metavar="TAG", help="e.g. v1.2.0")
    tag_development.set_defaults(
        handler=lambda a: output(**development.tag_development(a.tag))
    )

    pr = sub.add_parser(
        "release-pr",
        help="open or update the release PR of release/X.Y",
        description="Build release-pr/X.Y (HEAD of the release branch plus a commit"
        " that sets the version files and adds the CHANGELOG.md section, which starts"
        " from main's), push it, and open or update the PR into release/X.Y. The PR"
        " is a draft during beta. Needs git-cliff and gh (GH_TOKEN) on PATH; writes"
        " the PR body to RUNNER_TEMP (or a temporary directory).",
        epilog=epilog("VERSION_FILES", "RUNNER_TEMP", "GH_TOKEN", "GITHUB_REPOSITORY"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pr.add_argument("--series", required=True, metavar="X.Y", help="e.g. 0.1")
    pr.add_argument(
        "--version", required=True, metavar="X.Y.Z", help="the version the PR releases"
    )
    pr.add_argument(
        "--stage",
        required=True,
        choices=["beta", "rc", "released"],
        help="beta (draft PR), rc or released (ready PR)",
    )
    pr.add_argument(
        "--head",
        required=True,
        metavar="SHA",
        help="the commit of release/X.Y to build on",
    )
    pr.set_defaults(handler=lambda a: release_pr(a.series, a.version, a.stage, a.head))
    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse the command line and run the chosen subcommand."""
    args = build_parser().parse_args(argv)
    try:
        args.handler(args)
    except subprocess.CalledProcessError as error:
        # The command's own message is already in the log: run() inherits stderr.
        fail(f"{shlex.join(error.cmd)} failed with exit status {error.returncode}.")

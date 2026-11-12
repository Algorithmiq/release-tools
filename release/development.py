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

"""The version main develops after a final release: X.(Y+1).0.dev0.

Final tags are created on release/X.Y and never reach main's history, so a version
derived from main (git describe, setuptools-scm, hatch-vcs, copier) would stay below
the final until the next alpha. After X.Y.0, main moves on to X.(Y+1).0.dev0: written
into its version files by the changelog PR, and tagged vX.(Y+1).0.dev0 on the commit
that PR adds to main. A .dev version is a pre-release under PEP 440, and nothing ever
publishes it.
"""

from __future__ import annotations

import re
import sys

from release.git import git
from release.tagging import set_version, version_files
from release.versions import all_tags, final_version, final_versions


def development_version(tag: str) -> str:
    """Return the version main develops after the final TAG, or an empty string.

    Only X.Y.0 of the newest series moves main on: patch releases and releases of an
    older line leave it where it is.
    """
    major, minor, patch = final_version(tag)
    if patch != 0 or max(final_versions(), default=(0, 0, 0))[:2] > (major, minor):
        return ""
    return f"{major}.{minor + 1}.0.dev0"


def develop(tag: str) -> dict[str, str]:
    """After the final TAG, write the version main develops into the version files.

    Run in a checkout of main. Return the step's outputs: the version, or an empty
    string if TAG doesn't move main on.
    """
    version = development_version(tag)
    if version and version_files():
        set_version(version)
    return {"version": version}


def changelog_commit(tag: str, ref: str) -> str:
    """Return the commit on REF that added TAG's changelog, or an empty string."""
    subject = re.compile(
        rf"^chore: update changelog for {re.escape(tag)}(?: \(#\d+\))?$"
    )
    for line in git("log", "--format=%H %s", ref).splitlines():
        commit, _, title = line.partition(" ")
        if subject.match(title):
            return commit
    return ""


def tag_development(tag: str) -> dict[str, str]:
    """Tag the commit that added TAG's changelog to main with vX.(Y+1).0.dev0.

    Return the step's outputs: the tag, or an empty string if TAG doesn't move main on,
    the tag already exists or main doesn't have the changelog commit yet.
    """
    version = development_version(tag)
    if not version:
        return {"tag": ""}
    marker = f"v{version}"
    if marker in all_tags():
        print(f"::notice::{marker} already exists.", file=sys.stderr)  # noqa: T201
        return {"tag": ""}
    git("fetch", "--quiet", "origin", "refs/heads/main")
    commit = changelog_commit(tag, "FETCH_HEAD")
    if not commit:
        print(  # noqa: T201 - the annotation goes to the job log
            f"::warning::main doesn't have the changelog of {tag} yet, so {marker}"
            " isn't tagged: versions derived from main stay below"
            f" {tag[1:]} until the next alpha. Re-run this job after the changelog PR"
            " merges.",
            file=sys.stderr,
        )
        return {"tag": ""}
    series = version.rsplit(".", 2)[0]
    git("tag", "-a", marker, "-m", f"Development of {series}", commit)
    git("push", "--quiet", "origin", f"refs/tags/{marker}")
    return {"tag": marker}

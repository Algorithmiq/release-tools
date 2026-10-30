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

"""Version files and release tags."""

from __future__ import annotations

import os
import re
from pathlib import Path

from release.actions import fail
from release.git import git
from release.versions import all_tags

# `version = "..."` inside the [project] table of a pyproject.toml, and nowhere else.
PROJECT_VERSION = re.compile(
    r'(?ms)(^\[project\][^\n]*\n(?:(?!^\[).)*?^version\s*=\s*)"[^"]*"'
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


def create_tag(version: str, *, final: bool = False, branch: str = "") -> str:
    """Create the annotated tag vVERSION on HEAD, push it and return its name.

    With version files, a pre-release's tag points to a commit on top of HEAD that
    records the version, so that no branch is ever pushed to. With BRANCH, HEAD is
    pushed as that new branch in the same atomic push: the branch and its first tag
    exist together or not at all.
    """
    tag = f"v{version}"
    if tag in all_tags():
        fail(f"Tag {tag} already exists.")
    head = git("rev-parse", "HEAD")
    if version_files():
        set_version(version)
        if git("status", "--porcelain", "--", *version_files()):
            if final:
                fail(
                    f"The version files don't say {version}. Was the release PR edited?"
                )
            # Pre-releases: record the version in a commit that only the tag points
            # to, so the branch itself is never pushed to.
            git("checkout", "--detach")
            git("add", "--", *version_files())
            git("commit", "--quiet", "-m", f"chore: set version {version}")
    git("tag", "-a", tag, "-m", f"Release {version}")
    refs = [f"refs/tags/{tag}"]
    if branch:
        refs.insert(0, f"{head}:refs/heads/{branch}")
    git("push", "--quiet", "--atomic", "origin", *refs)
    return tag

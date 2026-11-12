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

"""CHANGELOG.md: a final release's section, and adding it to main in version order."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from release.actions import fail
from release.git import git
from release.versions import FINAL_TAG

# The heading of a final release's section in CHANGELOG.md: "## 1.2.0 (2026-10-29)".
CHANGELOG_SECTION = re.compile(r"^## (\d+)\.(\d+)\.(\d+) ")


def changelog_sections(text: str) -> tuple[str, list[str]]:
    """Split TEXT into its header and its `## ` sections, without trailing newlines."""
    header, *sections = re.split(r"(?m)^(?=## )", text)
    return header.rstrip("\n"), [section.rstrip("\n") for section in sections]


def section_version(section: str) -> tuple[int, int, int] | None:
    """Return the version of a changelog SECTION, or None for any other heading."""
    if m := CHANGELOG_SECTION.match(section):
        return int(m[1]), int(m[2]), int(m[3])
    return None


def final_version(tag: str) -> tuple[int, int, int]:
    """Return the version of the final release TAG, or fail if it is not one."""
    if not (m := FINAL_TAG.match(tag)):
        fail(f"{tag} is not a final release tag (vX.Y.Z).")
    return int(m[1]), int(m[2]), int(m[3])


def version_section(text: str, version: tuple[int, int, int]) -> str | None:
    """Return the section of VERSION in the changelog TEXT, or None."""
    return next(
        (s for s in changelog_sections(text)[1] if section_version(s) == version),
        None,
    )


def changelog_section(tag: str) -> str | None:
    """Return the section of the final release TAG in CHANGELOG.md as tagged.

    The tag is on the release PR's merge commit, so the section is the text that the
    PR's reviewers saw and fixed, without the header of the file. Return None, after
    saying why on standard error, if TAG has no CHANGELOG.md or no section in it.
    """
    version = final_version(tag)
    try:
        text = git("show", f"{tag}:CHANGELOG.md", quiet=True)
    except subprocess.CalledProcessError:
        print(f"{tag} has no CHANGELOG.md.", file=sys.stderr)  # noqa: T201
        return None
    if (section := version_section(text, version)) is None:
        print(  # noqa: T201 - the reason goes to the job log
            f"CHANGELOG.md at {tag} has no section for {tag[1:]}.", file=sys.stderr
        )
    return section


def sync_changelog(tag: str) -> None:
    """Add the section of the final release TAG to CHANGELOG.md, in version order.

    Only the new section is copied, so CHANGELOG.md keeps every release of every line,
    whatever the order in which they are released.
    """
    version = final_version(tag)
    try:
        released = git("show", f"{tag}:CHANGELOG.md", quiet=True) + "\n"
    except subprocess.CalledProcessError:
        fail(f"{tag} has no CHANGELOG.md.")
    path = Path("CHANGELOG.md")
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if not current.strip():
        path.write_text(released, encoding="utf-8")
        return
    new = version_section(released, version)
    if new is None:
        print(  # noqa: T201 - the annotation goes to the job log
            f"::notice::CHANGELOG.md at {tag} has no section for {tag[1:]}: nothing to"
            f" add."
        )
        return
    header, sections = changelog_sections(current)
    versions = [section_version(s) for s in sections]
    if version in versions:
        return
    index = next(
        (i for i, v in enumerate(versions) if v is not None and v < version),
        len(sections),
    )
    sections.insert(index, new)
    parts = [part for part in (header, *sections) if part]
    path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")

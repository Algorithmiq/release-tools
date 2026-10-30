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

"""CHANGELOG.md on main: add a final release's section in version order."""

from __future__ import annotations

import re
import subprocess
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


def sync_changelog(tag: str) -> None:
    """Add the section of the final release TAG to CHANGELOG.md, in version order.

    Only the new section is copied, so CHANGELOG.md keeps every release of every line,
    whatever the order in which they are released.
    """
    if not (m := FINAL_TAG.match(tag)):
        fail(f"{tag} is not a final release tag (vX.Y.Z).")
    version = (int(m[1]), int(m[2]), int(m[3]))
    try:
        released = git("show", f"{tag}:CHANGELOG.md") + "\n"
    except subprocess.CalledProcessError:
        fail(f"{tag} has no CHANGELOG.md.")
    path = Path("CHANGELOG.md")
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if not current.strip():
        path.write_text(released, encoding="utf-8")
        return
    new = [s for s in changelog_sections(released)[1] if section_version(s) == version]
    if not new:
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
    sections.insert(index, new[0])
    parts = [part for part in (header, *sections) if part]
    path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")

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

"""Tests of the adopt-release-tools agent skill: frontmatter, version, references.

The skill reads release-tools from a clone of the latest release (`$rt`), so every
`$rt/...` path it names must exist here, and every page heading it quotes too.
"""

from __future__ import annotations

import re
from typing import Any

import yaml
from conftest import ROOT

SKILL = ROOT / "skills" / "adopt-release-tools"
RELEASE_TOOLS_REF = re.compile(r"Algorithmiq/release-tools/([\w./-]+)@([\w.-]+)")
CLONE_PATH = re.compile(r"\$rt/([\w./-]*[\w-])")
# `$rt/docs/page.md`, "Heading"
QUOTED_HEADING = re.compile(r'`\$rt/(docs/[\w-]+\.md)`, "([^"]+)"')
MARKDOWN_LINK = re.compile(r"\]\(([^)#\s]+)\)")


def frontmatter() -> dict[str, Any]:
    """Return the YAML frontmatter of SKILL.md."""
    _, front, _ = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("---\n", 2)
    return yaml.safe_load(front)


def skill_text() -> str:
    """Return every Markdown file of the skill, concatenated."""
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(SKILL.glob("*.md")))


def test_frontmatter() -> None:
    front = frontmatter()
    assert set(front) == {"name", "description", "metadata"}
    assert front["name"] == SKILL.name
    assert front["description"].startswith("Use when")
    assert len(front["description"]) <= 500


def test_written_for_the_major_the_stubs_pin() -> None:
    stub = (ROOT / "examples" / "stubs" / "release.yml").read_text(encoding="utf-8")
    (tag,) = {ref for _, ref in RELEASE_TOOLS_REF.findall(stub)}
    major = tag.removeprefix("v").split(".")[0]
    assert frontmatter()["metadata"]["release-tools-major"] == major


def test_every_release_tools_path_exists() -> None:
    paths = set(CLONE_PATH.findall(skill_text()))
    assert "examples/stubs/deploy-codeartifact.yml" in paths
    assert sorted(p for p in paths if not (ROOT / p).exists()) == []


def test_every_quoted_heading_exists() -> None:
    quoted = QUOTED_HEADING.findall(skill_text())
    assert quoted
    for page, heading in quoted:
        lines = (ROOT / page).read_text(encoding="utf-8").splitlines()
        assert any(re.fullmatch(rf"#+ {re.escape(heading)}", line) for line in lines), (
            page,
            heading,
        )


def test_links_between_skill_files_resolve() -> None:
    for target in MARKDOWN_LINK.findall(skill_text()):
        if not target.startswith("http"):
            assert (SKILL / target).exists(), target


def test_no_pinned_release_tools_reference() -> None:
    # The skill pins the latest release at run time; a tag written here would go stale.
    assert not RELEASE_TOOLS_REF.search(skill_text())

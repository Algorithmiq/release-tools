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

import json
import re
from typing import Any

import pytest
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


def phase(number: int) -> str:
    """Return the text of SKILL.md's phase NUMBER, up to the next phase."""
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(
        rf"^## Phase {number}:.*?(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    assert match, number
    return match.group(0)


def test_upstream_reports_go_through_the_admin() -> None:
    # release-tools is public: an agent that opens an issue there itself can leak.
    text = " ".join(skill_text().split())
    assert "You do not open issues, PRs or comments on release-tools" in text


@pytest.mark.parametrize("number", [2, 4, 5, 6])
def test_phases_that_wait_for_the_admin_say_stop(number: int) -> None:
    assert re.search(r"\*\*stop\b", phase(number), re.IGNORECASE)


def test_handed_over_commands_hold_no_placeholder_or_heredoc() -> None:
    blocks = re.findall(r"```bash\n(.*?)```", skill_text(), re.DOTALL)
    assert blocks
    for block in blocks:
        assert "<<" not in block, block
        assert not re.search(r"<[\w -]+>", block), block


def test_the_handed_over_example_is_the_docs_tag_ruleset() -> None:
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    example = re.search(r"```json\n(.*?)```", skill, re.DOTALL)
    assert example
    setup = (ROOT / "docs" / "repository-setup.md").read_text(encoding="utf-8")
    docs = re.search(
        r"rulesets --input - <<EOF\n\s*(\{\"name\": \"release tags\".*?)EOF",
        setup,
        re.DOTALL,
    )
    assert docs
    app_id = json.loads(example.group(1))["bypass_actors"][0]["actor_id"]
    assert json.loads(example.group(1)) == json.loads(
        docs.group(1).replace("$APP_ID", str(app_id))
    )


def test_the_codeartifact_variables_are_the_ones_the_owner_sets() -> None:
    # Phase 2 hands an owner step 5's commands for the variables the workflows read.
    mapped = re.findall(
        r"vars\.(CODEARTIFACT_\w+)", (SKILL / "publish-workflow.md").read_text()
    )
    setup = (ROOT / "docs" / "organisation-setup.md").read_text(encoding="utf-8")
    assert set(re.findall(r"gh variable set (CODEARTIFACT_\w+)", setup)) == set(mapped)
    assert len(set(mapped)) == 6


def test_phase_5_reads_the_rulesets_again_before_step_8() -> None:
    # Rulesets can change between phase 1 and the merge: phase 5 reads them again.
    text = " ".join(phase(5).split())
    reread = text.index(
        "read the Rulesets and Classic branch protection rows of phase 1 again"
    )
    assert "rules/branches/main" in text
    assert reread < text.index("step 8 of `$rt/docs/repository-setup.md`")

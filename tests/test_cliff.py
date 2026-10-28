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

"""Tests of cliff.toml: git-cliff run on scratch histories of squash-merged PRs.

git-cliff comes from the dev dependency group, pinned to the version the workflows
and actions install.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest
from conftest import ROOT

if TYPE_CHECKING:
    from conftest import Repo

GIT_CLIFF_VERSION = "2.14.2"

HEADER = """\
# Changelog

All notable changes to this project are listed here.
"""

# A PR description as the template leaves it, with the Migration section above the
# Checklist.
BREAKING_BODY = """\
## Summary

Removes the old solver.

## Migration
<!-- Required for breaking changes (!) and deprecations. Delete otherwise. -->
Replace `old_solve(x)` with `solve(x)`:

```python
solve(x)
```

## Checklist

- [x] Tests added or updated
"""

DEPRECATION_BODY = """\
## Migration

Use `bar()` instead of `foo()`. `foo` will be removed in 0.6.0.
"""


def cliff(*args: str) -> str:
    """Run git-cliff with the central cliff.toml in the current directory."""
    executable = shutil.which("git-cliff")
    assert executable, "git-cliff is missing: run the tests with `just test`"
    result = subprocess.run(
        [executable, "--config", str(ROOT / "cliff.toml"), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def undated(text: str) -> str:
    """Replace the release dates in TEXT by DATE."""
    return re.sub(r"\(\d{4}-\d{2}-\d{2}\)", "(DATE)", text)


@pytest.fixture
def history(repo: Repo) -> Repo:
    """Return a repository with v0.0.0 followed by a mix of squash-merged PRs."""
    repo.commit("chore: start")
    repo.git("tag", "-a", "v0.0.0", "-m", "Start of the changelog")
    repo.commit("feat: ✨ add 3 new modes (#1)")
    repo.commit(f"feat!: 💥 remove old solver API (#2)\n\n{BREAKING_BODY}")
    repo.commit("fix(io): :bug: crash on NaN input (#3)")
    repo.commit(f"deprecate: :wastebasket: deprecate `foo` (#4)\n\n{DEPRECATION_BODY}")
    repo.commit("perf: ⚡️ 10x faster integrals (#5)")
    repo.commit("docs: 📝 explain the 2D plots (#6)")
    repo.commit(
        f"feat: add a feature with a stray Migration section (#7)\n\n{DEPRECATION_BODY}"
    )
    for kind in ("refactor", "test", "ci", "chore", "build", "style"):
        repo.commit(f"{kind}: 🔧 internal change")
    repo.commit("Merge an unconventional commit")
    return repo


EXPECTED_0_1_0 = """\
## 0.1.0 (DATE)

### Breaking changes

- Remove old solver API (#2)

  Replace `old_solve(x)` with `solve(x)`:

  ```python
  solve(x)
  ```

### Deprecations

- Deprecate `foo` (#4)

  Use `bar()` instead of `foo()`. `foo` will be removed in 0.6.0.

### Features

- Add 3 new modes (#1)
- Add a feature with a stray Migration section (#7)

### Fixes

- **io:** Crash on NaN input (#3)

### Performance

- 10x faster integrals (#5)

### Documentation

- Explain the 2D plots (#6)
"""


def test_cliff_runs_the_pinned_version() -> None:
    assert cliff("--version").strip() == f"git-cliff {GIT_CLIFF_VERSION}"


@pytest.mark.usefixtures("history")
def test_changelog_entry() -> None:
    # Gitmoji stripped without eating digits, migration notes indented under their
    # entry and cut at the next heading, internal and unconventional commits skipped.
    notes = cliff("--unreleased", "--tag", "v0.1.0", "--strip", "header")
    # Without the header the notes start with the blank line that followed it.
    assert undated(notes) == "\n" + EXPECTED_0_1_0


def test_no_double_blank_lines(history: Repo) -> None:
    # Two breaking changes with notes in one section, the last one followed by the
    # next section, and notes on the very last entry of the changelog.
    history.commit(f"fix!: change the default (#8)\n\n{DEPRECATION_BODY}")
    history.commit(f"deprecate: deprecate `baz` (#9)\n\n{DEPRECATION_BODY}")
    notes = cliff("--unreleased", "--tag", "v0.1.0")
    assert "\n\n\n" not in notes
    assert notes.endswith("\n")
    assert not notes.endswith("\n\n")
    breaking = notes.split("### Breaking changes\n\n")[1].split("### Deprecations")[0]
    assert breaking.count("\n\n  ") == 3


def test_breaking_change_of_a_skipped_type_is_kept(repo: Repo) -> None:
    repo.commit("chore: start")
    repo.git("tag", "v0.0.0")
    repo.commit(f"ci!: 👷 drop Python 3.11 (#1)\n\n{DEPRECATION_BODY}")
    assert "- Drop Python 3.11 (#1)" in cliff("--unreleased")


def test_release_candidate_tags_are_not_versions(history: Repo) -> None:
    history.git("tag", "-a", "v0.1.0rc1", "-m", "Release 0.1.0rc1")
    history.commit("fix: 🐛 fix found in rc1 (#10)")
    # Release notes of the next candidate: everything since the last final release.
    rc2 = cliff("--unreleased", "--tag", "v0.1.0rc2", "--strip", "header")
    assert rc2.startswith("\n## 0.1.0rc2 (")
    assert "- Add 3 new modes (#1)" in rc2
    assert "- Fix found in rc1 (#10)" in rc2

    history.git("tag", "-a", "v0.1.0", "-m", "Release 0.1.0")
    history.commit("fix: 🐛 after the release (#11)")
    history.git("tag", "-a", "v0.1.1rc1", "-m", "not a version either")
    changelog = cliff()
    assert "## 0.1.0rc" not in changelog
    assert "## 0.1.1rc" not in changelog
    assert changelog.count("## 0.1.0 (") == 1
    assert "- Fix found in rc1 (#10)" in changelog.split("## 0.1.0 (")[1]
    assert "- After the release (#11)" in changelog.split("## 0.1.0 (")[0]


def test_current_gives_the_notes_of_the_checked_out_final_tag(history: Repo) -> None:
    history.git("tag", "-a", "v0.1.0", "-m", "Release 0.1.0")
    history.commit("fix: 🐛 later (#12)")
    history.git("tag", "-a", "v0.1.1", "-m", "Release 0.1.1")
    history.git("checkout", "--quiet", "v0.1.0")
    assert undated(cliff("--current", "--strip", "header")) == "\n" + EXPECTED_0_1_0


@pytest.mark.parametrize("existing", ["", HEADER], ids=["empty", "header-only"])
def test_prepend_keeps_one_header(history: Repo, existing: str) -> None:
    # As in release.yml: the release PR prepends the next entry to CHANGELOG.md.
    changelog = history.path / "CHANGELOG.md"
    changelog.write_text(existing, encoding="utf-8")
    cliff("--unreleased", "--tag", "v0.1.0", "--prepend", str(changelog))
    history.git("tag", "-a", "v0.1.0", "-m", "Release 0.1.0")
    history.commit("fix: 🐛 a patch (#13)")
    cliff("--unreleased", "--tag", "v0.1.1", "--prepend", str(changelog))

    text = undated(changelog.read_text(encoding="utf-8"))
    assert text == (
        f"{HEADER}\n## 0.1.1 (DATE)\n\n### Fixes\n\n- A patch (#13)\n\n{EXPECTED_0_1_0}"
    )


def test_trailing_key_value_lines_are_dropped_as_trailers(repo: Repo) -> None:
    # The caveat in the README: git-cliff reads `Key: value` lines at the end of a
    # commit message as trailers, so they never reach the migration notes.
    repo.commit("chore: start")
    repo.git("tag", "v0.0.0")
    body = "## Migration\n\nRename the call.\n\nBefore: `old(x)`\nAfter: `new(x)`\n"
    repo.commit(f"feat!: rename old (#1)\n\n{body}")
    notes = cliff("--unreleased")
    assert "  Rename the call." in notes
    assert "Before:" not in notes
    assert "After:" not in notes

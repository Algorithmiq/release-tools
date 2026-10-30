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

"""What the release workflow does at each step: start, plan, backport targets."""

from __future__ import annotations

import os

from release.actions import fail
from release.git import git
from release.tagging import create_tag
from release.versions import (
    RELEASE_BRANCH,
    RELEASE_COMMIT,
    Series,
    final_versions,
    name,
    next_on_branch,
    next_prerelease,
    patches,
    prerelease_numbers,
    previous_line,
    release_branches,
    stage_of,
    tagged_by_start,
)


def refuse_or_promote(series: Series, branch: str, stage: str) -> dict[str, str]:
    """Promote the existing release/X.Y from beta to release candidates, or refuse."""
    version = f"{name(series)}.0"
    current = stage_of(series)
    if stage == "rc" and current == "beta":
        git("fetch", "--quiet", "origin", f"refs/heads/{branch}")
        git("checkout", "--quiet", "--detach", "FETCH_HEAD")
        head = git("rev-parse", "HEAD")
        tag_version = next_prerelease(series, "rc")
        create_tag(tag_version)
        return {
            "action": "promote",
            "series": name(series),
            "branch": branch,
            "version": version,
            "tag_version": tag_version,
            "head": head,
            "summary": f"Promoted {branch} to release candidates: v{tag_version}.",
        }
    if stage == "alpha":
        hint = " Run Release with stage rc to promote it." if current == "beta" else ""
        fail(f"{branch} exists: v{version} is past its alphas.{hint}")
    if current == "beta":
        fail(
            f"{branch} is already in beta: every backport merged into it tags the"
            " next beta. Run Release with stage rc to move it to release candidates."
        )
    if current == "rc":
        fail(
            f"{branch} is already at release candidates: merge its release PR to"
            f" release v{version}."
        )
    fail(
        f"{branch} already exists: that release is already in progress. Merge its"
        f" release PR to release v{version}."
    )


def start(bump: str, stage: str) -> dict[str, str]:
    """Start the release that follows the newest final release, or promote it.

    Alpha: tag the next alpha on HEAD (main). Beta or rc: create release/X.Y at HEAD
    with its first beta or release candidate. Rc on a release in beta: promote it.

    Return the step's outputs.
    """
    finals = final_versions()
    major, minor = finals[-1][:2] if finals else (0, 0)
    series = (major + 1, 0) if bump == "major" else (major, minor + 1)
    branch = f"release/{name(series)}"
    branches = release_branches()
    if series in branches:
        return refuse_or_promote(series, branch, stage)
    if stage == "alpha":
        action, cut = "alpha", ""
    else:
        if unfinished := [s for s in branches if not patches(s)]:
            fail(
                f"release/{name(unfinished[-1])} has no final release yet: release"
                f" it, or delete the branch, before starting {branch}."
            )
        action, cut = "cut", branch
    head = git("rev-parse", "HEAD")
    tag_version = next_prerelease(series, stage)
    create_tag(tag_version, branch=cut)
    summary = (
        f"Started {branch} at v{tag_version}."
        if cut
        else f"Tagged v{tag_version} on main."
    )
    return {
        "action": action,
        "series": name(series),
        "branch": cut,
        "version": f"{name(series)}.0",
        "tag_version": tag_version,
        "head": head,
        "summary": summary,
    }


def backport_targets() -> dict[str, str]:
    """List the branches a backport goes to, and the version each releases next.

    The newest release branch; while its X.Y.0 isn't out, also the newest released one.

    Return the step's outputs.
    """
    branches = release_branches()
    targets = branches[-1:]
    if targets and not patches(targets[0]):
        targets += [s for s in branches if patches(s)][-1:]
    return {
        "branches": " ".join(f"release/{name(s)}" for s in targets),
        "versions": " ".join(f"v{next_on_branch(s)[1]}" for s in targets),
    }


def plan() -> dict[str, str]:
    """Decide what a push to the checked-out release branch should produce.

    Return the step's outputs.
    """
    branch = os.environ.get("GITHUB_REF_NAME") or git(
        "rev-parse", "--abbrev-ref", "HEAD"
    )
    if not (m := RELEASE_BRANCH.match(branch)):
        fail(f"'{branch}' is not a release branch (release/X.Y).")
    series = (int(m[1]), int(m[2]))
    released = patches(series)
    pending = f"{name(series)}.{max(released) + 1 if released else 0}"
    stage, upcoming = next_on_branch(series)

    subject = git("log", "-1", "--format=%s")
    if merged := RELEASE_COMMIT.match(subject):
        # The release PR was just merged: tag the final release.
        if merged[1] != pending:
            fail(f"Release PR says v{merged[1]}, but the next version is v{pending}.")
        if not released and not prerelease_numbers(series, "rc"):
            fail(
                f"v{pending} has no release candidate: run Release with stage rc first."
            )
        return {
            "series": name(series),
            "action": "final",
            "tag_version": pending,
            "pending": pending,
            "stage": "released",
            "previous": "" if released else previous_line(series),
        }
    elif stage != "released" and not tagged_by_start(series):
        # X.Y.0 isn't out yet: every change gets the next beta or release candidate.
        return {
            "series": name(series),
            "action": "prerelease",
            "tag_version": upcoming,
            "pending": pending,
            "stage": stage,
            "previous": "",
        }
    else:
        # Only open or update the release PR: X.Y.0 is out (the next patch), or
        # `start` already tagged HEAD.
        return {
            "series": name(series),
            "action": "pr",
            "tag_version": "",
            "pending": pending,
            "stage": stage,
            "previous": "",
        }

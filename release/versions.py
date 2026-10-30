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

"""Versions from tags and branches: final releases, pre-releases, release lines."""

from __future__ import annotations

import re

from release.git import git

FINAL_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
RELEASE_BRANCH = re.compile(r"^release/(\d+)\.(\d+)$")
# Squash-merged release PRs: "chore: release v0.5.0 (#42)"
RELEASE_COMMIT = re.compile(r"^chore: release v(\S+?)(?: \(#\d+\))?$")
# Pre-releases of X.Y.0 (alphas, betas, release candidates), in PEP 440's spelling.
# Patch releases never have them.
PRERELEASE_TAG = re.compile(r"^v(\d+)\.(\d+)\.0(a|b|rc)(\d+)$")
# The stages of a release before X.Y.0, in order, and their tag suffixes.
SUFFIXES = {"alpha": "a", "beta": "b", "rc": "rc"}

type Series = tuple[int, int]


def all_tags() -> list[str]:
    """Return every tag starting with `v`."""
    return git("tag", "--list", "v*").split()


def final_versions() -> list[tuple[int, int, int]]:
    """Return the versions of the final release tags (vX.Y.Z), oldest first."""
    return sorted(
        (int(m[1]), int(m[2]), int(m[3]))
        for tag in all_tags()
        if (m := FINAL_TAG.match(tag))
    )


def name(series: Series) -> str:
    """Return SERIES as X.Y."""
    return f"{series[0]}.{series[1]}"


def patches(series: Series) -> list[int]:
    """Return the patch numbers of the final releases of SERIES, lowest first."""
    return [p for (x, y, p) in final_versions() if (x, y) == series]


def prerelease_numbers(series: Series, stage: str) -> list[int]:
    """Return the numbers of the STAGE tags of X.Y.0, lowest first."""
    suffix = SUFFIXES[stage]
    return sorted(
        int(m[4])
        for tag in all_tags()
        if (m := PRERELEASE_TAG.match(tag))
        and (int(m[1]), int(m[2])) == series
        and m[3] == suffix
    )


def stage_of(series: Series) -> str:
    """Return how far SERIES got: released, rc, beta, alpha or none."""
    if patches(series):
        return "released"
    for stage in ("rc", "beta", "alpha"):
        if prerelease_numbers(series, stage):
            return stage
    return "none"


def next_prerelease(series: Series, stage: str) -> str:
    """Return the version of the next STAGE pre-release of X.Y.0."""
    number = max(prerelease_numbers(series, stage), default=0) + 1
    return f"{name(series)}.0{SUFFIXES[stage]}{number}"


def release_branches() -> list[Series]:
    """Return the series of the release/X.Y branches on origin, oldest first."""
    lines = git("ls-remote", "--heads", "origin", "release/*").splitlines()
    return sorted(
        (int(m[1]), int(m[2]))
        for line in lines
        if (m := RELEASE_BRANCH.match(line.split("refs/heads/", 1)[-1]))
    )


def next_on_branch(series: Series) -> tuple[str, str]:
    """Return the stage of release/X.Y and the version its next change produces."""
    if released := patches(series):
        return "released", f"{name(series)}.{max(released) + 1}"
    stage = stage_of(series)
    if stage not in {"beta", "rc"}:
        stage = "rc"  # A branch cut by release-tools 1.1 or earlier.
    return stage, next_prerelease(series, stage)


def previous_line(series: Series) -> str:
    """Return X.Y of the newest released branch before SERIES, or an empty string."""
    older = [s for s in release_branches() if s < series and patches(s)]
    return name(older[-1]) if older else ""


def tagged_by_start(series: Series) -> bool:
    """Return whether HEAD already has a beta or release candidate tag of SERIES.

    `start` tags the first beta or release candidate itself when it cuts the branch or
    promotes it. With version files the tag points to a commit on top of HEAD that only
    records the version.
    """
    head = git("rev-parse", "HEAD")
    for tag in all_tags():
        m = PRERELEASE_TAG.match(tag)
        if not m or (int(m[1]), int(m[2])) != series or m[3] == "a":
            continue
        commit = git("rev-parse", f"{tag}^{{commit}}")
        recorded = git("log", "-1", "--format=%P %s", commit)
        if commit == head or recorded == f"{head} chore: set version {tag[1:]}":
            return True
    return False

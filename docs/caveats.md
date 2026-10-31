# Caveats

- **Trailers.** git-cliff reads `Key: value` lines at the end of a commit message as git
  trailers and drops them from the body. A PR description that ends with its Migration
  section, or whose notes end with `Before: …` / `After: …` lines, loses those lines from
  the changelog. Keep the Migration section above a later heading of the template, and
  write before/after examples as code blocks. (`tests/test_cliff.py` pins this behaviour.)
- **The changelog PR merges itself, without a review or its checks.** After a final
  release the bot opens a PR adding the release's section of `CHANGELOG.md` to `main`
  and merges it at once with its bypass of the `main` ruleset (`gh pr merge --admin`):
  the section was already reviewed in the release PR, and CI runs on `main` after the
  merge. Without the bypass ([Per-repository setup](repository-setup.md), step 8) the
  job enables auto-merge instead, with a warning, and the PR waits for an approval:
  auto-merge never bypasses a ruleset. If a changelog PR conflicts (two finals released
  close together), re-run its "Release" workflow run's sync job: it checks out `main`,
  rebuilds `changelog/vX.Y.Z` from the current `main` with `git checkout -B`, and
  force-pushes it.
- **Check names.** The PR checks report as `PR checks / PR title` and
  `PR checks / Migration notes`. A repository that required the contexts `PR title` and
  `Migration notes` of its own copy must switch its rulesets to the new names right after
  merging the stub: `pull_request_target` runs the workflow file of `main`, so the PR
  adding the stub still reports the old names, and every later PR the new ones.
- **Workflows on `release:` events no longer run.** `publish-release` publishes the
  GitHub release with `GITHUB_TOKEN`, and events caused by `GITHUB_TOKEN` start no
  workflows. A workflow that ran on `release: published` (tests, a container image,
  documentation) runs on `push: tags: ["v*"]` instead, or becomes a job of the publish
  workflow that `publish_release` needs.
- **`job.workflow_*` is GitHub.com-only** (not on GitHub Enterprise Server), and
  actionlint 1.7.12 doesn't know it yet: [`.github/actionlint.yaml`](https://github.com/Algorithmiq/release-tools/blob/main/.github/actionlint.yaml)
  ignores the two properties in `release.yml` and `backport.yml`. Consumers' stubs don't
  use it.
- **The release and backport jobs check release-tools out into `.release-tools/`** inside
  the caller's working tree. It is never added to a commit: the workflow only adds
  `CHANGELOG.md` and the version files, and excludes `.release-tools/` via
  `.git/info/exclude`.
- **An older release line runs its own version of the workflows.** Each push to
  `release/X.Y` runs the workflow files of that branch, whose stub pins the release-tools
  version of the time the branch was created. A patch release of an older line therefore
  runs that older release-tools (for release-tools itself: its own older workflows), with
  that version's behaviour and texts. Bump the pin on an older line only if its patch
  releases need a fix of release-tools.
- **Changelog entries of backports link the backport PR.** The changelog lists the PR
  that was squash-merged into each branch: a fix backported to two lines appears as, say,
  `#15` under one and `#16` under the other, not as the original PR on `main`. Each
  backport PR's description links the original ("Backport of #14").
- **Concurrency.** The release jobs queue per ref in the group `release-<ref>` of the
  calling repository. A promotion runs in `main`'s group, so a backport merged into
  `release/X.Y` at the same moment may briefly leave the release PR or a beta tag out of
  step; the next push to the branch puts the PR right.

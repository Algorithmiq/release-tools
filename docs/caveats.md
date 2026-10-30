# Caveats

- **Trailers.** git-cliff reads `Key: value` lines at the end of a commit message as git
  trailers and drops them from the body. A PR description that ends with its Migration
  section, or whose notes end with `Before: …` / `After: …` lines, loses those lines from
  the changelog. Keep the Migration section above a later heading of the template, and
  write before/after examples as code blocks. (`tests/test_cliff.py` pins this behaviour.)
<<<<<<< HEAD
- **Auto-merge of the changelog PR.** After a final release the bot opens a PR adding the
  release's section of `CHANGELOG.md` to `main` and enables auto-merge. Whether
  auto-merge honours the bot's ruleset bypass (instead of waiting for a review) is
  **unverified**. If the PR waits, approve it by hand and update this note. If a
  changelog PR conflicts (two finals released close together), re-run its "Release"
  workflow run's sync job: it checks out `main`, rebuilds `changelog/vX.Y.Z` from the
  current `main` with `git checkout -B`, and force-pushes it.
=======
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
>>>>>>> 8fa438d (fix(workflows): 🐛 merge the changelog PR with the bot's ruleset bypass (#21))
- **Check names.** The PR checks report as `PR checks / PR title` and
  `PR checks / Migration notes`. A repository that required the contexts `PR title` and
  `Migration notes` of its own copy must switch its rulesets to the new names right after
  merging the stub: `pull_request_target` runs the workflow file of `main`, so the PR
  adding the stub still reports the old names, and every later PR the new ones.
- **`job.workflow_*` is GitHub.com-only** (not on GitHub Enterprise Server), and
  actionlint 1.7.12 doesn't know it yet: [`.github/actionlint.yaml`](https://github.com/Algorithmiq/release-tools/blob/main/.github/actionlint.yaml)
  ignores the two properties in `release.yml` and `backport.yml`. Consumers' stubs don't
  use it.
- **The release and backport jobs check release-tools out into `.release-tools/`** inside
  the caller's working tree. It is never added to a commit: the workflow only adds
  `CHANGELOG.md` and the version files, and excludes `.release-tools/` via
  `.git/info/exclude`.
- **Concurrency.** The release jobs queue per ref in the group `release-<ref>` of the
  calling repository. A promotion runs in `main`'s group, so a backport merged into
  `release/X.Y` at the same moment may briefly leave the release PR or a beta tag out of
  step; the next push to the branch puts the PR right.

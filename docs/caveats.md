# Caveats

- **Footers.** git-cliff ends the body of a commit at the first line that looks like a
  footer (`Closes #12`, `**Docs:** …`, `Before: …`) and puts the rest into the footers.
  `cliff.toml` therefore takes the Migration section from the whole message. Up to
  v1.5.0 it took it from the body, so a description with such a line above the section
  lost its notes: the release notes and `CHANGELOG.md` of v1.5.0 were repaired by hand.
- **Changelog entries come from the PR descriptions.** GitHub's web UI wraps the body of
  a squash commit at 72 columns, which breaks the indented lines of a Migration section
  (a Python snippet fails with `IndentationError`) and the text that continues a list
  item. The release PR and the release notes of a pre-release therefore replace each
  commit's body by the description of its PR, with `git cliff --context`, the
  `release pr-descriptions` command and `git cliff --from-context`. One GraphQL query per
  100 commits looks up the PR number that ends the commit's title (`(#12)`); the
  description counts only if the PR is merged and its merge commit is that commit.
  - If the API fails (a rate limit, a token without `pull-requests: read`), the PR is not
    found or it is not that commit's (a commit cherry-picked by hand keeps the original
    title and number), the commit keeps its own body and a warning in the job log names
    the commit and the PR. A commit pushed without a PR keeps its body as well.
  - A description edited after the merge reaches the next generated changelog: the
    release PR regenerates `CHANGELOG.md` only when something is pushed to the release
    branch (re-run the "Release" run of the last push to refresh it). It never reaches a
    release that is published.
  - A backport PR's description starts with "Backport of #N to `release/X.Y`." and
    continues with the description of the original, so a backported entry keeps its
    Migration section.
  - Local previews (`just changelog`) and runs without `GITHUB_REPOSITORY` read the
    commit bodies, as before.
  - A `BREAKING CHANGE:` footer that is only in the commit body no longer counts: mark
    breaking changes with `!` in the title, as the process says.
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
- **Linters and formatters see a generated `CHANGELOG.md`.** The bot's release and
  changelog PRs write it from the PR descriptions, Migration code blocks included. A
  repository that adopted release-tools before v1.5.0 may still check the file with
  `ruff format` (which formats Python blocks in Markdown), a Markdown linter or a spell
  checker; a bot PR then fails a required check. Leave the file out of them, as
  [Adopting release-tools](adopting.md#linters-and-formatters-leave-out-changelogmd)
  shows.
- **Development tags on `main`.** Final tags are created on `release/X.Y` and never
  reach `main`'s history. After `X.Y.0`, the bot therefore tags the commit that the
  changelog PR adds to `main` with `vX.(Y+1).0.dev0`, so that `git describe`,
  setuptools-scm, hatch-vcs and copier see `main` above `X.Y.0` (for example
  `1.3.0.dev2+g1234567`). A `.dev` version is a pre-release under PEP 440: pip, uv and
  copier ignore it unless asked for pre-releases. Nothing publishes it, but it is a `v*`
  tag: every workflow on `push: tags` must exclude it with `"!v*.dev*"`, as the stubs do.
  Otherwise the publish workflow runs for it, and the `release-notes` action fails with
  that hint. The tag needs the changelog PR merged: if the bot can't merge it at once
  (auto-merge or a merge by hand), the job warns, and versions derived from `main` stay
  below `X.Y.0` until the PR merges and the job's "Release" run is re-run, or until the
  next alpha. The tag says `X.(Y+1)` even if the next release turns out to be a major
  one: it still sorts above `X.Y.0` and below every pre-release of the next release.
  Refer to [Branching model](branching-model.md#versions-of-main) for the version of
  `main` at each step of a release cycle. It also shows the steps where this version is
  lower than the release line.
- **Check names.** The PR checks report as `PR checks / PR title` and
  `PR checks / Migration notes`. A repository that required the contexts `PR title` and
  `Migration notes` of its own copy must switch its rulesets to the new names right after
  merging the stub: `pull_request_target` runs the workflow file of `main`, so the PR
  adding the stub still reports the old names, and every later PR the new ones.
- **Workflows on `release:` events no longer run.** `publish-release` publishes the
  GitHub release with `GITHUB_TOKEN`, and events caused by `GITHUB_TOKEN` start no
  workflows. A workflow that ran on `release: published` (tests, a container image,
  documentation) runs on `push: tags: ["v*", "!v*.dev*"]` instead, or becomes a job of the publish
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
- **The notes of a final release are the section of `CHANGELOG.md` at the tag.** They
  carry the wording fixes made in the release PR. A fix to `CHANGELOG.md` made after the
  merge, on `main` or anywhere else, does not reach a published release: its notes are
  immutable. A repository whose release PRs do not add a section for the tag (for
  example, one that never committed `CHANGELOG.md`) gets a warning, and the notes come
  from the commits with `git cliff --current`.
- **Concurrency.** The release jobs queue per ref in the group `release-<ref>` of the
  calling repository. A promotion runs in `main`'s group, so a backport merged into
  `release/X.Y` at the same moment may briefly leave the release PR or a beta tag out of
  step; the next push to the branch puts the PR right.

# Open questions

- **Visibility of release-tools** (public preferred). Everything works either way; see
  [One-time organisation setup](organisation-setup.md) for what an internal or
  private repository needs.
- **A license policy for proprietary packages.** `license-check` has one preset,
  `open-source`. Packages shipped to customers under a commercial license may need a
  stricter one (no LGPL, say), which the legal team must agree before it becomes a
  preset; until then such a repository passes its own grant configuration.
- **Dependabot and pre-releases.** Whether Dependabot proposes `vX.Y.0aN`, `bN` or `rcN`
  tags of release-tools as updates is untested: it shows only in a repository that pins
  release-tools while one of its pre-releases is out. If it does, add an `ignore` rule for
  them. The same goes for the development tags `vX.Y.0.dev0` that release-tools, like
  every adopting repository, has on `main` after each `X.Y.0`.

## Decided

- **Versions of `main` during a release cycle: we accept the problem.** After each
  `X.Y.0`, the version of `main` changes to `X.(Y+1).0.dev0`. But from the freeze to the
  next final release, this version is lower than the versions of the release line. With
  version files, it is lower from the first pre-release
  ([Branching model](branching-model.md#known-problems)).

  Only local development and tests use builds of `main`, and no release comes from
  `main`. Version files matter only for Nix builds, and only some public repositories
  have them. Thus the problem is small, and we do not correct it. We examined these
  solutions and did not use them:
  - **Change `main` at the cut.** The stage that creates `release/X.Y` also opens a PR to
    `main`. This PR writes `X.(Y+1).0.dev0` into the version files, and the bot tags the
    commit that the PR adds. This adds one PR for each release. A repository without
    version files has nothing to write.
  - **Tag each push to `main`.** The release stub also starts on `push` to `main`. A job
    tags the pushed commit with `vX.(Y+1).0.dev0` when the history of `main` has no tag of
    its series. This series is the one after the newest final release or release branch.
    The cost is one short job for each merge to `main`, and a change to each release
    stub. This solution does not help version files
    ([#57](https://github.com/Algorithmiq/release-tools/issues/57)).
  - **Tag `main` at each pre-release of the release line.** This needs no new trigger,
    but the commits between the cut and the next pre-release keep the incorrect version.
  - **setuptools-scm's `release-branch-semver` scheme.** It increases the minor version
    on every branch that is not a release branch. Thus the version of `main` is incorrect
    during the alphas, and so is the version of a release branch that CI checks out
    without a branch name.

## Answered by the v1.2.0 release

release-tools released v1.2.0 through two betas, a release candidate and the final, with
v1.1.1 shipped from the previous line in between. That answered:

- **Auto-merge of the changelog PR** doesn't bypass review: the PR waited for an
  approval. The bot now merges it with its ruleset bypass instead; see
  [Caveats](caveats.md).
- **`job.workflow_*` on real runs** resolve to release-tools at the pinned commit, so the
  jobs run the release package and `cliff.toml` of the same version as the workflows.
- **Pages builds after `mike deploy --push`** with `GITHUB_TOKEN`: the push triggers
  "pages build and deployment". The very first build, right after Pages is enabled, takes
  a few minutes, and the site returns 404 until it finishes.
- **The backport suggestion comment** works with the bot's *Pull requests: write*
  permission; no *Issues* permission is needed.

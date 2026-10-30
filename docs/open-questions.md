# Open questions

- **Visibility of release-tools** (public preferred). Everything works either way; see
  [One-time organisation setup](organisation-setup.md) for what an internal or
  private repository needs.
- **Dependabot and pre-releases.** Whether Dependabot proposes `vX.Y.0aN`, `bN` or `rcN`
  tags of release-tools as updates is untested: it shows only in a repository that pins
  release-tools while one of its pre-releases is out. If it does, add an `ignore` rule for
  them.

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

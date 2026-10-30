# Open questions

- **Visibility of release-tools** (public preferred). Everything works either way; see
  [One-time organisation setup](organisation-setup.md) for what an internal or
  private repository needs.
- **Does auto-merge of the changelog PR honour the bot's ruleset bypass?** Unverified
  until the first release.
- **`job.workflow_*` on real runs.** Documented and used by GitHub's own gh-aw, but not
  yet exercised by this repository; the first run of release-tools' own release workflow
  will show it.
- **Dependabot and pre-releases.** Whether Dependabot proposes `vX.Y.0aN`, `bN` or `rcN`
  tags of release-tools as updates is untested. If it does, add an `ignore` rule for them.

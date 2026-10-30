# Patch releases

Patch releases are **not** started from the Release workflow: they come from the
`backport` label.

1. Fix the bug on `main` as usual, with a `fix:` (or `perf:`) PR.
2. Add the **`backport`** label to the PR, before or after merging it. If it is merged
   without the label, the bot comments on it with the versions the label would ship it
   in.
3. The bot cherry-picks the fix onto `release/X.Y` and opens a backport PR with the same
   title. If the cherry-pick conflicts, the PR is a draft with the conflict committed:
   resolve it on that branch and mark it ready. Merging the first backport opens the
   release PR `chore: release vX.Y.Z`; later ones are added to it.
4. Merge the release PR when the fixes should ship. The bot tags `vX.Y.Z`, which is
   published like any release, with no alphas, betas or release candidates.

For example, with `v1.1.0` out, `fix: crash on empty input` is merged into `main`, and a
maintainer adds the `backport` label a day later. The bot opens the backport PR into
`release/1.1`; merging it opens `chore: release v1.1.1`; merging that releases `v1.1.1`.
While `1.2` is in beta or release candidates, the same label also opens a backport PR
into `release/1.2`, which tags its next beta or candidate.

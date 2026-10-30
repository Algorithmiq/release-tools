# Versioning and upgrading

release-tools follows [the release process](process.md) itself and uses [Semantic Versioning](https://semver.org)
from `1.0.0`:

- **Major**: consumers must change something: a stub's inputs, secrets or required
  permissions, the names of the PR checks, or the release behaviour.
- **Minor**: new optional inputs or features, changelog format changes that need no action.
- **Patch**: fixes.

Consumers pin an exact tag (`@v1.2.0`) in all three stubs and in the actions of the
publish workflow, and keep them in step. Dependabot's `github-actions` ecosystem updates
both reusable workflows and actions; group them so that one PR moves every reference:

```yaml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      release-tools:
        patterns:
          - "Algorithmiq/release-tools*"
```

Pre-releases of release-tools (`v1.2.0b1`, `v1.2.0rc1`) are real tags: pin one in a
repository to try a change before it is released. Immutable releases make every published
tag permanent, so a pinned version can never change under a consumer.

## Upgrading to v1.2.0

v1.2.0 brings alphas and betas, and changes visible to existing consumers:

- **Dual backports during every release candidate window.** With the default `stage: rc`,
  every release now has an rc window during which backports go to both lines: the branch
  in pre-release and the newest released branch. The previous line gets a backport PR and
  a patch release PR, which the X.Y.0 final closes.
- **Backport suggestion comment.** Merged `fix` and `perf` PRs without the `backport`
  label get a comment suggesting it.
- **`sync-changelog` adds only the release's own section to `main`.** Wording fixes a
  release PR makes to older sections no longer reach `main`.
- **The stub needs the `stage` input.** Pin v1.2.0 and add `stage:` to the stub's inputs,
  with the same description, type, required and default as in
  [release.yml](../.github/workflows/release.yml).

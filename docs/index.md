# release-tools

The shared release automation of Algorithmiq repositories: release branches,
pre-releases (alphas, betas, release candidates), the release PR, release tags,
backports, the changelog and the PR checks.

Each repository keeps three short caller stubs, its own publish workflow (because that
depends on how the project is built) and a changelog preview recipe. Everything else
lives in release-tools, once, and is pinned by tag.

## Where to start

- **You work in a repository that uses release-tools:** [The release process](process.md),
  then [Releasing](releasing.md) and [Patch releases](patch-releases.md). The
  [branching model](branching-model.md) shows a whole release cycle.
- **You are adopting release-tools in a repository:** [Adopting release-tools](adopting.md),
  [Per-repository setup](repository-setup.md), and once per organisation the
  [One-time organisation setup](organisation-setup.md).
- **You maintain release-tools:** [What is central](central-vs-local.md),
  [Versioning and upgrading](versioning.md), [Design](design.md),
  [Caveats](caveats.md), [Open questions](open-questions.md) and
  [Developing release-tools](developing.md).

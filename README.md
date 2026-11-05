# release-tools

The shared release automation of Algorithmiq repositories: release branches,
pre-releases (alphas, betas, release candidates), the release PR, release tags,
backports, the changelog and the PR checks.

**Documentation: <https://algorithmiq.github.io/release-tools/>** (with a version
selector). The same pages are in [`docs/`](docs), so browsing the tag you pin on GitHub
shows the documentation of that version.

## Quick start

1. Copy the three caller stubs and the publish workflow: [Adopting release-tools](docs/adopting.md).
2. Install the release bot and protect the branches: [Per-repository setup](docs/repository-setup.md)
   (and once per organisation, [One-time organisation setup](docs/organisation-setup.md)).
3. Start a release: **Actions → Release → Run workflow** on `main` ([Releasing](docs/releasing.md)).

Or let a coding agent walk you through it: [the adopt-release-tools skill](docs/adopting.md#let-an-agent-do-it).

## Pages

- [Home](docs/index.md)
- Using it: [The release process](docs/process.md), [Branching model](docs/branching-model.md),
  [Releasing](docs/releasing.md), [Patch releases](docs/patch-releases.md)
- Adopting it: [Adopting release-tools](docs/adopting.md),
  [One-time organisation setup](docs/organisation-setup.md),
  [Per-repository setup](docs/repository-setup.md)
- Reference: [What is central and what stays per repository](docs/central-vs-local.md),
  [Versioning and upgrading](docs/versioning.md), [Caveats](docs/caveats.md),
  [Design](docs/design.md), [Open questions](docs/open-questions.md)
- [Developing release-tools](docs/developing.md)

Licensed under the [Apache License 2.0](LICENSE).

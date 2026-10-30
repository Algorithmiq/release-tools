# What is central and what stays per repository

| Piece | Where | Per-repository input |
| --- | --- | --- |
| Release logic: start a release, alphas, betas and release candidates, the release PR, final tag, the changelog on `main` | [`.github/workflows/release.yml`](../.github/workflows/release.yml) (reusable) | `version-files` |
| Versions, tags, the release PR, the changelog on `main` | [`release/`](../release): `versions`, `tagging`, `changelog`, `workflow`, `release_pr` (standard library only), run by `release.yml` and `backport.yml` | none |
| Changelog format | [`cliff.toml`](../cliff.toml), used by `release.yml`, the `release-notes` action and the local preview | none |
| Backport PRs for the `backport` label, and the suggestion on fixes merged without it | [`.github/workflows/backport.yml`](../.github/workflows/backport.yml) (reusable) | none |
| PR title and migration notes checks | [`.github/workflows/pr-checks.yml`](../.github/workflows/pr-checks.yml) (reusable) | none |
| Release notes for a tag | [`actions/release-notes`](../actions/release-notes/action.yml) (composite) | none |
| Draft GitHub release with files | [`actions/draft-release`](../actions/draft-release/action.yml) (composite) | the files to attach |
| Publish the draft release | [`actions/publish-release`](../actions/publish-release/action.yml) (composite) | none |
| Triggers, permissions, the bot's credentials | each repository's stubs | |
| Build, version check, PyPI upload | each repository's publish workflow (`deploy.yml`) | everything |
| `just changelog` | each repository's `justfile` | none |
| PR template with the Migration section | each repository's `.github/pull_request_template.md` | anything else in it |
| `CHANGELOG.md` | each repository, written by the bot | |

PR titles use the types `feat fix deprecate perf docs refactor test build ci chore style`
in every repository. The first five appear in the changelog; the others are left out
unless they are breaking (`!`). A [gitmoji](https://gitmoji.dev) after the type
(`feat: ✨ add X`, or `:sparkles:`) is optional and stripped from the changelog. The
changelog starts at the newest final tag, so a repository tags `v0.0.0` where it adopts
the process. Each entry ends with an absolute link to its PR (`[#12](https://github.com/…/pull/12)`),
built from `GITHUB_REPOSITORY`: GitHub doesn't autolink `#12` in `CHANGELOG.md`, nor reliably
in release notes. The `just changelog` recipes take the repository from the `origin` remote.

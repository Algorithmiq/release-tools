# The release process

Every repository that adopts release-tools works this way. People only make decisions:
start a release, move it to its next stage, label fixes for backporting, and approve the
changelog. The release bot does the rest.

## Branches

| Branch | Purpose | Lifetime |
| --- | --- | --- |
| `main` | Where all work lands, through squash-merged pull requests. Always releasable. Alphas are tagged here. | Permanent |
| `release/X.Y` | Created at the feature freeze of release `X.Y`: its betas, release candidates, `X.Y.0` and patch releases. Only receives bug fixes backported from `main`. | Until the next minor or major release is final; then it is unsupported |
| `release-pr/X.Y`, `changelog/vX.Y.Z`, backport branches | The bot's branches for its PRs | Managed by the bot |
| Work branches (e.g. `fix/login-timeout`) | One change, one pull request | Deleted after merging |

Patches go to the newest final release. While the next release is in beta or release
candidates, fixes are backported to both; older releases get no fixes, and users upgrade.

## Pull requests

- Branch off `main` and target `main`, bug fixes included. Only the bot opens PRs against
  release branches.
- PRs are squash-merged, so the PR title and description become the commit. The **title
  becomes the changelog entry**, so write it for users: `type: description`, with an
  optional scope (`fix(io): …`), an optional [gitmoji](https://gitmoji.dev) after the
  colon (`fix(io): 🐛 …`, stripped from the changelog), and `!` after the type for a
  breaking change (`feat!: remove the old solver API`).

  | Type | Use for | In the changelog |
  | --- | --- | --- |
  | `feat` | new functionality | Features |
  | `fix` | bug fixes | Fixes |
  | `deprecate` | marking something as deprecated | Deprecations, with the migration notes |
  | `perf` | performance improvements | Performance |
  | `docs` | documentation only | Documentation |
  | `refactor`, `test`, `build`, `ci`, `chore`, `style` | changes users don't notice | no (unless breaking) |

- Breaking changes and deprecations need a `## Migration` section in the PR description
  saying what users have to change, with a before/after example as code blocks. It is
  copied into the changelog under the entry, which lists breaking changes first.
- The PR checks enforce the title format and the Migration section, and re-run when the
  title or description is edited.
- A bug fix that should also reach the current release gets the **`backport`** label,
  before or after merging: see [Patch releases](patch-releases.md). Features are never
  backported.

## Versions

[Semantic versioning](https://semver.org), `MAJOR.MINOR.PATCH`. Patch releases only fix
bugs and never break anything. Before 1.0, a minor release may break existing code; from
1.0 on, only a major release may. Tags carry a `v` prefix (`v0.5.0`, `v0.5.0rc1`).

A release started from the Release workflow (`X.Y.0`, including `0.Y.0` and `1.0.0`) can
have pre-releases, spelled as in [PEP 440](https://peps.python.org/pep-0440/):

| Stage | Tag | On | Pre-1.0 | 1.0 and later |
| --- | --- | --- | --- | --- |
| Alpha: features still landing (optional) | `vX.Y.0aN` | `main` | `v0.5.0a1` | `v1.3.0a1`, `v2.0.0a1` |
| Beta: feature freeze, fixes only (optional) | `vX.Y.0bN` | `release/X.Y` | `v0.5.0b1` | `v1.3.0b1` |
| Release candidate (at least one) | `vX.Y.0rcN` | `release/X.Y` | `v0.5.0rc1` | `v1.3.0rc1` |
| Final | `vX.Y.0` | `release/X.Y` | `v0.5.0` | `v1.3.0` |
| Patch | `vX.Y.Z` | `release/X.Y` | `v0.5.1` | `v1.3.1` |

**Patch releases (`X.Y.Z` with Z > 0) never have alphas, betas or release candidates,
before or after 1.0**: merging their release PR ships them directly.

Public functionality is deprecated before it is removed: it keeps working and emits a
`DeprecationWarning` naming the replacement and the earliest version that removes it, for
at least one minor release (from 1.0 on, until the next major release). The removal is
then a breaking change with migration notes. Names starting with `_` and anything
documented as experimental are exempt.

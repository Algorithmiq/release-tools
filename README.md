# release-tools

The shared release automation of Algorithmiq repositories: release branches, release
candidates, the release PR, release tags, backports, the changelog and the PR checks.
[The release process](#the-release-process) describes how it works for the people using
it; the rest of this README is about adopting and maintaining the automation.

Each repository keeps three short caller stubs, its own publish workflow (because that
depends on how the project is built) and a changelog preview recipe. Everything else lives
here, once, and is pinned by tag.

- [The release process](#the-release-process): branches, pull requests, versions, releases
- [What is central and what stays per repository](#what-is-central-and-what-stays-per-repository)
- [Adopting release-tools](#adopting-release-tools): the stubs to copy
- [Versioning and upgrading](#versioning-and-upgrading)
- [One-time organisation setup](#one-time-organisation-setup)
- [Per-repository setup](#per-repository-setup)
- [Caveats](#caveats)
- [Design](#design): how the central files reach the caller, and why
- [Enforcing the PR checks with an organisation ruleset](#enforcing-the-pr-checks-with-an-organisation-ruleset)
- [Open questions](#open-questions)
- [Developing release-tools](#developing-release-tools), and how it releases itself

## The release process

Every repository that adopts release-tools works this way. People only make decisions:
start a release, label fixes for backporting, and approve the changelog. The release bot
does the rest.

### Branches

| Branch | Purpose | Lifetime |
| --- | --- | --- |
| `main` | Where all work lands, through squash-merged pull requests. Always releasable. | Permanent |
| `release/X.Y` | Stabilising release `X.Y` and shipping its patch releases. Only receives bug fixes backported from `main`. | Until `release/X.Y+1` is created; then it is unsupported |
| `release-pr/X.Y`, `changelog/vX.Y.Z`, backport branches | The bot's branches for its PRs | Managed by the bot |
| Work branches (e.g. `fix/login-timeout`) | One change, one pull request | Deleted after merging |

Only the newest release is supported: older releases get no fixes, and users upgrade.

### Pull requests

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
  before or after merging. The bot cherry-picks the squashed commit onto the newest
  `release/*` branch and opens a backport PR with the same title. If the cherry-pick
  conflicts, the PR is a draft with the conflict committed: resolve it on that branch and
  mark it ready. Features are never backported.

### Versions

[Semantic versioning](https://semver.org), `MAJOR.MINOR.PATCH`. Patch releases only fix
bugs and never break anything. Before 1.0, a minor release may break existing code; from
1.0 on, only a major release may. Release candidates are `X.Y.0rcN`; tags carry a `v`
prefix (`v0.5.0`, `v0.5.0rc1`).

Public functionality is deprecated before it is removed: it keeps working and emits a
`DeprecationWarning` naming the replacement and the earliest version that removes it, for
at least one minor release (from 1.0 on, until the next major release). The removal is
then a breaking change with migration notes. Names starting with `_` and anything
documented as experimental are exempt.

### Releasing

1. **Start.** When `main` is ready, a maintainer checks that no deprecation is due for
   removal and runs **Actions → Release → Run workflow** on `main`, choosing **minor** or
   **major**. The bot creates `release/X.Y`, tags the first release candidate `vX.Y.0rc1`
   (published as a pre-release) and opens the release PR `chore: release vX.Y.0`, which
   holds the version and the new changelog section.
2. **Release candidates.** Until `X.Y.0` is out, every backport merged into
   `release/X.Y` tags the next candidate and updates the release PR. Testing candidates
   is optional (`pip install --pre <package>==X.Y.0rcN`).
3. **Release.** A maintainer reviews the changelog in the release PR and merges it. The
   bot tags `vX.Y.Z`; the repository's publish workflow builds, drafts the GitHub release
   with every file attached, publishes to PyPI and publishes the release, which makes it
   immutable. The bot then copies `CHANGELOG.md` back to `main`.
4. **Patch releases.** After `X.Y.0`, the first backport opens the release PR for
   `X.Y.1`; merge it when the fixes should ship. Patch releases have no candidates.

A published release never changes. A broken one is yanked on PyPI and replaced by a new
patch release. Only the bot creates `v*` tags.

## What is central and what stays per repository

| Piece | Where | Per-repository input |
| --- | --- | --- |
| Release logic: start a release, release candidates, release PR, final tag, changelog copy to `main` | [`.github/workflows/release.yml`](.github/workflows/release.yml) (reusable) | `version-files` |
| Version arithmetic and tagging | [`release.py`](release.py), run by `release.yml` | none |
| Changelog format | [`cliff.toml`](cliff.toml), used by `release.yml`, the `release-notes` action and the local preview | none |
| Backport PRs for the `backport` label | [`.github/workflows/backport.yml`](.github/workflows/backport.yml) (reusable) | none |
| PR title and migration notes checks | [`.github/workflows/pr-checks.yml`](.github/workflows/pr-checks.yml) (reusable) | none |
| Release notes for a tag | [`actions/release-notes`](actions/release-notes/action.yml) (composite) | none |
| Draft GitHub release with files | [`actions/draft-release`](actions/draft-release/action.yml) (composite) | the files to attach |
| Publish the draft release | [`actions/publish-release`](actions/publish-release/action.yml) (composite) | none |
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
the process.

## Adopting release-tools

Copy these files, replace `v1.0.0` with the current release of release-tools, and use the
same tag everywhere. The triggers stay in the stubs: only a repository's own workflow
files react to its events. The bot's client ID and private key are passed explicitly
rather than through `vars` inheritance or `secrets: inherit`: the reusable workflows
declare them as a required input and a required secret, so a stub that forgets one fails
before anything runs, and no other secret of the repository reaches release-tools.

### `.github/workflows/release.yml`

Set `version-files` to the files that hold the version number, such as `VERSION` or
`pyproject.toml` (whose `[project]` version is updated). Leave it empty if the version
comes from the git tag (setuptools-scm, hatch-vcs).

```yaml
# Releases: see https://github.com/Algorithmiq/release-tools#readme
name: Release

on:
  workflow_dispatch:
    inputs:
      bump:
        description: "Kind of release to start"
        type: choice
        options: [minor, major]
        default: minor
  push:
    branches: ["release/**"]
    tags: ["v*"]

permissions:
  contents: read

jobs:
  release:
    uses: Algorithmiq/release-tools/.github/workflows/release.yml@v1.0.0
    with:
      client-id: ${{ vars.RELEASE_BOT_CLIENT_ID }}
      bump: ${{ inputs.bump }}
      # Files that hold the version (e.g. "VERSION pyproject.toml"); empty if it
      # comes from the git tag (setuptools-scm, hatch-vcs).
      version-files: ""
    secrets:
      private-key: ${{ secrets.RELEASE_BOT_PRIVATE_KEY }}
```

### `.github/workflows/backport.yml`

```yaml
# Backports: see https://github.com/Algorithmiq/release-tools#readme
name: Backport

on:
  pull_request_target:
    types: [closed, labeled]

permissions:
  contents: read

jobs:
  backport:
    uses: Algorithmiq/release-tools/.github/workflows/backport.yml@v1.0.0
    with:
      client-id: ${{ vars.RELEASE_BOT_CLIENT_ID }}
    secrets:
      private-key: ${{ secrets.RELEASE_BOT_PRIVATE_KEY }}
```

### `.github/workflows/pr-checks.yml`

```yaml
# PR title and migration notes: see https://github.com/Algorithmiq/release-tools#readme
name: PR checks

on:
  pull_request_target:
    types: [opened, edited, reopened, synchronize]

permissions:
  pull-requests: read

jobs:
  # Reports the checks "PR checks / PR title" and "PR checks / Migration notes".
  pr-checks:
    name: PR checks
    uses: Algorithmiq/release-tools/.github/workflows/pr-checks.yml@v1.0.0
```

The checks report as **PR checks / PR title** and **PR checks / Migration notes** (a
called workflow's jobs are named `<caller job name> / <job name>`). Those are the names to
require in the rulesets.

### The publish workflow

It must follow this structure: run on `push: tags: ["v*"]`, build and
check that the built version matches the tag, create a **draft** GitHub release with every
file attached, publish to PyPI with Trusted Publishing, and publish the GitHub release last.
The build stays the repository's own; the three release steps are actions from here. The
`release-notes` action needs the full history and tags (`fetch-depth: 0`), and the release
jobs need `contents: write`. A complete example:

```yaml
# Publishing: see https://github.com/Algorithmiq/release-tools#readme
#
# Runs on the v* tags that the release workflow pushes: build, draft the GitHub release
# with every file attached, publish to PyPI, then publish the GitHub release, which makes
# it immutable. Never on `release: published`. Only the build job is repository-specific.
name: Publish

on:
  push:
    tags: ["v*"]

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  # A publish run must never be cut short half-way through.
  cancel-in-progress: false

jobs:
  build:
    name: Build sdist and wheel
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7.0.1
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v10.3.2
      - name: Build distributions
        run: uv build --out-dir dist
      - name: Check the version matches the release tag
        run: |
          expected="${GITHUB_REF_NAME#v}"
          wheels=(dist/*.whl)
          actual="$(basename "${wheels[0]}" | cut -d- -f2)"
          if [[ "$actual" != "$expected" ]]; then
            echo "::error::built version is '$actual', but the release tag is '$expected'"
            exit 1
          fi
      - uses: actions/upload-artifact@v7.0.2
        with:
          name: dist
          path: dist/*

  draft_release:
    # Immutable releases: files can only be attached while the release is a draft.
    name: Create the draft GitHub release
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v7.0.1
        with:
          fetch-depth: 0  # git-cliff needs the full history and the tags
      - uses: actions/download-artifact@v8.0.2
        with:
          name: dist
          path: dist
      - id: notes
        uses: Algorithmiq/release-tools/actions/release-notes@v1.0.0
      - uses: Algorithmiq/release-tools/actions/draft-release@v1.0.0
        with:
          notes-file: ${{ steps.notes.outputs.path }}
          files: |
            dist/*

  upload_pypi:
    name: Upload to PyPI
    needs: draft_release
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
      attestations: write
      contents: read
    steps:
      - uses: actions/download-artifact@v8.0.2
        with:
          name: dist
          path: dist
      - uses: actions/attest-build-provenance@v4.2.2
        with:
          subject-path: "dist/*"
      - uses: pypa/gh-action-pypi-publish@v1.14.3

  publish_release:
    # Publishing locks the tag and the files and creates GitHub's release attestation.
    name: Publish the GitHub release
    needs: upload_pypi
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: Algorithmiq/release-tools/actions/publish-release@v1.0.0
```

`release-notes` writes the tag's changelog entry for a final release
(`git cliff --current`) and everything since the last final release for a release
candidate (`git cliff --unreleased --tag vX.Y.ZrcN`), and outputs the file's `path`.
`draft-release` takes `notes-file` and `files` (one glob per line, each must match), and
marks release candidates as pre-releases. `publish-release` publishes the draft. All three
default to the tag that triggered the run (`tag` input) and to `github.token` (`token`
input), and need `pipx`, which GitHub-hosted runners have.

### `justfile`: preview the changelog

`just changelog` shows what the next release's entry will look like, with the central
`cliff.toml` at the version the stubs pin (read from `release.yml`, so Dependabot's updates
carry over). If release-tools is public:

```just
git_cliff := "git-cliff==2.14.2"

# Preview the changelog entry of the next release, with the central cliff.toml at the version release.yml pins.
changelog:
    #!/usr/bin/env bash
    set -euo pipefail
    ref=$(sed -nE 's|.*Algorithmiq/release-tools/.github/workflows/release.yml@([^[:space:]]+).*|\1|p' \
        .github/workflows/release.yml)
    uvx --from {{ git_cliff }} git-cliff --unreleased \
        --config-url "https://raw.githubusercontent.com/Algorithmiq/release-tools/$ref/cliff.toml"
```

`--config-url` only works for a public repository. If release-tools is internal or private,
fetch the file with the GitHub CLI instead (any member who has run `gh auth login`):

```just
git_cliff := "git-cliff==2.14.2"

# Preview the changelog entry of the next release, with the central cliff.toml at the version release.yml pins.
changelog:
    #!/usr/bin/env bash
    set -euo pipefail
    ref=$(sed -nE 's|.*Algorithmiq/release-tools/.github/workflows/release.yml@([^[:space:]]+).*|\1|p' \
        .github/workflows/release.yml)
    # release-tools isn't public: fetch cliff.toml with the GitHub CLI (`gh auth login`).
    config="$(mktemp -d)/cliff.toml"
    gh api -H "Accept: application/vnd.github.raw" \
        "repos/Algorithmiq/release-tools/contents/cliff.toml?ref=$ref" > "$config"
    uvx --from {{ git_cliff }} git-cliff --unreleased --config "$config"
```

### PR template

The changelog copies the PR description's `## Migration` section, **up to the next `## `
heading**, into the entry of a breaking change or deprecation. Keep the section above any
later heading of the template (such as a checklist), so that only the notes are copied, and
never make it the last thing in the description (see [Caveats](#caveats)):

```markdown
<!-- Keep this section above the Checklist: the changelog takes everything up to the next heading. -->
## Migration
<!-- Required for breaking changes (!) and deprecations. Delete otherwise.
     What do users need to change? Show a before/after example if possible. -->

## Checklist
```

## Versioning and upgrading

release-tools follows [the release process](#the-release-process) itself and uses [Semantic Versioning](https://semver.org)
from `1.0.0`:

- **Major**: consumers must change something: a stub's inputs, secrets or required
  permissions, the names of the PR checks, or the release behaviour.
- **Minor**: new optional inputs or features, changelog format changes that need no action.
- **Patch**: fixes.

Consumers pin an exact tag (`@v1.0.0`) in all three stubs and in the actions of the
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

Release candidates of release-tools (`v1.1.0rc1`) are real tags: pin one in a repository to
try a change before it is released. Immutable releases make every published tag permanent,
so a pinned version can never change under a consumer.

## One-time organisation setup

An organisation owner does this once. The commands need `gh` with the `admin:org` scope
(`gh auth refresh -h github.com -s admin:org`) and `jq`.

1. **Create the release bot GitHub App** (web UI only):
   <https://github.com/organizations/Algorithmiq/settings/apps/new>.
   - Name `algorithmiq-release-bot`; homepage `https://github.com/Algorithmiq`; webhook
     **not** active.
   - Repository permissions: **Contents** read and write (release branches, tags, the
     changelog), **Pull requests** read and write (release, backport and changelog PRs,
     auto-merge), **Workflows** read and write (pushing branches whose commits touch
     `.github/workflows/`). Metadata read-only is added automatically. Nothing else, no
     events. Installable only on this account.
   - Note the **App ID** (a number, for the rulesets) and the **Client ID** (`Iv23…`, for
     the workflows). Generate a **private key** and keep the `.pem` only until step 2.
   - **Install** it on `release-tools` and on every repository that adopts the process.
     release-tools needs it for its own releases, and the release workflow uses it to read
     release-tools when that repository is not public.
2. **Store the credentials** for the repositories that use them, release-tools included
   (`--repos` replaces the list, so always pass all of them):

   ```bash
   gh variable set RELEASE_BOT_CLIENT_ID --org Algorithmiq --visibility selected \
     --repos release-tools,AEGISS --body "$CLIENT_ID"
   gh secret set RELEASE_BOT_PRIVATE_KEY --org Algorithmiq --visibility selected \
     --repos release-tools,AEGISS < algorithmiq-release-bot.*.private-key.pem
   ```

3. **Allow the actions.** If the organisation restricts which actions and reusable
   workflows may run, allow `Algorithmiq/release-tools/*` and the actions it uses
   (`actions/checkout`, `actions/create-github-app-token`,
   `amannn/action-semantic-pull-request`, `korthout/backport-action`). The allow list of
   the calling repository applies to everything a reusable workflow uses.
4. **Visibility of release-tools.** Public is simplest and preferred. If it is internal or
   private instead:
   - release-tools → Settings → Actions → General → **Access**: "Accessible from
     repositories in the 'Algorithmiq' organization". Without it, no other repository can
     call its workflows or actions.
     ([docs](https://docs.github.com/en/actions/how-tos/reuse-automations/share-with-your-organization))
   - A public repository can only call public workflows, so release-tools must be public
     as soon as any public repository adopts it.
     ([docs](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations#access-to-reusable-workflows))
   - "Internal" exists only with GitHub Enterprise Cloud; otherwise it is private.
   - Dependabot needs access to release-tools to update the pins: add it to the
     organisation's "Grant Dependabot access to private repositories" list (in the
     organisation's code security settings).
   - Local changelog previews use the `gh` variant of `just changelog`.

   Nothing in the workflows changes: they read release-tools with a read-only token of the
   release bot either way (see [Design](#design)).

## Per-repository setup

A repository admin does this when a repository adopts the process. Set
`REPO=Algorithmiq/<name>` and `APP_ID=<the App ID>` first. Steps 1 to 7 come before
merging the PR that adds the stubs, 8 after it.

1. **Install the app and share the credentials** with the repository: add it to the app's
   installation (Organisation settings → GitHub Apps → algorithmiq-release-bot →
   Configure), and to the `--repos` lists of the variable and the secret.
2. **Tag `v0.0.0`, the start of the changelog**, on the last commit that should not appear
   in it, before the tag ruleset (step 5) exists. The first release is then `0.1.0` (or
   `1.0.0` when started with **major**).

   ```bash
   git tag -a v0.0.0 -m "Start of the changelog" <commit>
   git push origin v0.0.0
   just changelog    # what the first release will contain
   ```

3. **Settings.** Squash-merge only, with the PR title and description as the commit
   message (otherwise the migration notes never reach the changelog), auto-merge, automatic
   deletion of head branches, immutable releases, and the `backport` label:

   ```bash
   gh api -X PATCH repos/$REPO -F allow_squash_merge=true -F allow_merge_commit=false \
     -F allow_rebase_merge=false -F allow_auto_merge=true -F delete_branch_on_merge=true \
     -f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=PR_BODY
   gh api -X PUT repos/$REPO/immutable-releases
   gh label create backport -R $REPO --color B60205 \
     --description "Also ship this fix in the current release"
   ```

4. **Files.** The three stubs, the publish workflow, the `justfile` recipe, the Migration
   section of the PR template, an empty `CHANGELOG.md` if there is none, and the
   Dependabot group. Delete any local copies of `release.py` and `cliff.toml`.
5. **Tag ruleset**: only the release bot creates, moves or deletes `v*` tags.

   ```bash
   gh api -X POST repos/$REPO/rulesets --input - <<EOF
   {"name": "release tags", "target": "tag", "enforcement": "active",
    "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
    "rules": [{"type": "creation"}, {"type": "update"}, {"type": "deletion"}],
    "bypass_actors": [{"actor_id": $APP_ID, "actor_type": "Integration", "bypass_mode": "always"}]}
   EOF
   ```

6. **`release/*` ruleset**: changes only through squash-merged PRs that pass CI, and only
   the bot creates the branches. List the repository's own required checks next to the PR
   checks (`15368` is the GitHub Actions app, which reports them):

   ```bash
   gh api -X POST repos/$REPO/rulesets --input - <<EOF
   {"name": "release branches", "target": "branch", "enforcement": "active",
    "conditions": {"ref_name": {"include": ["refs/heads/release/*"], "exclude": []}},
    "rules": [
     {"type": "creation"}, {"type": "deletion"}, {"type": "non_fast_forward"}, {"type": "required_linear_history"},
     {"type": "pull_request", "parameters": {"allowed_merge_methods": ["squash"], "dismiss_stale_reviews_on_push": true,
       "require_code_owner_review": false, "require_last_push_approval": false,
       "required_approving_review_count": 1, "required_review_thread_resolution": false}},
     {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": true,
       "required_status_checks": [{"context": "PR checks / PR title", "integration_id": 15368},
         {"context": "PR checks / Migration notes", "integration_id": 15368}]}}],
    "bypass_actors": [{"actor_id": $APP_ID, "actor_type": "Integration", "bypass_mode": "always"}]}
   EOF
   ```

7. **PyPI Trusted Publishing** for the publish workflow: on PyPI, add a (pending)
   publisher with the repository, the workflow file name and the environment (`pypi` in
   the example). The first release candidate is published to PyPI straight away.
8. **After the stubs are on `main`: require the PR checks on `main` and let the bot
   bypass the `main` ruleset.** `pull_request_target` runs the workflow file of the base
   branch, so the checks never report until the stub is on `main`; requiring them earlier
   blocks every PR, including the one adding them. The bypass lets the bot's changelog PR
   merge without a review (see [Caveats](#caveats)).

   ```bash
   id=$(gh api repos/$REPO/rulesets --jq '.[] | select(.name == "main") | .id')
   gh api repos/$REPO/rulesets/$id | jq --argjson app "$APP_ID" '{name, target, enforcement, conditions,
     rules: (.rules | map(if .type == "required_status_checks"
       then .parameters.required_status_checks += [{"context": "PR checks / PR title", "integration_id": 15368},
                                                   {"context": "PR checks / Migration notes", "integration_id": 15368}]
       else . end)),
     bypass_actors: (.bypass_actors + [{"actor_id": $app, "actor_type": "Integration", "bypass_mode": "always"}])}' \
   | gh api -X PUT repos/$REPO/rulesets/$id --input -
   ```

   This assumes a `main` ruleset with a `required_status_checks` rule; create one first
   if there is none.

The first release: check that no deprecation is due for removal, then
**Actions → Release → Run workflow** on `main` (or
`gh workflow run release.yml -R $REPO --ref main -f bump=minor`).

## Caveats

- **Trailers.** git-cliff reads `Key: value` lines at the end of a commit message as git
  trailers and drops them from the body. A PR description that ends with its Migration
  section, or whose notes end with `Before: …` / `After: …` lines, loses those lines from
  the changelog. Keep the Migration section above a later heading of the template, and
  write before/after examples as code blocks. (`tests/test_cliff.py` pins this behaviour.)
- **Auto-merge of the changelog PR.** After a final release the bot opens a PR copying
  `CHANGELOG.md` to `main` and enables auto-merge. Whether auto-merge honours the bot's
  ruleset bypass (instead of waiting for a review) is **unverified**. If the PR waits,
  approve it by hand and update this note.
- **Check names.** The PR checks report as `PR checks / PR title` and
  `PR checks / Migration notes`. A repository that required the contexts `PR title` and
  `Migration notes` of its own copy must switch its rulesets to the new names right after
  merging the stub: `pull_request_target` runs the workflow file of `main`, so the PR
  adding the stub still reports the old names, and every later PR the new ones.
- **`job.workflow_*` is GitHub.com-only** (not on GitHub Enterprise Server), and
  actionlint 1.7.12 doesn't know it yet: [`.github/actionlint.yaml`](.github/actionlint.yaml)
  ignores the two properties in `release.yml`. Consumers' stubs don't use it.
- **Release jobs check release-tools out into `.release-tools/`** inside the caller's
  working tree. It is never added to a commit (the workflow only adds `CHANGELOG.md` and
  the version files).
- **Concurrency.** The release jobs queue per ref in the group `release-<ref>` of the
  calling repository.

## Design

### How the central files reach the caller at the pinned version

Inside a reusable workflow the `github` context is the caller's
([docs](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations#github-context)),
so `github.sha` and `github.workflow_ref` say nothing about release-tools. Three options
were considered:

- **(a) `job.workflow_repository` and `job.workflow_sha`**, chosen. The `job` context
  identifies the workflow file that defines the current job; for a reusable workflow, the
  called file. GitHub documents exactly this use: a reusable workflow checking out its
  own repository at `job.workflow_sha`
  ([job context](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#job-context);
  added to the docs in [github/docs#60709](https://github.com/github/docs/pull/60709),
  April 2026; used in production by
  [github/gh-aw](https://github.com/github/gh-aw/blob/main/actions/setup/js/resolve_host_repo.cjs)).
  `release.yml` checks out `${{ job.workflow_repository }}` at `${{ job.workflow_sha }}`,
  the commit of the tag the caller pinned, so the workflow logic, `release.py` and
  `cliff.toml` always come from one ref. It costs the stubs nothing.
- **(b) Composite actions called from the reusable workflow.** A composite action sees its
  files through `github.action_path`, but a reusable workflow calling
  `Algorithmiq/release-tools/<action>@<ref>` must hard-code `<ref>`. The workflow at
  `v1.2.0` would then run actions from whatever tag was written into it, unless every
  release rewrote its own references before tagging, which the release process can't do
  (the tag doesn't exist yet when the release PR is written). Rejected.
- **(c) Consumers calling composite actions directly.** Version-consistent, but each
  stub would carry the jobs, conditions, token steps and checkouts that make up most of
  `release.yml`: about a hundred lines per repository instead of thirty. Rejected.

The checkout of release-tools uses a second token of the release bot, limited to
`contents: read` on release-tools
([`repositories` and `permission-*` inputs](https://github.com/actions/create-github-app-token#inputs)).
For a public release-tools that token isn't needed, but it keeps one code path for every
visibility: an internal or private repository can't be read with the caller's
`GITHUB_TOKEN`, and the Actions **Access** setting only lets the runner download actions
and reusable workflows, not check the repository out
([docs](https://docs.github.com/en/actions/how-tos/reuse-automations/share-with-your-organization)).

`backport.yml` and `pr-checks.yml` need no files from here. The publish actions are
composite actions called directly from the consumer's `deploy.yml`, where the consumer
writes the ref: `release-notes` finds `cliff.toml` at `${{ github.action_path }}/../../cliff.toml`,
which the runner downloads with the action at that ref.

### Secrets and inputs

The stubs pass `client-id` and `private-key` explicitly. `secrets: inherit` would also
work, but would hand every secret of the repository to release-tools and hide which one it
needs. Workflow-level `env` of the caller does not reach a reusable workflow
([docs](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations#limitations-of-reusable-workflows)),
hence the `version-files` input.

## Enforcing the PR checks with an organisation ruleset

An organisation ruleset can **require workflows to pass before merging**, running a
workflow from release-tools in every targeted repository with no stub at all
([docs](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#require-workflows-to-pass-before-merging)).
It is an option, not the default, because of these caveats:

- It needs GitHub Enterprise Cloud.
- Ruleset workflows only run for the default activity types: `opened`, `synchronize` and
  `reopened` for `pull_request_target`; `types` filters are ignored
  ([docs](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/troubleshooting-rules#supported-ruleset-workflow-events)).
  **Editing a PR's title or description does not re-run the checks**, which defeats a
  title check: a fixed title stays red until the next push.
- The enforced file must trigger on `pull_request` or `pull_request_target`, so it would
  be a wrapper such as [`self-pr-checks.yml`](.github/workflows/self-pr-checks.yml) rather
  than the reusable `pr-checks.yml`. Whether its `./.github/workflows/pr-checks.yml`
  reference resolves to release-tools when run as a ruleset workflow in another
  repository is unverified.
- The workflow's repository must be at least as visible as the targeted ones (a public one
  works everywhere), with the Access setting if it isn't public.
- The rule blocks direct pushes on the targeted branches. Rulesets for `release/*` must
  use "Do not require workflow checks on creation" so that the bot can still create the
  branches. PRs opened before the rule only get the checks after their next push.

The upside is central enforcement that a repository can't remove. Reconsider it if the
`edited` limitation is lifted.

## Open questions

- **Visibility of release-tools** (public preferred). Everything works either way; see
  [One-time organisation setup](#one-time-organisation-setup) for what an internal or
  private repository needs.
- **Does auto-merge of the changelog PR honour the bot's ruleset bypass?** Unverified
  until the first release.
- **`job.workflow_*` on real runs.** Documented and used by GitHub's own gh-aw, but not
  yet exercised by this repository; the first run of release-tools' own release workflow
  will show it.
- **Dependabot and release candidates.** Whether Dependabot proposes `vX.Y.ZrcN` tags of
  release-tools as updates is untested. If it does, add an `ignore` rule for them.

## Developing release-tools

```bash
just build    # uv sync: pytest, ruff, ty, prek, git-cliff, shellcheck
just lint     # every hook: ruff, ty, actionlint (+ shellcheck), workflow and action schemas
just test     # release.py, cliff.toml, the actions, and that the examples match
```

- `tests/test_release.py` covers each command of `release.py`;
  `tests/test_release_e2e.py` drives two release series through it the way `release.yml`
  does, against a scratch repository with a local bare `origin`, and runs the release PR
  step of `release.yml` itself with a stand-in for `gh`.
- `tests/test_cliff.py` runs git-cliff 2.14.2 on scratch histories: gitmoji stripping,
  migration notes, blank lines, ignored release candidates, `--current`, `--prepend`.
- `tests/test_actions.py` shellchecks the composite actions and runs them with stand-ins
  for `pipx` and `gh`.
- `tests/test_examples.py` checks that this README, the `examples/` and the dogfooding
  stubs agree, that the stubs pass what the reusable workflows declare, and that every
  reference uses the same release-tools tag and git-cliff version.

Requires Python 3.12 or later: `release.py` runs on the runner's system Python and only
uses the standard library.

### How release-tools releases itself

release-tools follows the same process with its own workflows (dogfooding):
[`self-release.yml`](.github/workflows/self-release.yml),
[`self-backport.yml`](.github/workflows/self-backport.yml) and
[`self-pr-checks.yml`](.github/workflows/self-pr-checks.yml) are the consumer stubs
above with `uses: ./.github/workflows/<file>` instead of a pinned tag, and
[`self-publish.yml`](.github/workflows/self-publish.yml) publishes the GitHub release with
`./actions/*`. A local reference runs the workflow from the same commit as the event, so a
change is exercised by release-tools itself (release candidates included) before any
consumer pins it. Nothing is built or uploaded: the release is the tag and its notes.

It has no version files (`version-files: ""`). Set it up like any other repository (the
per-repository steps above, without PyPI), tag `v0.0.0` on the first commit, and start the
first release with **major** to get `v1.0.0rc1` and then `v1.0.0`.

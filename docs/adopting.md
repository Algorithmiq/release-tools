# Adopting release-tools

Copy these files, replace `v1.2.0` with the current release of release-tools (v1.2.0 or
later: the `stage` input is new in v1.2.0), and use the same tag everywhere. The triggers
stay in the stubs: only a repository's own workflow files react to its events. The bot's client ID and private key are passed explicitly
rather than through `vars` inheritance or `secrets: inherit`: the reusable workflows
declare them as a required input and a required secret, so a stub that forgets one fails
before anything runs, and no other secret of the repository reaches release-tools.

## `.github/workflows/release.yml`

Set `version-files` to the files that hold the version number, such as `VERSION` or
`pyproject.toml` (whose `[project]` version is updated). Leave it empty if the version
comes from the git tag (setuptools-scm, hatch-vcs). `stage` chooses where a release
starts (alpha, beta or rc) and promotes a release in beta to release candidates; see
[Releasing](releasing.md).

```yaml
# Releases: see https://github.com/Algorithmiq/release-tools#readme
name: Release

on:
  workflow_dispatch:
    inputs:
      bump:
        description: "Release to start: next minor or major (patch releases: add the backport label to the fix PR)"
        type: choice
        options: [minor, major]
        default: minor
      stage:
        description: "Stage to start at or promote to (patch releases have no pre-releases)"
        type: choice
        options: [rc, beta, alpha]
        default: rc
  push:
    branches: ["release/**"]
    tags: ["v*"]

permissions:
  contents: read

jobs:
  release:
    uses: Algorithmiq/release-tools/.github/workflows/release.yml@v1.2.0
    with:
      client-id: ${{ vars.RELEASE_BOT_CLIENT_ID }}
      bump: ${{ inputs.bump }}
      stage: ${{ inputs.stage }}
      # Files that hold the version (e.g. "VERSION pyproject.toml"); empty if it
      # comes from the git tag (setuptools-scm, hatch-vcs).
      version-files: ""
    secrets:
      private-key: ${{ secrets.RELEASE_BOT_PRIVATE_KEY }}
```

## `.github/workflows/backport.yml`

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
    uses: Algorithmiq/release-tools/.github/workflows/backport.yml@v1.2.0
    with:
      client-id: ${{ vars.RELEASE_BOT_CLIENT_ID }}
    secrets:
      private-key: ${{ secrets.RELEASE_BOT_PRIVATE_KEY }}
```

## `.github/workflows/pr-checks.yml`

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
    uses: Algorithmiq/release-tools/.github/workflows/pr-checks.yml@v1.2.0
```

The checks report as **PR checks / PR title** and **PR checks / Migration notes** (a
called workflow's jobs are named `<caller job name> / <job name>`). Those are the names to
require in the rulesets.

## The publish workflow

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
        uses: Algorithmiq/release-tools/actions/release-notes@v1.2.0
      - uses: Algorithmiq/release-tools/actions/draft-release@v1.2.0
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
      - uses: Algorithmiq/release-tools/actions/publish-release@v1.2.0
```

`release-notes` writes the tag's changelog entry for a final release
(`git cliff --current`) and everything since the last final release for a pre-release
(`git cliff --unreleased --tag vX.Y.0rcN`), and outputs the file's `path`.
`draft-release` takes `notes-file` and `files` (one glob per line, each must match), and
marks alphas, betas and release candidates as pre-releases. `publish-release` publishes
the draft. All three default to the tag that triggered the run (`tag` input) and to
`github.token` (`token` input), and need `pipx`, which GitHub-hosted runners have.

### Publishing to AWS CodeArtifact

A package for the organisation's private index on AWS CodeArtifact keeps the same
structure. Its upload job assumes the upload role with GitHub's OIDC token and runs
`twine upload`; the `CODEARTIFACT_*` variables come from the organisation
([One-time organisation setup](organisation-setup.md), step 5). A build that needs
private dependencies assumes `vars.CODEARTIFACT_READ_ROLE` the same way before building.

```yaml
# Publishing to AWS CodeArtifact: see https://github.com/Algorithmiq/release-tools#readme
#
# Runs on the v* tags that the release workflow pushes: build, draft the GitHub release
# with every file attached, upload to the organisation's private package index on AWS
# CodeArtifact, then publish the GitHub release, which makes it immutable. Never on
# `release: published`. Only the build job is repository-specific; the CODEARTIFACT_*
# variables are set once for the organisation.
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
        uses: Algorithmiq/release-tools/actions/release-notes@v1.2.0
      - uses: Algorithmiq/release-tools/actions/draft-release@v1.2.0
        with:
          notes-file: ${{ steps.notes.outputs.path }}
          files: |
            dist/*

  upload_codeartifact:
    name: Upload to AWS CodeArtifact
    needs: draft_release
    runs-on: ubuntu-latest
    permissions:
      id-token: write  # assume the upload role with GitHub's OIDC token
      contents: read
    steps:
      - uses: actions/download-artifact@v8.0.2
        with:
          name: dist
          path: dist
      - uses: aws-actions/configure-aws-credentials@v6.3.0
        with:
          role-to-assume: ${{ vars.CODEARTIFACT_WRITE_ROLE }}
          aws-region: ${{ vars.CODEARTIFACT_REGION }}
      - name: Upload with twine
        env:
          DOMAIN: ${{ vars.CODEARTIFACT_DOMAIN }}
          DOMAIN_OWNER: ${{ vars.CODEARTIFACT_DOMAIN_OWNER }}
          REPOSITORY: ${{ vars.CODEARTIFACT_REPOSITORY }}
        run: |
          TWINE_USERNAME=aws
          TWINE_PASSWORD="$(aws codeartifact get-authorization-token \
            --domain "$DOMAIN" --domain-owner "$DOMAIN_OWNER" \
            --query authorizationToken --output text)"
          echo "::add-mask::$TWINE_PASSWORD"
          TWINE_REPOSITORY_URL="$(aws codeartifact get-repository-endpoint \
            --domain "$DOMAIN" --domain-owner "$DOMAIN_OWNER" --repository "$REPOSITORY" \
            --format pypi --query repositoryEndpoint --output text)"
          export TWINE_USERNAME TWINE_PASSWORD TWINE_REPOSITORY_URL
          pipx run twine==7.0.0 upload dist/*

  publish_release:
    # Publishing locks the tag and the files and creates GitHub's release attestation.
    name: Publish the GitHub release
    needs: upload_codeartifact
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: Algorithmiq/release-tools/actions/publish-release@v1.2.0
```

## `justfile`: preview the changelog

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
    # Link the PR numbers like the release PR does: GitHub Actions sets GITHUB_REPOSITORY.
    repo=$(git remote get-url origin | sed -E 's#^.*github\.com[:/]##; s#\.git$##')
    GITHUB_REPOSITORY="${GITHUB_REPOSITORY:-$repo}" uvx --from {{ git_cliff }} git-cliff --unreleased \
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
    # Link the PR numbers like the release PR does: GitHub Actions sets GITHUB_REPOSITORY.
    repo=$(git remote get-url origin | sed -E 's#^.*github\.com[:/]##; s#\.git$##')
    GITHUB_REPOSITORY="${GITHUB_REPOSITORY:-$repo}" uvx --from {{ git_cliff }} git-cliff --unreleased \
        --config "$config"
```

## PR template

The changelog copies the PR description's `## Migration` section, **up to the next `## `
heading**, into the entry of a breaking change or deprecation. Keep the section above any
later heading of the template (such as a checklist), so that only the notes are copied, and
never make it the last thing in the description (see [Caveats](caveats.md)):

```markdown
<!-- Keep this section above the Checklist: the changelog takes everything up to the next heading. -->
## Migration
<!-- Required for breaking changes (!) and deprecations. Delete otherwise.
     What do users need to change? Show a before/after example if possible. -->

## Checklist

- [ ] Bug fix for the current release: add the `backport` label (or ask a maintainer to)
```

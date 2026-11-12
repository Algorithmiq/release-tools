# Adopting release-tools

Copy these files, replace `v1.2.0` with the current release of release-tools (v1.2.0 or
later: the `stage` input is new in v1.2.0), and use the same tag everywhere. The triggers
stay in the stubs: only a repository's own workflow files react to its events. The bot's client ID and private key are passed explicitly
rather than through `vars` inheritance or `secrets: inherit`: the reusable workflows
declare them as a required input and a required secret, so a stub that forgets one fails
before anything runs, and no other secret of the repository reaches release-tools.

## Let an agent do it

Repository admins can hand the adoption to a coding agent with the
`adopt-release-tools` [agent skill](https://agentskills.io), which ships in
[`skills/adopt-release-tools`](https://github.com/Algorithmiq/release-tools/tree/main/skills/adopt-release-tools):

```bash
npx skills add Algorithmiq/release-tools --skill adopt-release-tools
```

or copy that folder into your agent's skills directory. Then ask the agent to adopt
release-tools in your repository. It reads the repository and these pages at the latest
release, writes the files and opens the adoption PR; you run every command that changes
GitHub, from the commands it prepares. It follows this page and
[Per-repository setup](repository-setup.md), which stay the reference.

## `.github/workflows/release.yml`

`version-files` is a list of the files that the release bot updates for each release.
Use an empty value when the version is from the git tags (setuptools-scm, hatch-vcs).
Then each build that can read the tags has the exact version. This includes the wheels.
You do not edit files when you make a release. Add a file to the list only when a build
cannot read the tags but must have a real version:

- **The version is from the tags, and no other file contains it:** `""`.
- **A different file contains the version, and nothing reads that file,** for example a
  `VERSION` file that a person updates: `""`. Remove the file.
- **CMake reads the file,** for a C++ header or a package configuration: `""`. In CMake,
  use the version from the tags:
  - in a scikit-build-core build, use `SKBUILD_PROJECT_VERSION` and
    `SKBUILD_PROJECT_VERSION_FULL`;
  - in a plain CMake build, use `git describe`, or a module that uses it.
- **A build without git metadata reads the file,** usually a Nix derivation: the path of
  the file, for example `"VERSION"`. The derivation builds without `.git`, and gives the
  file to setuptools-scm as `SETUPTOOLS_SCM_PRETEND_VERSION`. The bot writes the file:
  - the commit of each release tag contains the version of that release;
  - `release/X.Y` contains its newest final release;
  - after each `X.Y.0`, the changelog PR writes `X.(Y+1).0.dev0` on `main`.
- **`pyproject.toml` has a static `[project] version`:** `"pyproject.toml"`. The bot
  updates it in the same way.

`stage` sets the first stage of a release: alpha, beta or rc. It also changes a release in
beta to release candidates. Refer to [Releasing](releasing.md).

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
    tags: ["v*", "!v*.dev*"]

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

It must follow this structure: run on `push: tags: ["v*", "!v*.dev*"]` (every release
tag, but not the development tags of `main`, which publish nothing), build and
check that the built version matches the tag, write the software bills of materials
(SBOMs) of the runtime dependencies and check their licenses, create a **draft** GitHub
release with every file attached, publish to PyPI with Trusted Publishing, and publish
the GitHub release last. The build stays the repository's own; the SBOM, the license
check and the three release steps are actions from here. The
`release-notes` action needs the full history and tags (`fetch-depth: 0`), and the release
jobs need `contents: write`; the job that calls `release-notes` also needs
`pull-requests: read`, which it uses to read the PR descriptions of a pre-release. The jobs that only call GitHub or the package index run on
`ubuntu-slim`, the one-CPU runner for short jobs (15 minutes at most, no Docker). `build`
and `sbom` install the project, and `upload_pypi` runs a Docker action, so they stay on
`ubuntu-latest`. A complete example:

```yaml
# Publishing: see https://github.com/Algorithmiq/release-tools#readme
#
# Runs on the v* tags that the release workflow pushes: build, draft the GitHub release
# with every file attached, publish to PyPI, then publish the GitHub release, which makes
# it immutable. Never on `release: published`. Only the build job is repository-specific.
name: Publish

on:
  push:
    tags: ["v*", "!v*.dev*"]

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

  sbom:
    # The software bills of materials of the locked runtime dependencies, attached to the
    # release, and their licenses checked: a failure stops the release before the draft
    # exists. A separate artifact: the upload takes everything in dist/.
    name: SBOM and license check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7.0.1
      - uses: Algorithmiq/release-tools/actions/sbom@v1.2.0
      - uses: Algorithmiq/release-tools/actions/license-check@v1.2.0
      - uses: actions/upload-artifact@v7.0.2
        with:
          name: sbom
          path: sbom/*

  draft_release:
    # Immutable releases: files can only be attached while the release is a draft.
    name: Create the draft GitHub release
    needs: [build, sbom]
    runs-on: ubuntu-slim
    permissions:
      contents: write
      pull-requests: read  # release-notes reads the PR descriptions
    steps:
      - uses: actions/checkout@v7.0.1
        with:
          fetch-depth: 0  # git-cliff needs the full history and the tags
      - uses: actions/download-artifact@v8.0.2
        with:
          name: dist
          path: dist
      - uses: actions/download-artifact@v8.0.2
        with:
          name: sbom
          path: sbom
      - id: notes
        uses: Algorithmiq/release-tools/actions/release-notes@v1.2.0
      - uses: Algorithmiq/release-tools/actions/draft-release@v1.2.0
        with:
          notes-file: ${{ steps.notes.outputs.path }}
          files: |
            dist/*
            sbom/*

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
    runs-on: ubuntu-slim
    permissions:
      contents: write
    steps:
      - uses: Algorithmiq/release-tools/actions/publish-release@v1.2.0
```

`release-notes` writes the tag's section of `CHANGELOG.md` for a final release, as
the release PR left it with its wording fixes (if the file has no section for the tag, a
warning says so and `git cliff --current` writes the notes from the commits). For a
pre-release it writes everything since the last final release
(`git cliff --unreleased --tag vX.Y.0rcN`), with each change's Migration section taken
from its PR description (see [Caveats](caveats.md)). It outputs the file's `path`.
`draft-release` takes `notes-file` and `files` (one glob per line, each must match), and
marks alphas, betas and release candidates as pre-releases. `publish-release` publishes
the draft. All three default to the tag that triggered the run (`tag` input) and to
`github.token` (`token` input). `release-notes` installs git-cliff itself, the official
binary with its checksum verified, with
[`taiki-e/install-action`](https://github.com/taiki-e/install-action).

### Software bills of materials

The organisation's secure development policy asks for a software bill of materials of
each released package. The `sbom` job writes one with the `sbom` action, in
[CycloneDX](https://cyclonedx.org) JSON, and `draft_release` attaches it to the release
next to the distributions.

- **What it lists:** the runtime dependencies locked in `uv.lock`. Each SBOM comes from a
  scratch environment that `uv sync --frozen --no-default-groups --no-install-project`
  creates, so it leaves out the dependency groups (tests, docs) and the project itself,
  which is the SBOM's root component. `cyclonedx-py environment` reads each package's
  licenses from its installed metadata, which `uv export --format cyclonedx1.5` doesn't
  provide.
- **`flavours`:** one SBOM per line, a name and its `uv sync` arguments, for a package
  whose extras pull in more dependencies:

  ```yaml
  - uses: Algorithmiq/release-tools/actions/sbom@v1.2.0
    with:
      flavours: |
        core
        viz --extra viz
  ```

  writes `<project>-core.cdx.json` and `<project>-viz.cdx.json`. Without `flavours`,
  one SBOM without extras: `<project>.cdx.json`.
- **Other inputs:** `path`, the directory (default `sbom`, which the action outputs as
  `path`); `component-type`, `library` (the default) or `application`; and `version`,
  the root component's version when `pyproject.toml` has none (setuptools-scm,
  hatch-vcs), which defaults to the tag.
- **One platform:** the environment is the runner's. Dependencies behind platform
  markers (`sys_platform == "win32"`) may differ on other platforms; a project that ships
  platform wheels can run the job once per platform, with a different `path` and
  artifact name for each.
- **Needs a uv project** with `uv.lock`. The action sets up uv itself, without a cache, in
  the version `pyproject.toml` or `uv.toml` requires, if any. A project whose
  dependencies come from a private index gives the `sbom` job the same credentials as its
  build.

### License check

The same policy asks for a check, before each release, that no dependency's license
clashes with how the package ships. The `license-check` action runs
[anchore/grant](https://github.com/anchore/grant), at a pinned version whose checksum it
verifies, on the SBOMs: a license outside the policy, or a package without any license,
fails the `sbom` job, so the release stops before its draft exists.

- **`policy`:** a preset of release-tools, at the version the action is pinned to.
  `open-source` (the default, in
  [`actions/license-check/policies`](https://github.com/Algorithmiq/release-tools/tree/main/actions/license-check/policies))
  allows what an Apache-2.0 library may depend on: permissive licenses and weak copyleft
  (LGPL, MPL). A repository can instead give the path of its own grant configuration,
  used as it is.
- **`ignore-packages`:** the repository's reviewed exceptions, one per line as
  `name: reason`; every entry needs the reason it passes:

  ```yaml
  - uses: Algorithmiq/release-tools/actions/license-check@v1.2.0
    with:
      ignore-packages: |
        block2: GPL-3.0-only, run as a separate program, never imported
  ```

  `ignore-packages-file` reads more of them from a file in the repository, in the same
  format, so that the publish workflow and `licenses.yml` share one list.
- **`sboms`:** the SBOMs to check, one glob per line (default `sbom/*.cdx.json`).
- **An `OR` expression** passes only if every alternative is allowed: grant checks each
  one. A package offering `LGPL-3.0-only OR GPL-3.0-only` fails, and goes into
  `ignore-packages` with the option the project takes.

### Licenses on pull requests

`licenses.yml` runs the same two actions on the pull requests that change
`pyproject.toml` or `uv.lock`, so that a license outside the policy shows up when the
dependency is added rather than at release time. It runs on `pull_request`, with the PR's
own code and a read-only token; unlike `pr-checks.yml`, which runs on
`pull_request_target` and must never read the PR's files.

```yaml
# Licenses: see https://github.com/Algorithmiq/release-tools#readme
#
# The publish workflow's SBOM and license check, on the pull requests that change the
# dependencies: a license outside the policy shows up before release time.
name: Licenses

on:
  pull_request:
    paths:
      - pyproject.toml
      - uv.lock
      - .github/workflows/licenses.yml
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  licenses:
    name: SBOM and license check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7.0.1
      - uses: Algorithmiq/release-tools/actions/sbom@v1.2.0
      - uses: Algorithmiq/release-tools/actions/license-check@v1.2.0
```

### Publishing to AWS CodeArtifact

A package for the organisation's private index on AWS CodeArtifact keeps the same
structure. Its upload job assumes the upload role with GitHub's OIDC token and runs
`uv publish`; the `CODEARTIFACT_*` variables come from the organisation
([One-time organisation setup](organisation-setup.md), step 5), so no repository's
`pyproject.toml` changes. A build that needs private dependencies assumes
`vars.CODEARTIFACT_READ_ROLE` the same way before building.

- **A failed upload can be re-run.** The job hands uv the index as a configuration file
  (`--index`), and uv reads it with the same credentials to skip the files already
  there. `UV_PUBLISH_URL` with `--check-url` alone doesn't do this for a private index:
  uv reads the check URL without credentials.
- **No PEP 740 attestations** (`--no-attestations`): they are verified and served by
  indexes with Trusted Publishing, such as PyPI, and CodeArtifact has none. The job
  attests the files with GitHub's build provenance instead, which works with any index:
  `gh attestation verify <file> --owner Algorithmiq`. In private and internal
  repositories this needs GitHub Enterprise Cloud.

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
    tags: ["v*", "!v*.dev*"]

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

  sbom:
    # The software bills of materials of the locked runtime dependencies, attached to the
    # release, and their licenses checked: a failure stops the release before the draft
    # exists. A separate artifact: the upload takes everything in dist/.
    name: SBOM and license check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7.0.1
      - uses: Algorithmiq/release-tools/actions/sbom@v1.2.0
      - uses: Algorithmiq/release-tools/actions/license-check@v1.2.0
      - uses: actions/upload-artifact@v7.0.2
        with:
          name: sbom
          path: sbom/*

  draft_release:
    # Immutable releases: files can only be attached while the release is a draft.
    name: Create the draft GitHub release
    needs: [build, sbom]
    runs-on: ubuntu-slim
    permissions:
      contents: write
      pull-requests: read  # release-notes reads the PR descriptions
    steps:
      - uses: actions/checkout@v7.0.1
        with:
          fetch-depth: 0  # git-cliff needs the full history and the tags
      - uses: actions/download-artifact@v8.0.2
        with:
          name: dist
          path: dist
      - uses: actions/download-artifact@v8.0.2
        with:
          name: sbom
          path: sbom
      - id: notes
        uses: Algorithmiq/release-tools/actions/release-notes@v1.2.0
      - uses: Algorithmiq/release-tools/actions/draft-release@v1.2.0
        with:
          notes-file: ${{ steps.notes.outputs.path }}
          files: |
            dist/*
            sbom/*

  upload_codeartifact:
    name: Upload to AWS CodeArtifact
    needs: draft_release
    runs-on: ubuntu-slim
    permissions:
      id-token: write  # the upload role and the attestations use GitHub's OIDC token
      attestations: write
      contents: read
    steps:
      - uses: actions/download-artifact@v8.0.2
        with:
          name: dist
          path: dist
      # Build provenance, stored by GitHub: `gh attestation verify <file> --owner <org>`.
      - uses: actions/attest-build-provenance@v4.2.2
        with:
          subject-path: "dist/*"
      - uses: aws-actions/configure-aws-credentials@v6.3.0
        with:
          role-to-assume: ${{ vars.CODEARTIFACT_WRITE_ROLE }}
          aws-region: ${{ vars.CODEARTIFACT_REGION }}
      - uses: astral-sh/setup-uv@v10.3.2
        with:
          enable-cache: false
      - name: Upload with uv publish
        env:
          DOMAIN: ${{ vars.CODEARTIFACT_DOMAIN }}
          DOMAIN_OWNER: ${{ vars.CODEARTIFACT_DOMAIN_OWNER }}
          REPOSITORY: ${{ vars.CODEARTIFACT_REPOSITORY }}
        run: |
          token="$(aws codeartifact get-authorization-token \
            --domain "$DOMAIN" --domain-owner "$DOMAIN_OWNER" \
            --query authorizationToken --output text)"
          echo "::add-mask::$token"
          endpoint="$(aws codeartifact get-repository-endpoint \
            --domain "$DOMAIN" --domain-owner "$DOMAIN_OWNER" --repository "$REPOSITORY" \
            --format pypi --query repositoryEndpoint --output text)"
          endpoint="${endpoint%/}/"
          # With --index, uv reads the index, with its credentials, and skips the files
          # already there, so a failed run can be re-run.
          config="$RUNNER_TEMP/codeartifact.toml"
          printf '[[index]]\nname = "codeartifact"\nurl = "%s"\npublish-url = "%s"\nexplicit = true\n' \
            "${endpoint}simple/" "$endpoint" > "$config"
          export UV_INDEX_CODEARTIFACT_USERNAME=aws UV_INDEX_CODEARTIFACT_PASSWORD="$token"
          uv publish --config-file "$config" --index codeartifact \
            --trusted-publishing never --no-attestations dist/*

  publish_release:
    # Publishing locks the tag and the files and creates GitHub's release attestation.
    name: Publish the GitHub release
    needs: upload_codeartifact
    runs-on: ubuntu-slim
    permissions:
      contents: write
    steps:
      - uses: Algorithmiq/release-tools/actions/publish-release@v1.2.0
```

## Linters and formatters: leave out `CHANGELOG.md`

The release PR and the changelog PR write `CHANGELOG.md`. git-cliff copies the summary and
the Migration section of each PR into it, code blocks included. Nobody formats this text
for your linters. If a linter or a formatter checks `CHANGELOG.md`, a bot PR can fail a
required check, and the release stops until somebody edits the bot's branch. For example,
`ruff format` also formats the Python code blocks in Markdown files: one Migration example
without a blank line after its imports makes the release PR fail `lint`.

Leave `CHANGELOG.md` out of every tool that checks its contents:

- **pre-commit or prek:** the top-level `exclude` of the configuration. It applies to every
  hook. Add the file to an existing regex with `|`.

  ```yaml
  exclude: ^CHANGELOG\.md$
  ```

- **ruff:** `extend-exclude` in `[tool.ruff]` of `pyproject.toml`, or in `ruff.toml`. It
  keeps the default exclusions of ruff. It applies to `ruff format .` and to the hooks of
  `ruff-pre-commit`, because those hooks use `--force-exclude`. If the configuration sets
  `exclude`, add the file there.

  ```toml
  [tool.ruff]
  extend-exclude = ["CHANGELOG.md"]
  ```

- **Other tools that a workflow starts directly** (prettier, markdownlint, mdformat, typos,
  codespell): the ignore list of each tool, for example `.prettierignore`.

## `justfile`: preview the changelog

`just changelog` shows what the next release's entry will look like, with the central
`cliff.toml` at the version the stubs pin (read from `release.yml`, so Dependabot's updates
carry over). It reads the squash commits, so a Migration section shows as the commit has it
(wrapped, if it was merged in the web UI), not as the release PR will take it from the PR
description (see [Caveats](caveats.md)). If release-tools is public:

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
heading**, into the PR's entry. Breaking changes and deprecations need it; any other change
that users must act on (a stub to update, say) can have one too. Keep the section above any
later heading of the template (such as a checklist), so that only the notes are copied, and
never make it the last thing in the description (see [Caveats](caveats.md)). The release
PR and the release notes of a pre-release read it from the PR description itself, which
needs the `pull-requests: read` permission of [the publish workflow](#the-publish-workflow):

```markdown
<!-- Keep this section above the Checklist: the changelog takes everything up to the next heading. -->
## Migration
<!-- Required for breaking changes (!) and deprecations. For any other change, only if
     users must act on it. Delete otherwise. The changelog shows it under the entry.
     What do users need to change? Show a before/after example if possible. -->

## Checklist

- [ ] Bug fix for the current release: add the `backport` label (or ask a maintainer to)
```

# Changelog

All notable changes to this project are listed here.

## 1.6.0 (2026-11-13)

### Fixes

- **changelog:** Keep the Migration section below footer-like lines ([#73](https://github.com/Algorithmiq/release-tools/pull/73))
- **actions:** Recover the release workflow from re-runs, wrong branches and dropped runs ([#95](https://github.com/Algorithmiq/release-tools/pull/95))
- **actions:** Run the sbom action on bash 3.2 (macOS) ([#96](https://github.com/Algorithmiq/release-tools/pull/96))
- Show why a release command failed in the job log ([#98](https://github.com/Algorithmiq/release-tools/pull/98))
- Stop the release job when a merged release PR was never tagged ([#101](https://github.com/Algorithmiq/release-tools/pull/101))

## 1.5.1 (2026-11-12)

### Fixes

- **changelog:** Keep the Migration section below footer-like lines ([#74](https://github.com/Algorithmiq/release-tools/pull/74))

## 1.5.0 (2026-11-12)

### Features

- **actions:** Install git-cliff with install-action instead of pipx ([#41](https://github.com/Algorithmiq/release-tools/pull/41))
- **release:** Move main on to X.(Y+1).0.dev0 after each X.Y.0 ([#42](https://github.com/Algorithmiq/release-tools/pull/42))

  When you bump release-tools to this version, add `"!v*.dev*"` to the tag triggers of the release stub, of the publish workflow and of any other workflow that runs on `push: tags`:

  Before:

  ```yaml
  on:
    push:
      tags: ["v*"]
  ```

  After:

  ```yaml
  on:
    push:
      tags: ["v*", "!v*.dev*"]
  ```

  Without it, the publish workflow runs for the development tag after each `X.Y.0` and fails in `release-notes`, before publishing anything.

- **actions:** Add the sbom action and an SBOM job to publish stubs ([#43](https://github.com/Algorithmiq/release-tools/pull/43))
- **actions:** Add a license-check action and a licenses stub for PRs ([#44](https://github.com/Algorithmiq/release-tools/pull/44))
- **workflows:** Run the jobs that only call APIs on ubuntu-slim ([#61](https://github.com/Algorithmiq/release-tools/pull/61))
- **changelog:** Show the migration notes of every PR ([#65](https://github.com/Algorithmiq/release-tools/pull/65))
- **actions:** Write the notes of a final release from CHANGELOG.md ([#66](https://github.com/Algorithmiq/release-tools/pull/66))
- **changelog:** Take the changelog entries from the PR descriptions ([#67](https://github.com/Algorithmiq/release-tools/pull/67))

  When you bump the pin to this version, add `pull-requests: read` to the permissions of the job that runs the `release-notes` action in your publish workflow (`draft_release` in the stubs):

  ```yaml
      permissions:
        contents: write
        pull-requests: read  # release-notes reads the PR descriptions
  ```

  Without it, a repository whose PRs the token cannot read still gets the notes of a pre-release, built from the commit bodies, with a warning per commit.

### Fixes

- **skill:** Read the rulesets of main again after the merge ([#49](https://github.com/Algorithmiq/release-tools/pull/49))
- **skill:** Leave the development tags of main out of the adoption ([#54](https://github.com/Algorithmiq/release-tools/pull/54))
- **skill:** Choose version-files by what reads each version file ([#58](https://github.com/Algorithmiq/release-tools/pull/58))
- **skill:** Leave the generated CHANGELOG.md out of linters ([#63](https://github.com/Algorithmiq/release-tools/pull/63))

  If your repository adopted release-tools before this version, leave the generated `CHANGELOG.md` out of your linters and formatters, as docs/adopting.md, "Linters and formatters: leave out `CHANGELOG.md`" shows. Otherwise a PR whose Migration section holds a code block that `ruff format` would change makes the next release PR fail `lint`.

  ```yaml
  # .pre-commit-config.yaml (top level)
  exclude: ^CHANGELOG\.md$
  ```

  ```toml
  # pyproject.toml
  [tool.ruff]
  extend-exclude = ["CHANGELOG.md"]
  ```

### Documentation

- Explain main's versions in a release cycle, and version-files ([#56](https://github.com/Algorithmiq/release-tools/pull/56))
- Accept the versions of main during a release cycle ([#69](https://github.com/Algorithmiq/release-tools/pull/69))

## 1.4.1 (2026-11-11)

### Fixes

- **skill:** Read the rulesets of main again after the merge ([#50](https://github.com/Algorithmiq/release-tools/pull/50))

## 1.4.0 (2026-11-05)

### Features

- **examples:** Add a publish workflow for AWS CodeArtifact ([#27](https://github.com/Algorithmiq/release-tools/pull/27))
- **skill:** Add the adopt-release-tools agent skill ([#29](https://github.com/Algorithmiq/release-tools/pull/29))

### Fixes

- Small follow-ups from the reviews of the leak checks, adoption docs and skill ([#36](https://github.com/Algorithmiq/release-tools/pull/36))

### Documentation

- **setup:** Adopt with existing releases and earlier changelog sections ([#28](https://github.com/Algorithmiq/release-tools/pull/28))

## 1.3.0 (2026-10-30)

### Fixes

- **actions:** Refuse to publish anything but a release tag ([#14](https://github.com/Algorithmiq/release-tools/pull/14))
- **workflows:** Merge the changelog PR with the bot's ruleset bypass ([#21](https://github.com/Algorithmiq/release-tools/pull/21))

### Documentation

- **site:** Record what the v1.2.0 release answered ([#20](https://github.com/Algorithmiq/release-tools/pull/20))

## 1.2.0 (2026-10-30)

### Features

- **release:** Add alphas and betas, and backport to both lines during pre-releases ([#9](https://github.com/Algorithmiq/release-tools/pull/9))

### Fixes

- **actions:** Refuse to publish anything but a release tag ([#15](https://github.com/Algorithmiq/release-tools/pull/15))

### Documentation

- **site:** Move the README into a versioned documentation site ([#11](https://github.com/Algorithmiq/release-tools/pull/11))

## 1.1.1 (2026-10-30)

### Fixes

- **actions:** Refuse to publish anything but a release tag ([#16](https://github.com/Algorithmiq/release-tools/pull/16))

## 1.1.0 (2026-10-28)

### Features

- **changelog:** Link each entry to its PR ([#6](https://github.com/Algorithmiq/release-tools/pull/6))

### Documentation

- **readme:** Describe the release process here instead of the internal guide ([#4](https://github.com/Algorithmiq/release-tools/pull/4))
- **examples:** Remove the AEGISS migration example ([#5](https://github.com/Algorithmiq/release-tools/pull/5))

## 1.0.0 (2026-10-28)

### Features

- **release:** Add the central release.py with tests of every command
- **changelog:** Add the central cliff.toml with tests on a scratch history
- **workflows:** Add reusable release, backport and PR checks workflows
- **actions:** Add composite actions for release notes, draft and publish

### Documentation

- **readme:** Add the adoption guide, the stubs and the AEGISS migration

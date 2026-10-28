# Migrating AEGISS to release-tools

AEGISS (branch `chore-release-workflows`) carries its own copies of the release
automation. These are the changes that make it use release-tools `v1.0.0` instead, with
the same behaviour. Apply them once release-tools `v1.0.0` exists; until then the stubs
point at a tag that doesn't.

## Files

Replace, with the files in this directory:

- `.github/workflows/release.yml` → [`.github/workflows/release.yml`](.github/workflows/release.yml)
  (stub; `version-files: ""` because the version comes from hatch-vcs)
- `.github/workflows/backport.yml` → [`.github/workflows/backport.yml`](.github/workflows/backport.yml) (stub)
- `.github/workflows/pr-checks.yml` → [`.github/workflows/pr-checks.yml`](.github/workflows/pr-checks.yml) (stub)
- `.github/workflows/deploy.yml` → [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)
  (full file; [`deploy.yml.diff`](deploy.yml.diff) shows the change: the draft and
  publish steps use the release-tools actions, and the draft job no longer needs the
  build environment)

Delete:

- `.github/scripts/release.py` (and the then empty `.github/scripts/`)
- `cliff.toml`

Patch (each applies with `git apply` from the root of AEGISS):

- [`justfile.diff`](justfile.diff): `just changelog` uses the central `cliff.toml` at the
  tag `release.yml` pins; `just release-notes` goes, the `release-notes` action replaces it.
  This uses `--config-url`, which needs release-tools to be **public**. If it is internal
  or private, use the `changelog` recipe of
  [`../stubs/justfile-internal`](../stubs/justfile-internal) instead.
- [`docs.diff`](docs.diff): `README.md` (the "Releases" section: the departures that
  release-tools now covers go, a paragraph points to release-tools), `AGENTS.md`, and
  `pyproject.toml` (no more ruff exclusion for `.github/scripts`, no `cliff.toml` in the
  sdist exclusions).

Unchanged: `.github/PULL_REQUEST_TEMPLATE.md` (its Migration section already sits above
the Checklist), `CHANGELOG.md`, `docs.yml`, `prek.toml` (the stubs pass
`check-github-workflows`, the exact-pin hook and `check-workflow-commands`, which they
have no `run:` steps for), and `.github/dependabot.yml` (its `actions` group already covers
`Algorithmiq/release-tools`, so one PR moves all six references).

## Settings

- **Required checks.** The PR checks now report as `PR checks / PR title` and
  `PR checks / Migration notes`. `pull_request_target` runs the workflow file of `main`,
  so the migration PR itself still reports the old names `PR title` and
  `Migration notes`; every PR after it reports the new ones. Replace the contexts in the
  `main` and `release branches` rulesets right after merging the migration PR, or
  require neither pair for that moment. (A ruleset that lists both pairs would block
  every PR, since only one pair ever reports.)
- Install the release bot on `release-tools` and add `release-tools` to the
  `--repos` lists of `RELEASE_BOT_CLIENT_ID` and `RELEASE_BOT_PRIVATE_KEY` (see the
  [organisation setup](../../README.md#one-time-organisation-setup)); AEGISS itself
  already has them.
- If release-tools is internal or private: its Actions **Access** setting must allow the
  organisation's repositories.

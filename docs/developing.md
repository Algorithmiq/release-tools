# Developing release-tools

```bash
just build    # uv sync: pytest, ruff, ty, prek, git-cliff, cyclonedx-py, shellcheck
just lint     # every hook: ruff, ty, actionlint (+ shellcheck), workflow and action schemas
just test     # the release package, cliff.toml, the actions, and that the examples match
```

- `tests/test_release.py` covers each command of the `release` package
  (`tests/test_cli.py` its entry points and help);
  `tests/test_release_e2e.py` drives whole release flows (two series; alphas, betas,
  candidates and two release lines with the changelog on `main`) the way `release.yml`
  and `backport.yml` do, against a scratch repository with a local bare `origin` and a
  stand-in for `gh`; `tests/test_release_pr.py` runs its `release-pr` command;
  `tests/test_workflows.py` checks that the workflows only read outputs the package
  writes.
- `tests/test_cliff.py` runs git-cliff 2.14.2 on scratch histories: gitmoji stripping,
  migration notes, blank lines, ignored pre-releases, two release lines, `--current`,
  `--prepend`, and a squash commit body wrapped at 72 columns whose PR description is
  intact.
- `tests/test_descriptions.py` covers `release/descriptions.py` (the PR descriptions that
  replace the commit bodies in git-cliff's context) against a fake GitHub API: a `gh`
  stand-in in `tests/conftest.py` that answers `gh api graphql` from canned pull requests
  and records the queries. `release-pr` and the `release-notes` action tests use it too.
- `tests/test_actions.py` shellchecks the composite actions and runs them with stand-ins
  for `gh` and git-cliff from the dev dependencies on `PATH`, standing in for
  `taiki-e/install-action`. The `release-notes` action runs on scratch histories: a final
  release gets the section of `CHANGELOG.md` at its tag, hand edits included, or
  git-cliff's notes and a warning when there is none. The `sbom` action runs for real, with uv and the
  cyclonedx-py of the dev dependencies, on a project without dependencies, and
  `license-check` with a stand-in for grant, or with grant itself when it is on `PATH`.
  The `actions` job of CI runs both on release-tools itself.
- `tests/test_examples.py` checks that docs/adopting.md, the `examples/` and the dogfooding
  stubs agree, that the stubs pass what the reusable workflows declare, and that every
  reference uses the same release-tools tag and git-cliff version.
- `tests/test_leaks.py` checks that no tracked file holds an AWS account ID, ARN or
  endpoint, or names an `Algorithmiq/` repository other than the public ones.
- `tests/test_repository_setup.py` runs the jq of docs/repository-setup.md, step 8, on
  sample rulesets: it adds only what is missing, so a second run changes nothing.
- `tests/test_skill.py` checks the agent skill in `skills/adopt-release-tools/`: its
  frontmatter, the major version it is written for, that every release-tools path
  and heading it reads exists, and that it stops for the admin and hands over only
  literal commands.

On Nix, `nix develop` (or [direnv](https://direnv.net) with the tracked `.envrc`) gives a
shell with Python 3.12, uv, just and git; run the same commands inside it. The tools
still come from `uv.lock`, so on NixOS their binary wheels need
[nix-ld](https://github.com/nix-community/nix-ld). Refresh the pinned nixpkgs with
`nix flake update`.

Requires Python 3.12 or later: the `release` package runs on the runner's
system Python (`python3 path/to/release <command>`) and only uses the standard
library. The jobs of the reusable workflows run on `ubuntu-slim`, whose Python is 3.12:
keep the package working there, and keep each job under its 15-minute limit. `python3 release --help` lists its commands.

## PR descriptions in the changelog

`release/descriptions.py` puts the description of each squash commit's PR in place of the
commit body, because the web UI wraps the body (see [Caveats](caveats.md)). Both callers
run git-cliff the same way: `git cliff --unreleased --tag vX.Y.Z --context` writes the
changelog context as JSON, `pr_descriptions` (or `release pr-descriptions`, as a filter)
sets each commit's `raw_message` to its title, a blank line and the description, and
`git cliff --from-context` renders it with the same `cliff.toml`. `release-pr` renders
the file twice (`--unreleased --prepend CHANGELOG.md` for the file, `--strip header` for
the PR body); the `release-notes` action pipes the context for a pre-release.

- **Which commits.** Every commit whose message ends with `(#N)`, as `cliff.toml` prints
  the Migration section of every entry. One `gh api graphql` query asks for up to 100
  PRs (`pullRequest(number: N) { body merged mergeCommit { oid } }`, one alias each).
  The description is used only for a merged PR whose merge commit is the commit.
- **Options.** `--from-context` ignores `--tag`, `--unreleased` and `--current`, so they
  go to the `--context` run; `--prepend` still insists on `--unreleased`.
  `commit_preprocessors` do not run again, so the helper strips `\r` and HTML comments
  from the description itself, as the Migration notes check does.
- **Failures.** `gh api graphql` exits with status 1 if any PR is not found, but prints
  the data of the others: the data decides, not the status. Any other failure keeps the
  commit bodies and prints a `::warning::` on standard error. Without
  `GITHUB_REPOSITORY` nothing is asked and nothing changes.
- **Backports.** The backport workflow gives the backport PR the description of the
  original (the `${pull_description}` placeholder of `korthout/backport-action`), so the
  squash commit on the release branch finds it under its own PR number.

## Keeping internal names out

release-tools is public; the organisation's private and internal repositories must not
be named in it. `just hooks` installs the git hooks, among them a pre-push check
([`scripts/check_internal_names.py`](https://github.com/Algorithmiq/release-tools/blob/main/scripts/check_internal_names.py))
that lists the non-public repositories with `gh` and refuses a push in which any commit's
added lines, paths or message name one. Each commit is checked on its own, so a name
that a later commit of the push removes is still caught. A name that is fine to publish goes in
`.git/info/allowed-names`, one per line; that file is never committed. PR titles and
descriptions are not checked: read them before opening the PR.

## How release-tools releases itself

release-tools follows the same process with its own workflows (dogfooding):
[`self-release.yml`](https://github.com/Algorithmiq/release-tools/blob/main/.github/workflows/self-release.yml),
[`self-backport.yml`](https://github.com/Algorithmiq/release-tools/blob/main/.github/workflows/self-backport.yml) and
[`self-pr-checks.yml`](https://github.com/Algorithmiq/release-tools/blob/main/.github/workflows/self-pr-checks.yml) are the
[consumer stubs](adopting.md) with `uses: ./.github/workflows/<file>` instead of a pinned tag, and
[`self-publish.yml`](https://github.com/Algorithmiq/release-tools/blob/main/.github/workflows/self-publish.yml) publishes the GitHub release with
`./actions/*`. A local reference runs the workflow from the same commit as the event, so a
change is exercised by release-tools itself (release candidates included) before any
consumer pins it. Nothing is built or uploaded: the release is the tag and its notes.

It has no version files (`version-files: ""`). Set it up like any other repository
([Per-repository setup](repository-setup.md), without PyPI), tag `v0.0.0` on the first
commit, and start the first release with **major** to get `v1.0.0rc1` and then `v1.0.0`.

## The documentation site

The pages in `docs/` are the source of <https://algorithmiq.github.io/release-tools/>,
built with [Zensical](https://zensical.org) (`zensical.toml`). `just docs` previews it
with live reload; `just docs-build` builds it the way CI does (`--strict`: broken links
fail). Links between pages are relative `.md` links, so they work on GitHub too.

Each release deploys its version with [Zensical's fork of mike](https://github.com/squidfunk/mike)
(the `docs` job of `.github/workflows/self-publish.yml`), which commits to the
`gh-pages` branch:

| Tag | Deployed as |
| --- | --- |
| `vX.Y.Z`, newest final line | `X.Y`, and `latest` moves to it |
| `vX.Y.Z`, an older line | `X.Y` (`latest` stays) |
| `vX.Y.0aN`, `bN`, `rcN` | `X.Y`, titled "X.Y (pre-release)", until its final replaces it |

The site root redirects to `latest` after the first final; until then, it redirects to
the first pre-release's line. If a docs deploy is skipped because several tags were
pushed close together, re-run that tag's docs job (the deploy logic doesn't depend on
order, so it's safe in any order). mike is transitional: when Zensical ships native
versioning, only the deploy step changes.

One-time setup, by a repository admin: Settings → Pages → Source: **Deploy from a
branch**, branch `gh-pages`, folder `/ (root)`. The branch appears with the first
deploy; set the source after it. No ruleset may block pushes of the Actions token to
`gh-pages`.

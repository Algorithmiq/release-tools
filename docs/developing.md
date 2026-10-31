# Developing release-tools

```bash
just build    # uv sync: pytest, ruff, ty, prek, git-cliff, shellcheck
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
  `--prepend`.
- `tests/test_actions.py` shellchecks the composite actions and runs them with stand-ins
  for `pipx` and `gh`.
- `tests/test_examples.py` checks that docs/adopting.md, the `examples/` and the dogfooding
  stubs agree, that the stubs pass what the reusable workflows declare, and that every
  reference uses the same release-tools tag and git-cliff version.
- `tests/test_leaks.py` checks that no tracked file holds an AWS account ID, ARN or
  endpoint, or names an `Algorithmiq/` repository other than the public ones.
- `tests/test_skill.py` checks the agent skill in `skills/adopt-release-tools/`: its
  frontmatter, the major version it is written for, and that every release-tools path
  and heading it reads exists.

Requires Python 3.12 or later: the `release` package runs on the runner's
system Python (`python3 path/to/release <command>`) and only uses the standard
library. `python3 release --help` lists its commands.

## Keeping internal names out

release-tools is public; the organisation's private and internal repositories must not
be named in it. `just hooks` installs the git hooks, among them a pre-push check
([`scripts/check_internal_names.py`](https://github.com/Algorithmiq/release-tools/blob/main/scripts/check_internal_names.py))
that lists the non-public repositories with `gh` and refuses a push whose added lines or
commit messages name one. A name that is fine to publish goes in
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

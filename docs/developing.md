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

Requires Python 3.12 or later: the `release` package runs on the runner's
system Python (`python3 path/to/release <command>`) and only uses the standard
library. `python3 release --help` lists its commands.

## How release-tools releases itself

release-tools follows the same process with its own workflows (dogfooding):
[`self-release.yml`](https://github.com/Algorithmiq/release-tools/blob/main/.github/workflows/self-release.yml),
[`self-backport.yml`](https://github.com/Algorithmiq/release-tools/blob/main/.github/workflows/self-backport.yml) and
[`self-pr-checks.yml`](https://github.com/Algorithmiq/release-tools/blob/main/.github/workflows/self-pr-checks.yml) are the consumer stubs
above with `uses: ./.github/workflows/<file>` instead of a pinned tag, and
[`self-publish.yml`](https://github.com/Algorithmiq/release-tools/blob/main/.github/workflows/self-publish.yml) publishes the GitHub release with
`./actions/*`. A local reference runs the workflow from the same commit as the event, so a
change is exercised by release-tools itself (release candidates included) before any
consumer pins it. Nothing is built or uploaded: the release is the tag and its notes.

It has no version files (`version-files: ""`). Set it up like any other repository (the
per-repository steps above, without PyPI), tag `v0.0.0` on the first commit, and start the
first release with **major** to get `v1.0.0rc1` and then `v1.0.0`.

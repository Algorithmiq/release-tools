# Design

## How the central files reach the caller at the pinned version

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
  the commit of the tag the caller pinned, so the workflow logic, the `release`
  package and `cliff.toml` always come from one ref. It costs the stubs nothing.
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

`backport.yml` checks release-tools out the same way, for its `backport-targets` command;
`pr-checks.yml` needs no files from here. The publish actions are
composite actions called directly from the consumer's `deploy.yml`, where the consumer
writes the ref: `release-notes` finds `cliff.toml` at `${{ github.action_path }}/../../cliff.toml`,
which the runner downloads with the action at that ref.

## Secrets and inputs

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
  be a wrapper such as [`self-pr-checks.yml`](../.github/workflows/self-pr-checks.yml) rather
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

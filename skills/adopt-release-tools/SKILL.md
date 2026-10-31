---
name: adopt-release-tools
description: Use when adopting release-tools, Algorithmiq's release process, in a repository, or when a repository should stop publishing its releases by hand through the GitHub UI.
metadata:
  release-tools-major: "1"
---

# Adopt release-tools

You move one repository onto release-tools together with its admin. The work splits in
two, and stays split even when the admin offers you their token:

- **You** read the repository and GitHub, write the files, push the adoption branch and
  open the adoption PR.
- **The admin** runs every command that changes GitHub: repository settings, labels,
  tags, rulesets, the organisation's variable and secret lists, `gh workflow
  disable`/`enable`, the merge of the adoption PR and the first release. Give each one in
  order, and wait until the admin reports it done.

Beyond the adoption branch and its PR, you run reads only. A command block with a write
in it (`gh api -X …`, `gh label create`, `gh variable set`, `git push` of a tag) is text
for the admin: hand it over as text, even when you only want to test it. Every command
you hand over names this repository, the App ID and the ruleset ids literally, or guards
each variable it uses (`${REPO:?}`, `${APP_ID:?}`), so that a missing value stops it
before `gh api` runs.

Work through the phases in order. Each ends on a **done** check. A **blocker** is what
stops the adoption until someone outside it acts: a default branch other than `main`, a
pre-release tag without its final, a published version above the newest final tag,
missing `CODEARTIFACT_*` organisation variables, no admin access. Stop on a blocker, say
exactly what is missing and who can resolve it, and go on once it is resolved.
Everything the plan does itself (sharing the bot credentials, installing the app,
creating rulesets, the settings, rewriting the publish workflow for the index it
publishes to today) is a **to-do** in the plan. Inspect only reads, so a second run of this skill finds where an interrupted
adoption stopped: pass quickly over every phase whose done check already holds.

The adopting repository is private or internal, and release-tools is public. Anything
you report upstream (an issue, a PR, a comment) describes the problem in general terms,
without this repository's name, files or contents.

## Phase 0: The source

release-tools' documentation is the source of every stub, command and setting: read it
from a clone of the latest release, and copy stubs and commands from there.

```bash
tag=$(gh release view -R Algorithmiq/release-tools --json tagName --jq .tagName)
rt=$(mktemp -d)/release-tools
git clone --quiet --depth 1 --branch "$tag" https://github.com/Algorithmiq/release-tools "$rt"
```

- `$rt/docs/adopting.md`: the stubs, the publish workflow, the `justfile` recipe, the
  PR template.
- `$rt/docs/repository-setup.md`: the admin's steps, numbered 1 to 8.
- `$rt/docs/caveats.md`: what the team needs to know afterwards.
- `$rt/examples/stubs/`: the files to copy. They pin an example tag: write `$tag`
  in every `Algorithmiq/release-tools` reference instead.

This skill is written for the major version in `release-tools-major` above. If `$tag`
has another major, that is a blocker: the skill is out of date (`npx skills update`).

**Done:** `$tag` is known, its major matches, and `$rt` exists.

## Phase 1: Inspect

Read only. Fill in a **facts table**, one row per fact below, with the value its command
returned. Set `REPO=Algorithmiq/<name>`, and work in an up-to-date clone of the
repository on its default branch.

| Fact | How to read it | Target, or blocker |
| --- | --- | --- |
| Admin access | `gh api repos/$REPO --jq .permissions.admin`; `gh auth status` lists the `admin:org` scope | `true`, else a blocker. Without `admin:org`, an organisation owner runs the organisation steps |
| Default branch | `gh api repos/$REPO --jq .default_branch` | `main`. Anything else is a blocker: the admin renames it (`$rt/docs/repository-setup.md`) |
| Version source | `pyproject.toml` (`[project] version` or `dynamic`), the build backend, a `VERSION` file | `version-files`: `"pyproject.toml"` for a static version; `"VERSION"` when the build reads it, or when it is kept in step with the tags next to setuptools-scm; `""` when the version comes only from the tag |
| Newest final tag | `git tag --list 'v*' --sort=-v:refname` | The newest `vX.Y.Z` |
| Newest tag | the same list | A pre-release (`v0.4.0rc1`, `v0.4.0b1`) newer than every final tag, without its final, is a blocker: the admin releases that final the old way first |
| Published versions | `gh release list -R $REPO`; PyPI: `curl -s https://pypi.org/pypi/<distribution>/json \| jq -r '.releases \| keys[]'`; CodeArtifact: `aws codeartifact list-package-versions --format pypi --package <distribution> …`, which needs AWS credentials | A final version newer than the newest final tag is a blocker: the admin tags that version's commit `vX.Y.Z` first. An index you cannot read goes to the admin in phase 2 |
| Baseline | the rows above | The newest final tag; `v0.0.0` only with no final tags and nothing published |
| Publish workflow | the workflow that uploads (`twine`, `pypa/gh-action-pypi-publish`, `codeartifact`) | Variant: PyPI, CodeArtifact or none; its triggers; each job, what it does and its `if:` |
| `release` triggers | the `on:` of every workflow; a job named `release:` is not a trigger | Every workflow listed, with what it does on a release: phase 3 moves each one |
| Inlined CodeArtifact values | every workflow and job: AWS account, role ARNs, domain, region, repository | Each value with its file, job and the `vars.CODEARTIFACT_*` it becomes |
| Tag-push workflows at the `v0.0.0` commit | baseline `v0.0.0` only: `git show <commit>:.github/workflows/<file>`, a `tags:` under `push:` | None that publish; otherwise the admin disables that workflow around the push of `v0.0.0` |
| Old process | `release` triggers, `workflow_dispatch` routes to publishing, `.github/release.yml` | Listed; the adoption PR removes them |
| Files | the PR template (`.github/pull_request_template.md`, any case), `justfile`, `.github/dependabot.yml`, `CHANGELOG.md` | Present or absent |
| Settings | `gh api repos/$REPO --jq '{allow_squash_merge, allow_merge_commit, allow_rebase_merge, allow_auto_merge, delete_branch_on_merge, squash_merge_commit_title, squash_merge_commit_message}'` | As step 3 of `$rt/docs/repository-setup.md` sets them |
| Immutable releases | `gh api repos/$REPO/immutable-releases --jq .enabled` | `true` |
| `backport` label | `gh label list -R $REPO --search backport` | Present |
| Rulesets | `gh api repos/$REPO/rulesets --jq '.[].id'`, then for each `gh api repos/$REPO/rulesets/<id> --jq '{id, name, target, include: .conditions.ref_name.include, rules: [.rules[].type], bypass: .bypass_actors}'` | `release tags` and `release branches` as steps 5 and 6 create them. The default branch's rulesets are those whose `include` holds `~DEFAULT_BRANCH`, `refs/heads/main` or `~ALL`, whatever their name (such as `Protect main`): note their ids and the checks they already require |
| App ID | `gh api orgs/Algorithmiq/installations --jq '.installations[] \| select(.app_slug == "algorithmiq-release-bot") \| .app_id'` | A number, for the rulesets |
| App installed on the repository | not readable with a user token | The admin confirms it: Organisation settings → GitHub Apps → algorithmiq-release-bot → Configure |
| Bot credentials | `gh api orgs/Algorithmiq/actions/variables/RELEASE_BOT_CLIENT_ID/repositories --jq '[.repositories[].name]'`; the same for `secrets/RELEASE_BOT_PRIVATE_KEY` | The repository is in both lists |
| CodeArtifact variables | when any workflow uses CodeArtifact: `gh api repos/$REPO/actions/organization-variables --jq '[.variables[].name]'` | All six of `$rt/docs/organisation-setup.md`, step 5. A missing one is a blocker for an organisation owner |

**Done:** every row holds what its command returned; "cannot check" only with the
error or the missing credential that stopped it. The blockers are listed apart from the
to-dos.

## Phase 2: Plan

Show the admin the facts table, then the plan:

1. **The admin's decisions:** the baseline, and for `v0.0.0` its commit (the last one
   that should not appear in the changelog); the repository's own CI checks to require
   on `release/*` next to the PR checks; the number of approvals there.
2. **The adoption PR:** every file it adds, changes or removes (phase 3).
3. **The admin's commands,** in order, each filled in for this repository (phases 4 and
   5).
4. **What changes for the team:** squash-merge only; releases start from the Release
   workflow instead of the GitHub UI; every pre-release is published to the package
   index; workflows with `release` triggers move to tag pushes.

When you could not read the package index, ask the admin to run the filled-in
`list-package-versions` command and report every version it lists. Settle the
baseline on that answer: `v0.0.0` only once the admin confirms the index holds no
version of the package.

With an existing baseline tag, add that `CHANGELOG.md` gets the releases before
adoption, generated in the adoption PR, where the admin completes them.

**Done:** the admin has answered for the package index, approves the plan explicitly,
and no blocker from phase 1 is open.

## Phase 3: The adoption PR

On a new branch off the default branch:

- **The three stubs** from `$rt/examples/stubs/` (`release.yml`, `backport.yml`,
  `pr-checks.yml`) into `.github/workflows/`, with `$tag` and the `version-files` of the
  facts table.
- **The publish workflow:** follow [publish-workflow.md](publish-workflow.md).
- **Every inlined CodeArtifact value** of the facts table becomes its
  `vars.CODEARTIFACT_*` variable, in every workflow and job that holds one, not only
  the upload (publish-workflow.md, "The CodeArtifact variables").
- **`just changelog`:** the recipe for a public release-tools from
  `$rt/docs/adopting.md`, in the `justfile` (a new one if there is none).
- **The PR template:** the Migration section and the backport checklist item from
  `$rt/docs/adopting.md`, above any later heading of the existing template.
- **`CHANGELOG.md`:** with an existing baseline tag, a `## X.Y.Z (YYYY-MM-DD)` section
  for every final release up to it, generated as step 2 of
  `$rt/docs/repository-setup.md` shows; an empty file with `v0.0.0` only. An existing
  `CHANGELOG.md` stays only if its release headings read `## X.Y.Z (YYYY-MM-DD)`;
  otherwise regenerate it and tell the admin.
- **Dependabot:** the `release-tools` group from `$rt/docs/versioning.md`, merged into
  `.github/dependabot.yml`.
- **The old process removed:** the publishing `workflow_dispatch` routes,
  `.github/release.yml`, and the `release` trigger of every workflow (tests, image
  builds, documentation), each replaced as publish-workflow.md says so that its work
  still runs for every release.

Title the PR by the convention it introduces, for example `ci: 👷 adopt release-tools`.
Its description lists, for every release before adoption, the section to compare with
`gh release view vX.Y.Z`, and the stray groups git-cliff made from capitalised types
(such as `### Fix`). Push the branch and open the PR; the admin merges it after phase 4.

**Done:** every `Algorithmiq/release-tools` reference uses `$tag`
(`grep -rn 'Algorithmiq/release-tools' .github justfile`); no workflow has a `release`
trigger; `grep -rnE 'arn:aws[:]|\b[0-9]{12}\b' .github/workflows` finds nothing; the
done check of publish-workflow.md holds; actionlint passes on `.github/workflows/`
(`uvx --from actionlint-py actionlint`); and the PR is open.

## Phase 4: The admin's steps before the merge

Steps 1 to 7 of `$rt/docs/repository-setup.md`, as filled-in commands, one at a time,
in this order. After each, re-read its row of the facts table.

1. **Bot credentials** (step 1): `--repos` replaces the list, so give the full current
   list from phase 1 with this repository added, for the variable and the secret.
2. **App installation** (step 1, web UI).
3. **Settings, immutable releases, the `backport` label** (step 3).
4. **The baseline** (step 2): `v0.0.0` only when the plan says so, before the tag
   ruleset, with a tag-push publishing workflow disabled around it if phase 1 found one.
5. **The tag ruleset** (step 5), with the App ID.
6. **The `release/*` ruleset** (step 6), with the App ID and the checks the admin chose.
7. **The package index** (step 7): PyPI, the Trusted Publisher (web UI); CodeArtifact
   and no package, nothing.

**Done:** re-running phase 1 shows each of these rows at its target.

## Phase 5: After the merge

The admin squash-merges the adoption PR. Then step 8 of
`$rt/docs/repository-setup.md`, on the default branch's rulesets from phase 1, whatever
their name: the default branch requires `PR checks / PR title` and
`PR checks / Migration notes`, and the release bot bypasses every one of those rulesets
with a `pull_request` or `required_status_checks` rule, without which every changelog
PR waits for an approval. Hand over step 8's command once per ruleset, with its id
written in place of the `id=$(…)` line. A default branch without a
`required_status_checks` rule gets one first. If a ruleset required other checks for
PR titles, they switch to the new names now (`$rt/docs/caveats.md`, check names).

**Done:** `gh api repos/$REPO/rulesets/<id>` shows both checks required on the default
branch, and the App ID among the bypass actors of each of those rulesets.

## Phase 6: The first release, and the report

Hand over the first release: check that no deprecation is due for removal, then
**Actions → Release → Run workflow** on `main` with a bump (`minor` or `major`) and a
stage (`rc` by default; `beta` or `alpha` to start earlier), or
`gh workflow run release.yml -R <owner/name> --ref main -f bump=minor -f stage=rc` with
the repository written in. Every pre-release is published to the package index.

End with a report:

- what was done, and by whom;
- what is still waiting for a human, with its command;
- from `$rt/docs/caveats.md`, what matters to the team from now on: the changelog PR
  merges itself only with the bypass of phase 5; an older release line runs the
  release-tools version its branch pins; workflows on `release` events no longer run.

**Done:** the report is written. The adoption is complete when its waiting list is
empty.

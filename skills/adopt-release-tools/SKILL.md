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
  order, and wait until the admin reports it done. When you hand one over, address the
  admin: write "You run:" above it, never "the commands run" or "I run".

**What you run.** Reads: `gh api` without `-X`/`--method` other than `GET` and without
`-f`, `-F`, `--field`, `--raw-field` or `--input` (any of them makes it a POST);
`gh … list`, `view` and `status`; `git clone`, `fetch`, `log`, `show`, `ls-remote`. Local
work in your clone and in `mktemp -d` directories. And the adoption PR only:
`git push origin <the adoption branch>`, by name, and `gh pr create`/`gh pr edit` for it.
Everything else that changes GitHub (a `gh api` write, `gh label create`,
`gh variable set`, `gh workflow run`, `gh release …`, `gh pr merge`, `gh issue create`)
is text for the admin: hand it over as text, even when you only want to test it. Never
create a tag, local or pushed, and never push with `--tags`, `--all` or `--follow-tags`.
Every report you write, the one of phase 6 and one that ends the adoption early (on a
blocker, or because the admin stops it), ends with "Commands run that were not reads,
beyond the adoption branch and its PR: none", or their list.

**File tool only.** Write every file whose content you compose with your file-writing
tool, never a shell heredoc, `echo`, `printf`, `tee` or a script: the adoption PR's files
(workflows, PR template, `dependabot.yml`, `justfile`, your edits to `CHANGELOG.md`),
the payload files, and every plan, report or document. A heredoc inside a command
substitution (`$(cat <<'EOF' …)`, as an argument of `--body` or `-m`, say) is a heredoc
too: write the text to a file, and pass the file (`--body-file`, `-F`). A tool's own
output is fine: git-cliff's `--output`, or a stub copied with `cp` and then edited with
the file tool. A heredoc only feeds a script that reads.

**Handed-over commands.** A JSON payload goes into a file outside the clone, so that it
never reaches the adoption PR: even in a dry run, create the directory with `mktemp -d`,
write the file there, and put its literal absolute path in the command's `--input`,
never a variable (`${DIR:?}`). Where `$rt/docs/repository-setup.md` pipes a heredoc into
`--input -`, the file replaces the heredoc. Show the file's content next to the command,
and tell the admin to save it at that path, or edit the path, if they run the command on
another machine. Each command names this repository, the App ID and the ruleset ids
literally, or guards each variable it uses (`${REPO:?}`, `${APP_ID:?}`) and sets it on
its first line, so that a missing value stops it before `gh api` runs. No command you
hand over holds a heredoc or a `<placeholder>`. A value you cannot read (a role ARN that
no workflow holds, the commit `v0.0.0` goes on) is a question for the admin in phase 2:
until it is answered you hand over no command that needs it, and the plan lists that
command under **Waiting for**, with its question. For example, step 5 of phase 4, after
`mktemp -d` printed `/tmp/tmp.Xa81kQ`:

````markdown
`/tmp/tmp.Xa81kQ/release-tags.json`:

```json
{"name": "release tags", "target": "tag", "enforcement": "active",
 "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
 "rules": [{"type": "creation"}, {"type": "update"}, {"type": "deletion"}],
 "bypass_actors": [{"actor_id": 1234567, "actor_type": "Integration", "bypass_mode": "always"}]}
```

You run (save the file at that path first if you run it on another machine):

```bash
gh api -X POST repos/Algorithmiq/example/rulesets --input /tmp/tmp.Xa81kQ/release-tags.json
```

Reply `done` once it has run, or paste its error.
````

**Stop** in a phase means: send what the phase lists, end your turn, and go on only once
the admin has replied as it says.

Work through the phases in order. Each ends on a **done** check. A **blocker** is what
stops the adoption until someone outside it acts: a default branch other than `main`, a
pre-release tag without its final, a published version above the newest final tag,
missing `CODEARTIFACT_*` organisation variables (phase 2 hands an owner the commands
that set them), no admin access. Stop on a blocker, say
exactly what is missing and who can resolve it, and go on once it is resolved.
Everything the plan does itself (sharing the bot credentials, installing the app,
creating rulesets, the settings, rewriting the publish workflow for the index it
publishes to today) is a **to-do** in the plan. What you cannot read or decide (the
package index, a role ARN, a value that differs from the organisation's) is a
**question** for the admin in phase 2. What you cannot check (an AWS role's trust
policy) the plan and the report mark **not verified**, never a fact. Inspect only reads,
so a second run of this skill finds where an interrupted adoption stopped: pass quickly
over every phase whose done check already holds, continue on the open adoption PR's
branch if a previous run opened one, and hand over no step whose row is already at its
target.

The adopting repository is usually private or internal, and release-tools is public.
You do not open issues, PRs or comments on release-tools. When something there is
wrong, write the report in general terms, without this repository's name, files or
contents, and hand it to the admin to post.

## Phase 0: The source

release-tools' documentation is the source of every stub, command and setting: read it
from a clone of one release, and copy stubs and commands from there. If the admin names
a release-tools tag (such as a release candidate for a pilot), use that tag: set `tag`
to it instead of the first line below, which reads the latest final release only. A
named tag still goes through the major check below.

```bash
tag=$(gh release view -R Algorithmiq/release-tools --json tagName --jq .tagName)
rt=$(mktemp -d)/release-tools
git clone --quiet --depth 1 --branch "$tag" https://github.com/Algorithmiq/release-tools "$rt"
```

- `$rt/docs/adopting.md`: the stubs, the publish workflow, the `justfile` recipe, the
  PR template.
- `$rt/docs/repository-setup.md`: the admin's steps, numbered 1 to 8.
- `$rt/docs/caveats.md`: what the team needs to know afterwards.
- `$rt/examples/stubs/`: the files to copy. They pin an example tag: in every
  `uses: Algorithmiq/release-tools…@` pin, write the value of `$tag` (such as `v1.3.0`)
  instead, never the string `$tag`.

Shell variables may not outlive one command: write the values of `$tag` and `$rt` at the
top of the facts table, and use them literally from then on.

This skill is written for the major version in `release-tools-major` above. If `$tag`
has another major, that is a blocker: the skill is out of date (`npx skills update`), or
the admin names a tag of this major. If a path under `$rt` that this skill names is
missing, the release predates the skill: that is a blocker too; use a newer tag, or ask
the admin for one.

**Done:** `$tag` is the admin's tag or the latest release, its major matches, `$rt`
exists, and every path under `$rt` that this skill names exists in it.

## Phase 1: Inspect

Read only. Fill in a **facts table** with the columns `Fact | Value | Target | Status`:
one row per fact below, the value its command returned, and a status of `ok`, `to-do`,
`blocker`, `question` or `not verified`. Set `REPO=Algorithmiq/<name>`, and work in an
up-to-date clone of the repository on its default branch.

| Fact | How to read it | Target, or blocker |
| --- | --- | --- |
| Admin access | `gh api repos/$REPO --jq .permissions.admin`; `gh auth status` lists the `admin:org` scope | `true`, else a blocker. Without `admin:org`, an organisation owner runs the organisation steps: say who, in the plan |
| Default branch | `gh api repos/$REPO --jq .default_branch` | `main`. Anything else is a blocker: the admin renames it (`$rt/docs/repository-setup.md`) |
| Visibility | `gh api repos/$REPO --jq .visibility` | As read: `public`, `internal` or `private`. The organisation variables (visibility `private`) reach `internal` and `private` repositories only: a `public` one that publishes to CodeArtifact is a blocker |
| Version source | `pyproject.toml` (`[project] version` or `dynamic`), the build backend, a `VERSION` file | `version-files`: `"pyproject.toml"` for a static version; `"VERSION"` when the build reads it; `""` when the version comes only from the tag (setuptools-scm, hatch-vcs); `"VERSION"` too for a `VERSION` file kept in step with the tags next to setuptools-scm (`$rt/docs/adopting.md`). When you cannot tell which file the build reads, it is a question |
| Newest final tag | `git fetch --tags`, then `git tag --list 'v*' --sort=-v:refname`; a final tag matches `vX.Y.Z` exactly | The newest `vX.Y.Z` |
| Newest tag | the same list | A pre-release (`v0.4.0rc1`, `v0.4.0b1`) newer than every final tag, without its final, is a blocker: the admin releases that final the old way first. A development tag (`v0.5.0.dev0`), which the bot puts on `main` after each final once the repository has adopted, is no pre-release: leave it out |
| Published versions | `gh release list -R $REPO --limit 1000` (30 without `--limit`), and the index the publish workflow uploads to, only that one: PyPI, `curl -s https://pypi.org/pypi/<distribution>/json \| jq -r '.releases \| keys[]'`; CodeArtifact, `aws codeartifact list-package-versions --format pypi --package <distribution>` with the domain, domain owner, repository and region of the CodeArtifact rows, which needs AWS credentials. Never query PyPI for a package published elsewhere: its name is private | A final version newer than the newest final tag is a blocker: the admin tags that version's commit `vX.Y.Z` first, with any tag-push workflow that publishes disabled around the push (Tag-push workflows row). An index you cannot read is a question for phase 2, not a blocker |
| Baseline | the rows above | The newest final tag; `v0.0.0` only with no final tags and nothing published |
| Publish workflow | the workflow that uploads (`twine`, `uv publish`, `pypa/gh-action-pypi-publish`, `codeartifact`) | Variant: PyPI, CodeArtifact, both or none; its file name, its triggers; each job, what it does and its `if:` |
| `release` triggers | the `on:` of every workflow; a job named `release:` is not a trigger | Every workflow listed, with what it does on a release and what else triggers it: phase 3 moves each one |
| Tag triggers | the `on:` of every workflow: a `tags:` under `push:` | Each one whose patterns would match `v1.3.0.dev0` (such as `v*`) holds `"!v*.dev*"`, or the adoption PR adds it: after each final, the bot tags `main` with `vX.(Y+1).0.dev0`, which is no release, and a workflow on it runs for nothing (the publish workflow fails). `v[0-9]+.[0-9]+.[0-9]+` matches finals only, and needs nothing |
| Workflow file names | `.github/workflows/release.yml`, `backport.yml`, `pr-checks.yml` | Absent, or already a release-tools stub. Any other file of that name is renamed by the adoption PR before the stub takes its place (publish-workflow.md, "Each existing job") |
| Inlined CodeArtifact values | every workflow and job: AWS account, role ARNs, domain, region, repository | Each value with its file, job, the `vars.CODEARTIFACT_*` it becomes, and whether it equals that variable's value (the CodeArtifact variables row): one that differs is a question. A role that serves more than CodeArtifact is a question (publish-workflow.md, "The CodeArtifact variables") |
| Tag-push workflows at a commit the admin tags | `v0.0.0`, or the commit of a published version above the newest final tag: `git show <commit>:.github/workflows/<file>`, a `tags:` under `push:` | None that publish; otherwise the admin disables that workflow around the push of the tag |
| Old process | `release` triggers, `workflow_dispatch` routes to publishing, `.github/release.yml`, local copies of `release.py` and `cliff.toml`, docs (README, `CONTRIBUTING.md`, `docs/`) that describe any step of the old process: creating a release on GitHub, bumping the version by hand, tagging by hand, a forced upload, editing the changelog at release time | Listed; the adoption PR removes them and points those docs to **Actions → Release** |
| Files | the PR template (`.github/pull_request_template.md`, any case), `justfile`, `.github/dependabot.yml` (or `.yaml`), `CHANGELOG.md` | Present or absent |
| Settings | `gh api repos/$REPO --jq '{allow_squash_merge, allow_merge_commit, allow_rebase_merge, allow_auto_merge, delete_branch_on_merge, squash_merge_commit_title, squash_merge_commit_message}'` | As step 3 of `$rt/docs/repository-setup.md` sets them |
| Immutable releases | `gh api repos/$REPO/immutable-releases --jq .enabled` | `true` |
| `backport` label | `gh label list -R $REPO --search backport` | Present |
| Rulesets | `gh api --paginate repos/$REPO/rulesets --jq '.[].id'`, then for each `gh api repos/$REPO/rulesets/<id> --jq '{id, name, source_type, enforcement, target, include: .conditions.ref_name.include, rules: [.rules[].type], checks: [.rules[] \| select(.type == "required_status_checks") \| .parameters.required_status_checks[]], bypass: .bypass_actors}'` | `release tags` and `release branches` as steps 5 and 6 create them. Another ruleset on `refs/tags/v*` or `refs/heads/release/*` is a question. The default branch's rulesets are those whose `include` holds `~DEFAULT_BRANCH`, `~ALL` or `refs/heads/<default branch>`, whatever their name (such as `Protect main`): note their ids, `source_type`, `enforcement`, and the checks they already require with each one's `integration_id`. A ruleset with `enforcement` `disabled` or `evaluate` enforces nothing: list it, and leave it out of phase 5 |
| Classic branch protection | `gh api repos/$REPO/branches/main/protection` (404: none) | None. Otherwise a question: the bot's bypass covers rulesets only |
| `release/*` branches | `git ls-remote --heads origin 'release/*'` | None. Otherwise listed: they have no stubs, so the PR checks never report on them |
| App ID | `gh api --paginate orgs/Algorithmiq/installations --jq '.installations[] \| select(.app_slug == "algorithmiq-release-bot") \| .app_id'` | A number, for the rulesets |
| App installed on the repository | not readable with a user token | The admin confirms it: Organisation settings → GitHub Apps → algorithmiq-release-bot → Configure |
| Bot credentials | `gh api --paginate orgs/Algorithmiq/actions/variables/RELEASE_BOT_CLIENT_ID/repositories --jq '.repositories[].name'`; the same for `secrets/RELEASE_BOT_PRIVATE_KEY` | The repository is in both lists. Phase 4 adds it one repository at a time; `--repos` is not used, because it replaces the whole list |
| CodeArtifact variables | when any workflow uses CodeArtifact: `gh api --paginate repos/$REPO/actions/organization-variables --jq '.variables[] \| {name, value}'` | All six of `$rt/docs/organisation-setup.md`, step 5. A missing one is a blocker for an organisation owner, except `CODEARTIFACT_READ_ROLE` when no workflow assumes a read role: then note it for an owner. Phase 2 hands the owner the commands that set the missing ones. Each inlined value that differs from its variable's is a question: after adoption the workflows read the variable, so packages go where it points |

**Done:** every row holds what its command returned; "cannot check" only with the
error or the missing credential that stopped it. The blockers are listed apart from the
to-dos.

## Phase 2: Plan

Send the admin one message with these headings, in this order:

1. **Facts:** the facts table.
2. **Blockers:** each one, who resolves it and how; `None` if there are none.
   **Missing `CODEARTIFACT_*` variables** are set by an organisation owner, with step 5
   of `$rt/docs/organisation-setup.md`. They serve every private and internal
   repository, so this message hands over no `gh variable set` yet. Show, for each
   missing variable, every value phase 1 found inlined and where (several when
   workflows disagree, none when no workflow holds it), and ask, as a decision: which
   value does the organisation use? Under **Waiting for**, name the variables only,
   with no command and no value. Once the owner has answered every variable, hand over
   one `gh variable set` per variable, with the answered value written in, to the owner
   only (never into the adoption PR or a report upstream: they name the AWS account and
   the roles). In the same message, ask the admin about each inlined value that
   differs from the answer: once the workflows read the variable, that job's packages
   go elsewhere (phase 1). Phase 3 waits for that answer too. The blocker stays open
   until the owner reports the commands run and the row reads at its target.
3. **Decisions requested:** numbered, each with the answer you need. Ask only what this
   skill leaves open: what it settles (release-tools is public, the variant follows the
   index the repository publishes to, a Trusted Publisher is for PyPI only) is part of
   the plan, not a question. The decisions:
   - the baseline, and for `v0.0.0` its commit (the last one that should not appear in
     the changelog);
   - the repository's own CI checks to require on `release/*` next to the PR checks.
     Start from those the default branch's active rulesets already require, with the
     `integration_id` each has there. Leave out a check whose workflow skips some PRs to
     `release/*` (`paths` or `paths-ignore` filters, `branches` that leave out
     `release/*`, or `branches-ignore` that matches it): its required check would block
     those PRs. Leave out a PR-title or migration-notes check of the repository's own:
     the PR checks replace it. A matrix
     job reports one check per entry (`test (3.12)`), whose names change with the
     matrix and can differ between release lines: name such checks in the plan as a
     risk, and prefer a job that aggregates them if the repository has one. List each
     check left out, and why;
   - the number of approvals on `release/*` (1 in step 6 of
     `$rt/docs/repository-setup.md`);
   - for each workflow or job that moves from `release` to tag pushes: whether it should
     also run for pre-release tags (alphas, betas, release candidates). If not, the PR
     limits it to final tags (publish-workflow.md, "The old triggers");
   - every question of phase 1. For a package index you could not read, the admin runs
     the filled-in `list-package-versions` command and reports every version it lists.
     Settle the baseline on that answer: `v0.0.0` only once the admin confirms the index
     holds no version of the package.
4. **The adoption PR:** every file it adds, changes, renames or removes (phase 3). With
   an existing baseline tag, `CHANGELOG.md` gets a section for each final release up to
   it, generated in the PR; the admin checks each section there against that release's
   GitHub notes.
5. **The admin's commands:** in order, each filled in for this repository (phases 4 and
   5), and under **Waiting for**, each command that needs an answer, with its question.
6. **What changes for the team:** squash-merge only; releases start from the Release
   workflow instead of the GitHub UI; every pre-release is published to the package
   index; workflows with `release` triggers move to tag pushes, and run for pre-release
   tags unless the plan says otherwise.

End the message with: "Answer each numbered decision, then reply `Plan approved`."
**Stop.**

**Done:** the admin has answered every decision, replied `Plan approved`, and no
blocker from phase 1 is open.

## Phase 3: The adoption PR

On a new branch `ci/adopt-release-tools` off the default branch, or the branch of the
adoption PR a previous run opened, the changes below and no others. An improvement you
notice on the way (a stricter check, a newer pin) goes in the report, for a PR of its
own:

- **Renames first:** a workflow that holds the name of a stub (Workflow file names, phase
  1) moves to a free name in the same PR, as publish-workflow.md, "Each existing job"
  says.
- **The three stubs** from `$rt/examples/stubs/` (`release.yml`, `backport.yml`,
  `pr-checks.yml`) into `.github/workflows/`, with the value of `$tag` and the
  `version-files` of the facts table.
- **The publish workflow:** follow [publish-workflow.md](publish-workflow.md).
- **Every inlined CodeArtifact value** of the facts table, in every workflow and job,
  not only the upload: mapped as publish-workflow.md, "The CodeArtifact variables" says.
- **`just changelog`:** release-tools is public, so the recipe for a public release-tools
  from `$rt/docs/adopting.md` (not `justfile-internal`), in the `justfile` (a new one if
  there is none).
- **The PR template:** the Migration section and the backport checklist item from
  `$rt/docs/adopting.md`, above any later heading of the existing template. Migration is
  never the last section: with no later heading, add the `## Checklist` heading after it,
  as the docs' template does. With no template, use the docs' template.
- **`CHANGELOG.md`:** with an existing baseline tag, a `## X.Y.Z (YYYY-MM-DD)` section
  for every final release up to it, generated as step 2 of
  `$rt/docs/repository-setup.md` shows; an empty file with `v0.0.0` only. An existing
  `CHANGELOG.md` whose release headings read `## X.Y.Z (YYYY-MM-DD)` stays as it is.
  Otherwise generate the new file, then carry over by hand every note the old file holds
  that the generated sections lack, in its wording, under the section of its release,
  and tell the admin.
- **Dependabot:** the `release-tools` group from `$rt/docs/versioning.md`, merged into
  the existing `github-actions` entry of `.github/dependabot.yml`, or added with one.
- **Development tags left out:** `"!v*.dev*"` in every `tags:` under `push:` that would
  match `v1.3.0.dev0` (Tag triggers, phase 1), the moved triggers included.
- **The old process removed:** the publishing `workflow_dispatch` routes,
  `.github/release.yml`, local copies of `release.py` and `cliff.toml`, and the
  `release` trigger of every workflow (tests, image builds, documentation), each replaced
  as publish-workflow.md says so that its work still runs for every release. Every doc
  of the old process points to **Actions → Release** instead.

Title the PR by the convention it introduces, for example `ci: 👷 adopt release-tools`.
Its description lists, for every final release up to the baseline, the section to
compare with `gh release view vX.Y.Z`, the stray groups git-cliff made from capitalised
types (such as `### Fix`), and every renamed file. Before you push, run actionlint on
`.github/workflows/`: `uvx --from actionlint-py actionlint`, or, when that cannot
download its binary, `docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:1.7.12`
or `nix run nixpkgs#actionlint`. Fix what it reports in the files you changed, and list
the rest in the PR description. When none runs, the PR description says
`actionlint not run: <the error>`. Then push the branch and open the PR.

**Done:**

- every `uses: Algorithmiq/release-tools…@` pin ends in the value of `$tag`
  (`grep -rn 'Algorithmiq/release-tools[^ ]*@' .github`);
- every `tags:` under `push:` in `.github/workflows` that would match `v1.3.0.dev0`
  also holds `"!v*.dev*"`;
- the `on:` of every workflow holds no `release`, and
  `grep -rn 'github.event.release' .github` prints nothing;
- in `.github/workflows`, `grep -rnF` finds no role ARN of the facts table that became
  a variable, and no line of `grep -rniE 'codeartifact|--domain-owner'` holds the AWS
  account or the domain of the facts table, except a role the admin kept (the account
  can also serve other services, such as a container registry; values such as a
  `pypi` repository or a region appear in the stub itself, so the check leaves them
  out);
- the done check of publish-workflow.md holds;
- actionlint passed before the push, or the PR description says why it did not run;
- the PR is open.

Tell the admin the PR is open and that phase 4 comes before its merge.

## Phase 4: The admin's steps before the merge

The admin's part of steps 1 to 7 of `$rt/docs/repository-setup.md` (step 4, the files,
is phase 3), as filled-in commands. The items below are numbered in the order to run
them, which is not the docs' order: hand over one at a time, **stop** until the admin
replies, then re-read its row of the facts table. Skip an item whose row is already at
its target. A ruleset whose name already exists gets a `PUT` on its id, never a second
`POST`.

1. **Bot credentials** (step 1): add this repository to the variable and the secret
   one by one, with this repository written in on the first line (`example` here), so
   that the command does not rely on the admin's shell:

   ```bash
   REPO=Algorithmiq/example
   REPO_ID=$(gh api "repos/${REPO:?}" --jq .id)
   gh api -X PUT "orgs/Algorithmiq/actions/variables/RELEASE_BOT_CLIENT_ID/repositories/${REPO_ID:?}"
   gh api -X PUT "orgs/Algorithmiq/actions/secrets/RELEASE_BOT_PRIVATE_KEY/repositories/${REPO_ID:?}"
   ```

   Not `--repos`: it replaces the whole list, and drops every repository left out.
2. **App installation** (step 1, web UI).
3. **Settings, immutable releases, the `backport` label** (step 3).
4. **The baseline** (step 2): `v0.0.0` only when the plan says so, before the tag
   ruleset: step 2's `git tag` and `git push` with the commit the admin chose written
   in, and `gh workflow disable` before and `gh workflow enable` after them for a
   tag-push publishing workflow phase 1 found.
5. **The tag ruleset** (step 5): its JSON, with the App ID, in `release-tags.json` in
   the `mktemp -d` directory, shown in full, and step 5's `gh api -X POST` with
   `--input` and that file's literal absolute path, as in the example at the top.
6. **The `release/*` ruleset** (step 6): its JSON, with the App ID, the checks the
   admin chose (each with its `integration_id` from the default branch's ruleset, or
   `15368` for a GitHub Actions check) and the approvals, in `release-branches.json` in
   the same directory, shown in full like step 5's, and step 6's `gh api -X POST`.
7. **The package index** (step 7): PyPI, the Trusted Publisher (web UI), with the
   owner, repository, workflow file name and environment of the publish workflow written
   in; for a project already on PyPI, the admin checks that its publisher matches them
   (a renamed file breaks it). CodeArtifact and no package, nothing.

**Done:** re-running phase 1 shows each of these rows at its target, and the admin has
confirmed the app installation.

## Phase 5: After the merge

The admin squash-merges the adoption PR. **Stop** until they report it merged.

Then read the Rulesets and Classic branch protection rows of phase 1 again: days can
pass between phase 1 and the merge, and an organisation owner can add, change or remove
a ruleset of the default branch in the meantime. `gh api repos/$REPO/rules/branches/main`
lists every ruleset that applies to it now. Phase 5 works on these, not on phase 1's.

Then step 8 of `$rt/docs/repository-setup.md`, on the default branch's rulesets read
again, whatever their name, that have a `pull_request` or `required_status_checks`
rule and `enforcement` `active`. Leave a `disabled` or `evaluate` one as it is, and say
so in the report: it requires nothing today, and if someone activates it, it needs the
bot's bypass. A repository ruleset requires `PR checks / PR title` and
`PR checks / Migration notes` on the default branch, and the release bot bypasses every
one of those rulesets, without which every changelog PR waits for an approval. Hand
over step 8's command once per ruleset, with its id written in place of
`<the ruleset id>` and the App ID in `--argjson app`:

- a repository ruleset (`source_type` `Repository`) as step 8 has it, with the checks;
- an organisation ruleset (`source_type` `Organization`) gets the bypass only:
  `--argjson checks '[]'`, and `orgs/Algorithmiq/rulesets/<id>` instead of `repos/…`
  in both calls, the read too, so that the `PUT` starts from the ruleset as the
  organisation holds it. It goes to an organisation owner, saying that the bot's
  bypass then covers every repository the ruleset targets. Never the checks: the
  ruleset would require them in repositories without the PR-checks stub, where they
  never report, and block every PR there;
- with no active repository ruleset on the default branch, step 8's `PR checks`
  ruleset, its JSON in a file as in phase 4, item 5;
- if a ruleset required other checks for PR titles or migration notes, the same jq
  removes them (`$rt/docs/caveats.md`, check names).

In an older release, step 8 finds the ruleset by name (`id=$(…)`) and appends without
looking: write the id in place of that line, leave out of the jq a check or the bypass
actor the ruleset already holds, give a repository ruleset without a
`required_status_checks` rule one first, and give an organisation ruleset the bypass
only.

**Done:** `gh api repos/$REPO/rulesets/<id>` shows both checks required on the default
branch by a repository ruleset with `enforcement` `active`, and the App ID is among the
bypass actors of each of those rulesets. An organisation ruleset is done when
`gh api orgs/Algorithmiq/rulesets/<id>` lists the App ID among its bypass actors; until
the owner has run its command, it is under **Waiting for** in the report, with the
command and the owner it went to, and phase 6 goes ahead: the changelog PR then waits
for an approval.

## Phase 6: The first release, and the report

Ask the admin whether a deprecation is due for removal (`$rt/docs/process.md`: a
`DeprecationWarning` names the earliest version that removes it). Then hand over the
first release: **Actions → Release → Run workflow** on `main` with a bump (`minor` or
`major`) and a stage (`rc` by default; `beta` or `alpha` to start earlier), or
`gh workflow run release.yml -R <owner/name> --ref main -f bump=minor -f stage=rc` with
the repository written in. Every pre-release is published to the package index.
**Stop** until the admin reports the run's result, then read it:
`gh run list -R $REPO -w release.yml -L 1`, and `gh release view` of the tag it made.

End with a report:

- what was done, and by whom;
- what is still waiting for a human, with its command;
- from `$rt/docs/caveats.md`, what matters to the team from now on: the changelog PR
  merges itself only with the bypass of phase 5; an older release line runs the
  release-tools version its branch pins; workflows on `release` events no longer run;
  after each final, `main` carries a `vX.(Y+1).0.dev0` tag, which nothing publishes and
  which every workflow on `push: tags` leaves out;
- last, the line on commands run that were not reads (see "What you run").

**Done:** the report is written. The adoption is complete when its waiting list is
empty.

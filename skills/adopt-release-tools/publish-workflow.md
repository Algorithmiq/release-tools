# Restructuring the publish workflow

Read with `SKILL.md`, phase 3. `$rt` is the clone of release-tools at `$tag`.

## The target

`$rt/docs/adopting.md`, "The publish workflow" gives the shape:

- triggered by `push: tags: ["v*"]` only, with `cancel-in-progress: false`;
- **build** (with the repository's version check) → **draft_release** → **upload** →
  **publish_release**, always last: publishing the GitHub release makes it immutable;
- it runs for every tag the release bot pushes: alphas, betas, release candidates and
  finals.

## The variant

| The repository publishes to | Start from | Upload |
| --- | --- | --- |
| PyPI | `$rt/examples/stubs/deploy.yml` | Trusted Publishing; the admin adds the publisher (step 7) |
| AWS CodeArtifact | `$rt/examples/stubs/deploy-codeartifact.yml`, see `$rt/docs/adopting.md`, "Publishing to AWS CodeArtifact" | attests the files, assumes `vars.CODEARTIFACT_WRITE_ROLE`, runs `uv publish` |
| Both | `$rt/examples/stubs/deploy.yml`, with the `upload_codeartifact` job of `deploy-codeartifact.yml` added | both jobs need `draft_release`, and `publish_release` needs both |
| No package index | `$rt/examples/stubs/deploy.yml` without `upload_pypi` | none: `publish_release` needs `draft_release`. Keep `build` while the release attaches files (wheels, a bundle). With nothing to attach, drop `build` too, keep `draft_release` without its download step and `files`, and keep the version check in a job that `draft_release` needs, if the repository has one |

Anything else is a question for the admin, not a guess: a publish workflow that another
workflow calls (`workflow_call`, `workflow_run`) or that a shared workflow provides, an
index other than these, or a package that is not Python.

Keep the existing file name (usually `deploy.yml`) and the repository's build: its
steps, runners, Python versions, wheels, and the authentication a build with private
dependencies needs. A build step that assumes a CodeArtifact read role stays, with the
role read from `vars.CODEARTIFACT_READ_ROLE` (below). The one
exception to the name: a publish workflow named `release.yml`, `backport.yml` or
`pr-checks.yml` moves to `deploy.yml` (or another free name), so that the stub can take
its name. A PyPI Trusted Publisher names the file, so the admin updates it (step 7).

## The CodeArtifact variables

Every inlined CodeArtifact value, in every workflow and job (builds, image and
documentation jobs, the upload), becomes the organisation variable that holds it:

| Inlined value | Becomes |
| --- | --- |
| AWS account (`--domain-owner`) | `vars.CODEARTIFACT_DOMAIN_OWNER` |
| `--domain` | `vars.CODEARTIFACT_DOMAIN` |
| `--region`, `aws-region` | `vars.CODEARTIFACT_REGION` |
| `--repository` | `vars.CODEARTIFACT_REPOSITORY` |
| the role ARN a build or an image job assumes to read packages | `vars.CODEARTIFACT_READ_ROLE` |
| the role ARN the upload assumes | `vars.CODEARTIFACT_WRITE_ROLE` |

A role ARN maps whole to its role variable, never split into account and name. The
account and region of another service (a container registry's login, say) stay as they
are, even when they equal the CodeArtifact ones.

A role is a CodeArtifact value only when its job uses it for CodeArtifact alone (a
token, a login). A role that the job also uses for something else (S3, a deployment),
or whose name says it serves more (`…_S3`, `…-deploy`), may hold permissions that the
CodeArtifact role lacks, used by code the workflow does not show. Swap it for nothing
on your own: it is a question of phase 2, and it stays as it is unless the admin says
the CodeArtifact role covers that job.

An inlined value that differs from its variable's (another repository name, say) moves
the packages once the workflow reads the variable: it is a question of phase 2 (SKILL.md,
phase 1, "CodeArtifact variables"). Write the workflow only once the admin has answered
it, and record the answer in the PR description.

## Each existing job

Place every job of the existing workflow:

- **Build jobs** become `build`, or several jobs that `draft_release` needs. Every file
  to attach is uploaded as an artifact; `draft_release` and the upload download them
  (`pattern` and `merge-multiple: true` for several artifacts), and every glob of
  `draft-release`'s `files` matches.
- **The version check stays,** reading the tag from `GITHUB_REF_NAME` instead of
  `github.event.release`. With no check in the repository, add the stub's. When a
  `VERSION` file is kept in step with the tags, the bot now writes it (`version-files`),
  and the check compares it with the tag.
- **The upload** becomes the variant's upload job, as the stub has it: its `twine` or
  `uv publish` step is replaced, not kept, and `pyproject.toml` stays as it is.
- **Jobs that ship something for the tag** (container images, documentation) stay, and
  every one of them joins the `needs` of `publish_release`: the release is published
  only once everything it ships exists.
- **Jobs that also run for pull requests or pushes to the default branch** (test builds,
  preview images) are copied: the publish workflow keeps its tag-only job, and the
  copy moves to a separate workflow, for example `build.yml`, with their other triggers
  and `cancel-in-progress: true`. A publish run is never cancelled; a PR build should
  be. A check that a ruleset requires keeps its name (the workflow's and the job's).

## The old triggers

- `release` triggers leave the publish workflow, and so does any `workflow_dispatch`
  input or job that publishes ("force upload"): only the bot's tags publish.
- **Other workflows with a `release` trigger** (release-tools publishes with
  `GITHUB_TOKEN`, which starts no workflows):
  - the jobs that ship something for the tag (an image push, a documentation deploy)
    move into the publish workflow, as above;
  - the jobs that ship nothing (tests) get `push: tags: ["v*"]` in place of the
    `release` trigger;
  - the workflow's other triggers (pull requests, pushes to the default branch) and
    their jobs stay in its file.
- **Final tags only:** a moved job or workflow runs for every pre-release tag too. Where
  the admin chose finals only (phase 2), a workflow gets
  `tags: ["v[0-9]+.[0-9]+.[0-9]+"]`, and a job in the publish workflow
  `if: ${{ !contains(github.ref_name, 'a') && !contains(github.ref_name, 'b') && !contains(github.ref_name, 'rc') }}`
  (the bot's pre-release tags end in `aN`, `bN` or `rcN`). `publish_release` still needs
  a skipped job: add `if: ${{ !cancelled() && !failure() }}` to it.
- `.github/release.yml`, the configuration of GitHub's generated notes, goes: the
  `release-notes` action writes the notes.

## What stays as it is

- The repository's pins of third-party actions; only `Algorithmiq/release-tools`
  references move to `$tag`. A job copied from a stub keeps the stub's pins.
- Permissions per job, as in the stub: `contents: write` for `draft_release` and
  `publish_release`; `id-token: write` where a job assumes an AWS role or uses Trusted
  Publishing.

**Done:** the workflow triggers on `v*` tags only; `publish_release` needs every job
that ships something; no job reads `github.event.release`; no workflow has a `release`
trigger; every CodeArtifact value reads a `vars.CODEARTIFACT_*` variable; actionlint
passes, or the PR description says why it did not run (SKILL.md, phase 3).

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
| AWS CodeArtifact | `$rt/examples/stubs/deploy-codeartifact.yml`, see `$rt/docs/adopting.md`, "Publishing to AWS CodeArtifact" | assumes `vars.CODEARTIFACT_WRITE_ROLE`, runs `twine upload` |
| nothing | `$rt/examples/stubs/deploy.yml` without `upload_pypi`, and without `build` when nothing is attached | none: `publish_release` needs `draft_release` |

Keep the existing file name (usually `deploy.yml`) and the repository's build: its
steps, runners, Python versions, wheels, and the authentication a build with private
dependencies needs. A build step that assumes a CodeArtifact read role stays, with
`vars.CODEARTIFACT_READ_ROLE`.

## The CodeArtifact variables

Every inlined CodeArtifact value, in every workflow and job (builds, image and
documentation jobs, the upload), becomes the organisation variable that holds it:

| Inlined value | Becomes |
| --- | --- |
| AWS account (`--domain-owner`, the account in a role ARN) | `vars.CODEARTIFACT_DOMAIN_OWNER` |
| `--domain` | `vars.CODEARTIFACT_DOMAIN` |
| `--region`, `aws-region` | `vars.CODEARTIFACT_REGION` |
| `--repository` | `vars.CODEARTIFACT_REPOSITORY` |
| the role a build or an image job assumes to read packages | `vars.CODEARTIFACT_READ_ROLE` |
| the role the upload assumes | `vars.CODEARTIFACT_WRITE_ROLE` |

When `gh variable list --org Algorithmiq` shows a variable's value and it differs from
the inlined one (another repository name, say), the PR description says so for the admin
to confirm.

## Each existing job

Place every job of the existing workflow:

- **Build jobs** become `build`, or several jobs that `draft_release` needs. Every file
  to attach is uploaded as an artifact; `draft_release` and the upload download them
  (`pattern` and `merge-multiple: true` for several artifacts), and every glob of
  `draft-release`'s `files` matches.
- **The version check stays.** When a `VERSION` file is kept in step with the tags, the
  bot now writes it (`version-files`), and the check compares it with the tag.
- **The upload** becomes the variant's upload job. Inlined CodeArtifact values (account,
  roles, domain, region, repository) become the `vars.CODEARTIFACT_*` variables, in the
  build too.
- **Jobs that ship something for the tag** (container images, documentation) stay, and
  every one of them joins the `needs` of `publish_release`: the release is published
  only once everything it ships exists.
- **Jobs that also run for pull requests or pushes to the default branch** (test builds,
  preview images) move to a separate workflow, for example `build.yml`, with their own
  triggers and `cancel-in-progress: true`: a publish run is never cancelled, a PR build
  should be.

## The old triggers

- `release` triggers leave the publish workflow, and so does any `workflow_dispatch`
  input or job that publishes ("force upload"): only the bot's tags publish.
- **Other workflows with a `release` trigger** (tests, image builds) get
  `push: tags: ["v*"]` instead, or move into the publish workflow when they ship
  something: release-tools publishes with `GITHUB_TOKEN`, which starts no workflows.
- `.github/release.yml`, the configuration of GitHub's generated notes, goes: the
  `release-notes` action writes the notes.

## What stays as it is

- The repository's pins of third-party actions; only `Algorithmiq/release-tools`
  references move to `$tag`.
- Permissions per job, as in the stub: `contents: write` for `draft_release` and
  `publish_release`; `id-token: write` where a job assumes an AWS role or uses Trusted
  Publishing.

**Done:** the workflow triggers on `v*` tags only; `publish_release` needs every job
that ships something; no job reads `github.event.release`; no workflow has a `release`
trigger; every CodeArtifact value reads a `vars.CODEARTIFACT_*` variable; actionlint
passes.

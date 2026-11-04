# Per-repository setup

A repository admin does this when a repository adopts the process. Set
`REPO=Algorithmiq/<name>` and `APP_ID=<the App ID>` first. Steps 1 to 7 come before
merging the PR that adds the stubs, 8 after it.

The repository's default branch must be `main`: the release workflow starts releases
from it and adds the changelog to it. Rename it first if it isn't (Settings → Branches),
which retargets the open PRs; everyone then updates their clones.

1. **Install the app and share the credentials** with the repository: add it to the app's
   installation (Organisation settings → GitHub Apps → algorithmiq-release-bot →
   Configure), and to the `--repos` lists of the variable and the secret.
2. **The baseline: where versions count from and the changelog starts.** The release
   workflow counts versions from the newest final tag `vX.Y.Z`, and the changelog starts
   there. Settle it before the tag ruleset (step 5) exists.

   - **A repository that released by hand has final tags**: the newest one is the
     baseline; tag nothing. If its newest `v*` tag is a pre-release without its final
     (`v0.4.0rc1` but no `v0.4.0`), release that final the old way first. If the package
     index has a final version newer than the newest final tag, tag that version's commit
     `vX.Y.Z` first.
   - **A repository with no final tags and nothing published** tags `v0.0.0` on the last
     commit that should not appear in the changelog. The first release is then `0.1.0`
     (or `1.0.0` when started with **major**). Pushing a tag runs the workflows of the
     tagged commit: if one of them publishes on tag pushes, disable it while you push
     (`gh workflow disable`, then `gh workflow enable`).

     ```bash
     git tag -a v0.0.0 -m "Start of the changelog" <commit>
     git push origin v0.0.0
     just changelog    # what the first release will contain
     ```

   **The releases before the baseline** belong in `CHANGELOG.md` too. Generate their
   sections in the PR that adds the stubs (step 4), with the `cliff.toml` of the
   release-tools tag the stubs pin, from a worktree at the baseline tag so that later
   commits stay out. The command replaces an existing `CHANGELOG.md`: keep or merge a
   hand-written one first.

   ```bash
   tmp=$(mktemp -d)
   git worktree add "$tmp/base" vX.Y.Z    # the baseline tag
   gh api -H "Accept: application/vnd.github.raw" \
     "repos/Algorithmiq/release-tools/contents/cliff.toml?ref=<the pinned tag>" > "$tmp/cliff.toml"
   GITHUB_REPOSITORY=$REPO uvx --from git-cliff==2.14.2 git-cliff \
     --config "$tmp/cliff.toml" --repository "$tmp/base" --output CHANGELOG.md
   git worktree remove "$tmp/base"
   ```

   Each final tag gets a `## X.Y.Z (date)` section; pre-release tags are skipped. Titles
   that are not conventional commits are left out, and a capitalised type (`Fix: …`)
   lands in a group of its own (`### Fix`): compare each section with that release's
   GitHub notes (`gh release view vX.Y.Z`), move stray entries into their groups and add
   what is missing. Release PRs add their sections above these.

3. **Settings.** Squash-merge only, with the PR title and description as the commit
   message (otherwise the migration notes never reach the changelog), auto-merge, automatic
   deletion of head branches, immutable releases, and the `backport` label:

   ```bash
   gh api -X PATCH repos/$REPO -F allow_squash_merge=true -F allow_merge_commit=false \
     -F allow_rebase_merge=false -F allow_auto_merge=true -F delete_branch_on_merge=true \
     -f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=PR_BODY
   gh api -X PUT repos/$REPO/immutable-releases
   gh label create backport -R $REPO --color B60205 \
     --description "Also ship this fix in the current release"
   ```

4. **Files.** The three stubs, the publish workflow, the `justfile` recipe, the Migration
   section of the PR template, the `CHANGELOG.md` of step 2 (empty if the baseline is
   `v0.0.0`), and the Dependabot group. Delete any local copies of `release.py` and
   `cliff.toml`. Retire publishing by hand: the publish workflow no longer runs on
   `release: published`, other workflows with a `release:` trigger move to
   `push: tags: ["v*"]` (see [Caveats](caveats.md)), and `.github/release.yml`, the
   configuration of GitHub's generated release notes, goes: the `release-notes` action
   writes them.
5. **Tag ruleset**: only the release bot creates, moves or deletes `v*` tags.

   ```bash
   gh api -X POST repos/$REPO/rulesets --input - <<EOF
   {"name": "release tags", "target": "tag", "enforcement": "active",
    "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
    "rules": [{"type": "creation"}, {"type": "update"}, {"type": "deletion"}],
    "bypass_actors": [{"actor_id": $APP_ID, "actor_type": "Integration", "bypass_mode": "always"}]}
   EOF
   ```

6. **`release/*` ruleset**: changes only through squash-merged PRs that pass CI, and only
   the bot creates the branches. List the repository's own required checks next to the PR
   checks (`15368` is the GitHub Actions app, which reports them):

   ```bash
   gh api -X POST repos/$REPO/rulesets --input - <<EOF
   {"name": "release branches", "target": "branch", "enforcement": "active",
    "conditions": {"ref_name": {"include": ["refs/heads/release/*"], "exclude": []}},
    "rules": [
     {"type": "creation"}, {"type": "deletion"}, {"type": "non_fast_forward"}, {"type": "required_linear_history"},
     {"type": "pull_request", "parameters": {"allowed_merge_methods": ["squash"], "dismiss_stale_reviews_on_push": true,
       "require_code_owner_review": false, "require_last_push_approval": false,
       "required_approving_review_count": 1, "required_review_thread_resolution": false}},
     {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": true,
       "required_status_checks": [{"context": "PR checks / PR title", "integration_id": 15368},
         {"context": "PR checks / Migration notes", "integration_id": 15368}]}}],
    "bypass_actors": [{"actor_id": $APP_ID, "actor_type": "Integration", "bypass_mode": "always"}]}
   EOF
   ```

7. **The package index** of the publish workflow. PyPI: add a (pending) Trusted
   Publisher with the repository, the workflow file name and the environment (`pypi` in
   the example). AWS CodeArtifact: nothing per repository; the organisation variables
   ([One-time organisation setup](organisation-setup.md), step 5) and the roles' trust
   policies cover every repository. The first pre-release is published straight away.
8. **After the stubs are on `main`: require the PR checks on `main` and let the bot
   bypass the `main` ruleset.** `pull_request_target` runs the workflow file of the base
   branch, so the checks never report until the stub is on `main`; requiring them earlier
   blocks every PR, including the one adding them. The bypass lets the bot merge its
   changelog PR at once, without a review or the PR checks (see [Caveats](caveats.md));
   without it, each changelog PR waits for a maintainer's approval.

   ```bash
   id=$(gh api repos/$REPO/rulesets --jq '.[] | select(.name == "main") | .id')
   gh api repos/$REPO/rulesets/$id | jq --argjson app "$APP_ID" '{name, target, enforcement, conditions,
     rules: (.rules | map(if .type == "required_status_checks"
       then .parameters.required_status_checks += [{"context": "PR checks / PR title", "integration_id": 15368},
                                                   {"context": "PR checks / Migration notes", "integration_id": 15368}]
       else . end)),
     bypass_actors: (.bypass_actors + [{"actor_id": $app, "actor_type": "Integration", "bypass_mode": "always"}])}' \
   | gh api -X PUT repos/$REPO/rulesets/$id --input -
   ```

   This assumes a `main` ruleset with a `required_status_checks` rule; create one first
   if there is none.

The first release: check that no deprecation is due for removal, then
**Actions → Release → Run workflow** on `main` (or
`gh workflow run release.yml -R $REPO --ref main -f bump=minor -f stage=rc`).

# One-time organisation setup

An organisation owner does this once. The commands need `gh` with the `admin:org` scope
(`gh auth refresh -h github.com -s admin:org`) and `jq`.

1. **Create the release bot GitHub App** (web UI only):
   <https://github.com/organizations/Algorithmiq/settings/apps/new>.
   - Name `algorithmiq-release-bot`; homepage `https://github.com/Algorithmiq`; webhook
     **not** active.
   - Repository permissions: **Contents** read and write (release branches, tags, the
     changelog), **Pull requests** read and write (release, backport and changelog PRs,
     merging the changelog PRs, the backport suggestions), **Workflows** read and write (pushing branches
     whose commits touch
     `.github/workflows/`). Metadata read-only is added automatically. Nothing else, no
     events. Installable only on this account.
   - Note the **App ID** (a number, for the rulesets) and the **Client ID** (`Iv23…`, for
     the workflows). Generate a **private key** and keep the `.pem` only until step 2.
   - **Install** it on `release-tools` and on every repository that adopts the process.
     release-tools needs it for its own releases, and the release workflow uses it to read
     release-tools when that repository is not public.
2. **Store the credentials** for the repositories that use them, release-tools included
   (`--repos` replaces the list, so always pass all of them):

   ```bash
   gh variable set RELEASE_BOT_CLIENT_ID --org Algorithmiq --visibility selected \
     --repos release-tools,AEGISS --body "$CLIENT_ID"
   gh secret set RELEASE_BOT_PRIVATE_KEY --org Algorithmiq --visibility selected \
     --repos release-tools,AEGISS < algorithmiq-release-bot.*.private-key.pem
   ```

3. **Allow the actions.** If the organisation restricts which actions and reusable
   workflows may run, allow `Algorithmiq/release-tools/*` and the actions it uses
   (`actions/checkout`, `actions/create-github-app-token`,
   `amannn/action-semantic-pull-request`, `korthout/backport-action`). The allow list of
   the calling repository applies to everything a reusable workflow uses.
4. **Visibility of release-tools.** Public is simplest and preferred. If it is internal or
   private instead:
   - release-tools → Settings → Actions → General → **Access**: "Accessible from
     repositories in the 'Algorithmiq' organization". Without it, no other repository can
     call its workflows or actions.
     ([docs](https://docs.github.com/en/actions/how-tos/reuse-automations/share-with-your-organization))
   - A public repository can only call public workflows, so release-tools must be public
     as soon as any public repository adopts it.
     ([docs](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations#access-to-reusable-workflows))
   - "Internal" exists only with GitHub Enterprise Cloud; otherwise it is private.
   - Dependabot needs access to release-tools to update the pins: add it to the
     organisation's "Grant Dependabot access to private repositories" list (in the
     organisation's code security settings).
   - Local changelog previews use the `gh` variant of `just changelog`.

   Nothing in the workflows changes: they read release-tools with a read-only token of the
   release bot either way (see [Design](design.md)).

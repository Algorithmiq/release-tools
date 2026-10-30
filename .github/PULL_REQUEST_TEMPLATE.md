<!-- The PR title becomes the changelog entry, so write it for users:
     `<type>(<optional scope>): <gitmoji> <description>`, `!` after the type for a breaking change.
     Bug fixes that should also reach the current release get the `backport` label. -->

## Summary

<!-- What this PR does and why. -->

<!-- Keep this section above the Checklist: the changelog takes everything up to the next heading. -->
## Migration
<!-- Required for breaking changes (!) and deprecations. Delete otherwise.
     What do users need to change? Show a before/after example if possible. -->

## Checklist

- [ ] Bug fix for the current release: add the `backport` label (or ask a maintainer to)
- [ ] `just lint` and `just test` pass
- [ ] docs/adopting.md, docs/organisation-setup.md, and docs/repository-setup.md updated if the stubs, inputs or setup changed
- [ ] Breaking change or deprecation: the Migration section says what consumers must change

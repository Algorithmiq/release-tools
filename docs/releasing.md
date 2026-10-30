# Releasing

Steps 1–3 are runs of **Actions → Release → Run workflow** on `main`, with a **bump**
(**minor** or **major**, counted from the newest final release) and a **stage**. Before
starting, a maintainer checks that no deprecation is due for removal.

1. **Alphas (optional).** Stage **alpha** tags `vX.Y.0aN` on `main`, published as a
   pre-release. Run it again for the next alpha; features keep landing on `main`.
2. **Betas (optional): the feature freeze.** Stage **beta** creates `release/X.Y` from
   `main`, tags `vX.Y.0b1` and opens the release PR `chore: release vX.Y.0` as a draft.
   From then on only backported fixes reach `X.Y`: each one merged into `release/X.Y`
   tags the next beta and updates the release PR. Features merged into `main` wait for
   the next release.
3. **Release candidates.** Stage **rc** promotes a release in beta: it tags `vX.Y.0rc1`
   on `release/X.Y` and marks the release PR ready for review. Without betas, it creates
   `release/X.Y` with `vX.Y.0rc1` and opens the release PR. Every backport then tags the
   next candidate. Testing pre-releases is optional
   (`pip install --pre <package>==X.Y.0rcN`).
4. **Release.** A maintainer reviews the changelog in the release PR and merges it. The
   bot tags `vX.Y.0`; the repository's publish workflow builds, drafts the GitHub release
   with every file attached, publishes to PyPI and publishes the release, which makes it
   immutable. The bot then adds the release's section of `CHANGELOG.md` to `main`
   through a PR that it merges itself, and closes the pending patch release PR of the
   previous line, if any: its support ends here, and its fixes are in `X.Y.0`. Merge
   that PR first to ship them.

The workflow refuses to go backwards (an alpha once `release/X.Y` exists, a beta once it
is at release candidates), and to create a release branch while another one has no final
release yet. `CHANGELOG.md` on `main` lists every final release of every line; to reword
an older section, edit it on `main` with a normal PR (a release PR only adds its own
section to `main`).

A published release never changes. A broken one is yanked on PyPI and replaced by a new
patch release. Only the bot creates `v*` tags.

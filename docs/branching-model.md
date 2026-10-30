# Branching model

`release/X.Y` is created at the feature freeze: the first beta, or the first release
candidate when there are no betas. Alphas never create a branch. Each step below is the
same history, later.

**1. v1.1.0 is out.** `release/1.1` was cut at `v1.1.0rc1`; merging its release PR tagged
`v1.1.0`, and the changelog was copied back to `main`. Features keep landing on `main`.

```mermaid
gitGraph TB:
  commit id: "feat: A" tag: "v1.1.0rc1"
  branch release/1.1
  commit id: "release v1.1.0" tag: "v1.1.0"
  checkout main
  commit id: "changelog v1.1.0"
  commit id: "feat: B"
```

**2. Alphas.** *Release, minor, alpha* tags `main`'s HEAD; each rerun tags the next alpha.
No branch, no release PR. Features keep landing.

```mermaid
gitGraph TB:
  commit id: "feat: A" tag: "v1.1.0rc1"
  branch release/1.1
  commit id: "release v1.1.0" tag: "v1.1.0"
  checkout main
  commit id: "changelog v1.1.0"
  commit id: "feat: B" tag: "v1.2.0a1"
  commit id: "feat: C" tag: "v1.2.0a2"
```

**3. Beta: the feature freeze.** *Release, minor, beta* cuts `release/1.2` at `main`'s HEAD
and tags `v1.2.0b1`; the release PR opens as a draft. `feat: E` lands on `main` after the
freeze, so it waits for 1.3. `fix: F` gets the `backport` label: because 1.2 is in
pre-release, it goes to **both** lines, tagging `v1.2.0b2` and updating the `v1.1.1`
release PR, which a maintainer merges.

```mermaid
gitGraph TB:
  commit id: "feat: A" tag: "v1.1.0rc1"
  branch release/1.1
  commit id: "release v1.1.0" tag: "v1.1.0"
  checkout main
  commit id: "changelog v1.1.0"
  commit id: "feat: B" tag: "v1.2.0a1"
  commit id: "feat: C" tag: "v1.2.0a2"
  commit id: "feat: D" tag: "v1.2.0b1"
  branch release/1.2
  checkout main
  commit id: "feat: E"
  commit id: "fix: F"
  checkout release/1.2
  cherry-pick id: "fix: F" tag: "v1.2.0b2"
  checkout release/1.1
  cherry-pick id: "fix: F" tag: ""
  commit id: "release v1.1.1" tag: "v1.1.1"
  checkout main
  commit id: "changelog v1.1.1"
```

**4. Release candidates.** *Release, minor, rc* promotes 1.2: it tags `v1.2.0rc1` on the
branch HEAD (the same commit as `v1.2.0b2`) and marks the release PR ready. The next
backport, `fix: G`, tags `v1.2.0rc2` and still reaches 1.1 (pending `v1.1.2`).

```mermaid
gitGraph TB:
  commit id: "feat: A" tag: "v1.1.0rc1"
  branch release/1.1
  commit id: "release v1.1.0" tag: "v1.1.0"
  checkout main
  commit id: "changelog v1.1.0"
  commit id: "feat: B" tag: "v1.2.0a1"
  commit id: "feat: C" tag: "v1.2.0a2"
  commit id: "feat: D" tag: "v1.2.0b1"
  branch release/1.2
  checkout main
  commit id: "feat: E"
  commit id: "fix: F"
  checkout release/1.2
  cherry-pick id: "fix: F" tag: "v1.2.0b2 + v1.2.0rc1"
  checkout release/1.1
  cherry-pick id: "fix: F" tag: ""
  commit id: "release v1.1.1" tag: "v1.1.1"
  checkout main
  commit id: "changelog v1.1.1"
  commit id: "fix: G"
  checkout release/1.2
  cherry-pick id: "fix: G" tag: "v1.2.0rc2"
  checkout release/1.1
  cherry-pick id: "fix: G" tag: ""
```

**5. Final and patches.** The pending `v1.1.2` is merged, then the 1.2 release PR, which
tags `v1.2.0`. From now on 1.1 is unsupported and backports go to `release/1.2` only:
`fix: H` updates the `v1.2.1` release PR, and merging it ships the patch, with no
pre-releases.

```mermaid
gitGraph TB:
  commit id: "feat: A" tag: "v1.1.0rc1"
  branch release/1.1
  commit id: "release v1.1.0" tag: "v1.1.0"
  checkout main
  commit id: "changelog v1.1.0"
  commit id: "feat: B" tag: "v1.2.0a1"
  commit id: "feat: C" tag: "v1.2.0a2"
  commit id: "feat: D" tag: "v1.2.0b1"
  branch release/1.2
  checkout main
  commit id: "feat: E"
  commit id: "fix: F"
  checkout release/1.2
  cherry-pick id: "fix: F" tag: "v1.2.0b2 + v1.2.0rc1"
  checkout release/1.1
  cherry-pick id: "fix: F" tag: ""
  commit id: "release v1.1.1" tag: "v1.1.1"
  checkout main
  commit id: "changelog v1.1.1"
  commit id: "fix: G"
  checkout release/1.2
  cherry-pick id: "fix: G" tag: "v1.2.0rc2"
  checkout release/1.1
  cherry-pick id: "fix: G" tag: ""
  commit id: "release v1.1.2" tag: "v1.1.2"
  checkout main
  commit id: "changelog v1.1.2"
  checkout release/1.2
  commit id: "release v1.2.0" tag: "v1.2.0"
  checkout main
  commit id: "changelog v1.2.0"
  commit id: "fix: H"
  checkout release/1.2
  cherry-pick id: "fix: H" tag: ""
  commit id: "release v1.2.1" tag: "v1.2.1"
  checkout main
  commit id: "changelog v1.2.1"
```

The diagrams leave out the bot's `release-pr/X.Y`, `changelog/vX.Y.Z` and backport
branches, and the commits that record the version for pre-release tags when a repository
has version files.

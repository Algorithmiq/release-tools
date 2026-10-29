#!/usr/bin/env bash
# Opens or updates the release PR of release/$SERIES, as described in "The release
# process" in README.md: the branch release-pr/$SERIES is $HEAD_SHA plus one commit
# that sets the version files to $PENDING and adds its section to CHANGELOG.md. Run by
# the start and update jobs of .github/workflows/release.yml in the root of the
# repository being released, with git-cliff and gh on PATH.
#
# Environment:
#   RELEASE_TOOLS  this repository, checked out (release.py, cliff.toml)
#   SERIES         X.Y of the release branch
#   PENDING        the version the PR releases (X.Y.Z)
#   STAGE          beta, rc or released; the PR is a draft during beta
#   HEAD_SHA       the commit of release/$SERIES to build the PR on
#   VERSION_FILES  the files that hold the version (see release.py)
#   RUNNER_TEMP    a scratch directory
#   GH_TOKEN       a token that can push branches and open PRs
set -euo pipefail

base="release/$SERIES"
pr_branch="release-pr/$SERIES"
title="chore: release v$PENDING"
git checkout --quiet -B "$pr_branch" "$HEAD_SHA"

python3 "$RELEASE_TOOLS/release.py" set-version "$PENDING"
# Start from main's CHANGELOG.md: it has every release so far, including the patch
# releases of the previous line made after this branch was created.
if git cat-file -e origin/main:CHANGELOG.md 2> /dev/null; then
  git show origin/main:CHANGELOG.md > CHANGELOG.md
fi
[ -f CHANGELOG.md ] || touch CHANGELOG.md
cliff=(git cliff --config "$RELEASE_TOOLS/cliff.toml" --unreleased --tag "v$PENDING")
"${cliff[@]}" --prepend CHANGELOG.md
"${cliff[@]}" --strip header > "$RUNNER_TEMP/notes.md"
# shellcheck disable=SC2086 # VERSION_FILES is a space-separated list
git add CHANGELOG.md $VERSION_FILES
git commit --quiet -m "$title"
git push --quiet --force origin "$pr_branch"

{
  if [ "$STAGE" = beta ]; then
    echo "Draft while v$PENDING is in beta. To move to release candidates, run Release with stage \`rc\`."
    echo
  fi
  echo "Merging this PR releases **v$PENDING**."
  echo
  echo "It is updated automatically whenever a change lands on \`$base\`."
  if [[ "$PENDING" != *.0 ]]; then
    echo "Every fix backported to \`$base\` is added to this PR. Merge it when the fixes"
    echo "should ship. Patch releases have no release candidates."
  fi
  echo "Wording fixes to \`CHANGELOG.md\` can be pushed to this PR, but make them"
  echo "just before merging: the next update overwrites them."
  echo
  echo "---"
  echo
  cat "$RUNNER_TEMP/notes.md"
} > "$RUNNER_TEMP/body.md"

found=$(gh pr list --head "$pr_branch" --base "$base" --state open \
  --json number,isDraft --jq '.[0] // empty | "\(.number) \(.isDraft)"')
if [ -n "$found" ]; then
  read -r number draft <<< "$found"
  gh pr edit "$number" --title "$title" --body-file "$RUNNER_TEMP/body.md"
  if [ "$STAGE" = beta ] && [ "$draft" = false ]; then
    gh pr ready "$number" --undo
  elif [ "$STAGE" != beta ] && [ "$draft" = true ]; then
    gh pr ready "$number"
  fi
else
  flags=()
  if [ "$STAGE" = beta ]; then flags+=(--draft); fi
  gh pr create ${flags[@]+"${flags[@]}"} --head "$pr_branch" --base "$base" \
    --title "$title" --body-file "$RUNNER_TEMP/body.md"
fi

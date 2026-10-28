set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set positional-arguments := true

# The uv environments and the hooks' environments must only see their own packages: a
# PYTHONPATH from the shell (Nix sets one) would shadow them and break source builds.
unexport PYTHONPATH

# List the recipes.
default:
    @just --list

# Install the tools (pytest, ruff, ty, prek, git-cliff); extra arguments go to `uv sync`.
build *ARGS:
    uv sync "$@"

# Format the code and apply the safe lint fixes.
fmt:
    uv run --no-sync ruff format .
    uv run --no-sync ruff check --fix .

# Run every hook on the whole tree: ruff, ty, actionlint, the workflow and action schemas.
lint:
    uv run --no-sync prek run --all-files

# Type-check with ty.
typecheck:
    uv run --no-sync ty check

# Run the tests of release.py and cliff.toml; extra arguments go to pytest.
test *ARGS:
    uv run --no-sync pytest "$@"

# Preview the changelog entry of the next release of this repository.
changelog:
    GITHUB_REPOSITORY="${GITHUB_REPOSITORY:-Algorithmiq/release-tools}" uv run --no-sync git-cliff --unreleased

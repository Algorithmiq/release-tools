{
  mkShell,
  python,
  git,
  just,
  uv,
}:

# The tools (ruff, ty, prek, git-cliff, shellcheck, pytest, zensical) come from uv.lock
# through `just build`, so their versions are pinned in one place. On NixOS their binary
# wheels need nix-ld.
mkShell {
  nativeBuildInputs = [
    git
    just
    python
    uv
  ];

  shellHook = ''
    # The python setup hook exports the site-packages of this shell's Python inputs; uv's
    # virtual environments must only see their own packages.
    unset PYTHONPATH

    # Use this shell's CPython rather than one uv downloads.
    export UV_PYTHON_PREFERENCE=only-system
    export UV_PYTHON="${python}/bin/python"
  '';
}

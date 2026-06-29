{ pkgs, ... }:
pkgs.mkShell {
  packages = with pkgs; [
    python313
    python313Packages.pip
    ruff
    mypy

    # Docs: `mdbook serve docs` for a live preview. mdbook-linkcheck2 backs the
    # link check that runs as part of `mdbook build` / `nix flake check`.
    mdbook
    mdbook-mermaid
    mdbook-linkcheck2
  ];
}

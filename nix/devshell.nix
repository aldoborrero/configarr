{ pkgs, ... }:
let
  python = pkgs.python313.withPackages (
    ps: with ps; [
      # runtime libs needed to import configarr.config / configarr.diff
      click
      pydantic
      pyyaml
      requests
      rich
      # test tooling
      pytest
      responses
      pip
    ]
  );
in
pkgs.mkShell {
  packages = [
    python
    pkgs.ruff
    pkgs.mypy

    # Docs: `mdbook serve docs` for a live preview. mdbook-linkcheck2 backs the
    # link check that runs as part of `mdbook build` / `nix flake check`.
    pkgs.mdbook
    pkgs.mdbook-mermaid
    pkgs.mdbook-linkcheck2
  ];
}

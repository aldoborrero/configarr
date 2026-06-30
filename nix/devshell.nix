{ pkgs, ... }:
let
  # Same runtime libs the CI checks use, plus the dev tooling. mypy lives inside
  # the python env so it resolves pydantic/requests stubs (matching the mypy gate).
  python = (import ./lib { inherit pkgs; }).pyWith (
    ps: with ps; [
      pytest
      responses
      mypy
      types-requests
      types-pyyaml
      pip
    ]
  );
in
pkgs.mkShell {
  packages = [
    python
    pkgs.ruff

    # Docs: `mdbook serve docs` for a live preview. mdbook-linkcheck2 backs the
    # link check that runs as part of `mdbook build` / `nix flake check`.
    pkgs.mdbook
    pkgs.mdbook-mermaid
    pkgs.mdbook-linkcheck2
  ];
}

{ pkgs, ... }:
# Build the book under `nix flake check`. The build runs the mdbook-linkcheck2
# backend, so a broken internal link or a stale {{#include}} fails CI here.
import ../packages/docs.nix { inherit pkgs; }

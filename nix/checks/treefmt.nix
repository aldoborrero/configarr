# Fail CI if anything is not formatted. Uses treefmt-nix's own check derivation
# (config.build.check) over the flake source — no hand-rolled runner needed.
{
  inputs,
  flake,
  pkgs,
  ...
}:
(flake.lib.treefmtEval pkgs).config.build.check inputs.self

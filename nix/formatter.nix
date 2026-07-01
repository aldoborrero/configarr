# The `nix fmt` formatter: treefmt-nix wrapper (nixfmt + ruff + yamlfmt). The
# config lives in flake.lib.treefmtEval so the treefmt CI check reuses it.
{
  pkgs,
  flake,
  ...
}:
(flake.lib.treefmtEval pkgs).config.build.wrapper

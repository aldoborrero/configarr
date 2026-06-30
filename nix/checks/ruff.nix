{
  pkgs,
  inputs,
  ...
}:
# Lint gate: enforce the real ruff ruleset (pyproject [tool.ruff.lint]) so style
# and correctness lints — not just import sorting — fail CI. Scoped to the diff
# engine and its tests, matching the mypy gate; the ruleset lives in pyproject so
# `nix develop -c ruff check` and this check agree.
let
  helpers = import ../lib { inherit pkgs; };
in
helpers.srcCheck {
  name = "ruff-check";
  src = inputs.self;
  command = "${pkgs.ruff}/bin/ruff check configarr tests";
}

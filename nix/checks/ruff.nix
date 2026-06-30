{
  pkgs,
  inputs,
  ...
}:
# Lint gate: enforce the real ruff ruleset (pyproject [tool.ruff.lint]) so style
# and correctness lints — not just import sorting — fail CI. Scoped to the diff
# engine and its tests, matching the mypy gate; the ruleset lives in pyproject so
# `nix develop -c ruff check` and this check agree.
pkgs.runCommandLocal "ruff-check" { } ''
  cp -r ${inputs.self} src
  chmod -R u+w src
  export HOME=$(mktemp -d)
  cd src
  ${pkgs.ruff}/bin/ruff check configarr/diff tests
  touch $out
''

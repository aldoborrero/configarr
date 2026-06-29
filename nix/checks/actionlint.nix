{ pkgs, ... }:
# Lint the GitHub Actions workflows. shellcheck is on PATH so actionlint also
# checks the `run:` shell scripts embedded in the workflows.
pkgs.runCommandLocal "actionlint-check"
  {
    nativeBuildInputs = [
      pkgs.actionlint
      pkgs.shellcheck
    ];
  }
  ''
    actionlint -color ${../../.github/workflows}/*.yml
    touch $out
  ''

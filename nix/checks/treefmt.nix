{
  pkgs,
  inputs,
  ...
}:
# Fail CI if anything is not formatted. `treefmt --ci` enables --no-cache and
# --fail-on-change. The source is copied to a writable dir because the formatter
# rewrites files in place before checking for changes.
let
  treefmt = import ../formatter.nix { inherit pkgs; };
in
pkgs.runCommandLocal "treefmt-check" { } ''
  cp -r ${inputs.self} src
  chmod -R u+w src
  export HOME=$(mktemp -d)
  cd src
  ${pkgs.lib.getExe treefmt} --ci --tree-root .
  touch $out
''

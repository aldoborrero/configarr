{
  pkgs,
  inputs,
  ...
}:
# Fail CI if anything is not formatted. `treefmt --ci` enables --no-cache and
# --fail-on-change; the source is copied writable because the formatter rewrites
# in place before checking for changes.
let
  helpers = import ../lib { inherit pkgs; };
  treefmt = import ../formatter.nix { inherit pkgs; };
in
helpers.srcCheck {
  name = "treefmt-check";
  src = inputs.self;
  command = "${pkgs.lib.getExe treefmt} --ci --tree-root .";
}

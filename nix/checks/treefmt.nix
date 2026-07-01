{
  pkgs,
  inputs,
  flake,
  ...
}:
# Fail CI if anything is not formatted. `treefmt --ci` enables --no-cache and
# --fail-on-change; the source is copied writable because the formatter rewrites
# in place before checking for changes.
let
  treefmt = import ../formatter.nix { inherit pkgs; };
in
flake.lib.srcCheck pkgs {
  name = "treefmt-check";
  src = inputs.self;
  command = "${pkgs.lib.getExe treefmt} --ci --tree-root .";
}

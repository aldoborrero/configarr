{
  pkgs,
  inputs,
  flake,
  ...
}:
# Run the pytest suite in CI. The tests import only configarr.* (client-free), so
# the nix-only generated API clients are not needed here.
let
  py = flake.lib.pyWith pkgs (
    ps: with ps; [
      pytest
      responses
    ]
  );
in
flake.lib.srcCheck pkgs {
  name = "pytest-check";
  src = inputs.self;
  command = "${py}/bin/pytest -q";
}

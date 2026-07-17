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
  # The trash git-source tests shell out to `git` (a local repo stands in for a
  # remote), so it must be on PATH inside the sandbox.
  nativeBuildInputs = [ pkgs.git ];
  command = "${py}/bin/pytest -q";
}

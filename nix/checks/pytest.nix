{
  pkgs,
  inputs,
  ...
}:
# Run the pytest suite in CI. The tests import only configarr.*
# and configarr.config/models (client-free), so the nix-only generated API
# clients are not needed here.
let
  helpers = import ../lib { inherit pkgs; };
  py = helpers.pyWith (
    ps: with ps; [
      pytest
      responses
    ]
  );
in
helpers.srcCheck {
  name = "pytest-check";
  src = inputs.self;
  command = "${py}/bin/pytest -q";
}

{
  pkgs,
  inputs,
  flake,
  ...
}:
# Type-check configarr so a divergent provider or signature fails CI. mypy shares
# one python env with the runtime deps + stubs so it resolves pydantic/requests/
# yaml types; configarr is client-free, so the generated clients are not needed.
let
  py = flake.lib.pyWith pkgs (
    ps: with ps; [
      mypy
      types-requests
      types-pyyaml
    ]
  );
in
flake.lib.srcCheck pkgs {
  name = "mypy-check";
  src = inputs.self;
  command = "${py}/bin/mypy --strict configarr";
}

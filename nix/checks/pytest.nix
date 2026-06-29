{
  pkgs,
  inputs,
  ...
}:
# Run the pytest suite in CI. The diff-engine tests import only configarr.diff.*
# and configarr.config/models (client-free), so the nix-only generated API
# clients are not needed here.
let
  py = pkgs.python313.withPackages (
    ps: with ps; [
      click
      pydantic
      pyyaml
      requests
      rich
      pytest
      responses
    ]
  );
in
pkgs.runCommandLocal "pytest-check" { } ''
  cp -r ${inputs.self} src
  chmod -R u+w src
  export HOME=$(mktemp -d)
  cd src
  ${py}/bin/pytest -q
  touch $out
''

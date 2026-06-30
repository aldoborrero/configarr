{
  pkgs,
  inputs,
  ...
}:
# Type-check the diff engine so a divergent provider fails CI. ResourceProvider
# is the typed seam the runner/registry depend on, so a provider that drops or
# mis-signs a method is caught here. mypy and the runtime deps must live in one
# python env (withPackages) so mypy resolves pydantic/requests stubs; the diff
# engine is client-free, so the nix-only generated clients are not needed.
let
  py = pkgs.python313.withPackages (
    ps: with ps; [
      mypy
      types-requests
      click
      pydantic
      pyyaml
      requests
      rich
    ]
  );
in
pkgs.runCommandLocal "mypy-check" { } ''
  cp -r ${inputs.self} src
  chmod -R u+w src
  export HOME=$(mktemp -d)
  cd src
  ${py}/bin/mypy --strict configarr/diff
  touch $out
''

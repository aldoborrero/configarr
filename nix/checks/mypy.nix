{
  pkgs,
  inputs,
  ...
}:
# Type-check the diff engine so a divergent provider fails CI. mypy shares one
# python env with the runtime deps so it resolves pydantic/requests stubs; the
# diff engine is client-free, so the generated clients are not needed.
let
  helpers = import ../lib { inherit pkgs; };
  py = helpers.pyWith (
    ps: with ps; [
      mypy
      types-requests
    ]
  );
in
helpers.srcCheck {
  name = "mypy-check";
  src = inputs.self;
  command = "${py}/bin/mypy --strict configarr/diff";
}

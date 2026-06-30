# Shared helpers for the flake's checks/devshell. Exposed by blueprint as
# `lib`, but also imported directly by the checks via `import ../lib {inherit pkgs;}`.
# `pkgs` defaults to null so blueprint can evaluate this without a system context —
# the helpers (functions) are only forced when a check actually calls them with pkgs.
{
  pkgs ? null,
  ...
}:
let
  inherit (pkgs) python313;

  # Runtime libraries configarr imports (config parsing + the engine).
  # The nix-only generated API clients are deliberately excluded — the diff layer
  # is client-free, and so are its tests.
  runtimeLibs =
    ps: with ps; [
      click
      pydantic
      pyyaml
      requests
      rich
    ];
in
{
  # A python313 carrying the runtime libs plus the given extra tool selector.
  pyWith = extra: python313.withPackages (ps: runtimeLibs ps ++ extra ps);

  # A check that runs `command` against a writable copy of the flake source and
  # succeeds when it exits 0. `src` is normally inputs.self.
  srcCheck =
    {
      name,
      src,
      nativeBuildInputs ? [ ],
      command,
    }:
    pkgs.runCommandLocal name { inherit nativeBuildInputs; } ''
      cp -r ${src} src
      chmod -R u+w src
      export HOME=$(mktemp -d)
      cd src
      ${command}
      touch $out
    '';
}

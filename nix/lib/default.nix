# Shared flake helpers. Blueprint imports this as `flake.lib` (system-independent),
# so the functions take `pkgs` explicitly — the per-system checks/devshell pass
# their own `pkgs` from blueprint's scope (`flake.lib.pyWith pkgs …`).
_:
let
  # Runtime libraries configarr imports (config parsing + the engine). The
  # nix-only generated API clients are deliberately excluded — configarr talks to
  # each HTTP API directly, so it and its tests are client-free.
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
  # A python313 (from the given pkgs) carrying the runtime libs plus extra tools.
  pyWith = pkgs: extra: pkgs.python313.withPackages (ps: runtimeLibs ps ++ extra ps);

  # A check that runs `command` against a writable copy of the flake source and
  # succeeds when it exits 0. `src` is normally inputs.self.
  srcCheck =
    pkgs:
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

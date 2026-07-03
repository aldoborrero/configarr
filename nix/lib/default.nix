# Shared flake helpers. Blueprint imports this as `flake.lib` (system-independent)
# with specialArgs, so it receives `inputs` and the functions take `pkgs` — the
# per-system checks/devshell/formatter pass their own `pkgs` from blueprint's scope.
{ inputs, ... }:
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

  # treefmt config, evaluated per-system via treefmt-nix. Exposes
  # `.config.build.wrapper` (the `nix fmt` formatter) and `.config.build.check`
  # (the CI check) — no need to hand-roll either.
  treefmtModule = {
    projectRootFile = "flake.nix";
    settings.on-unmatched = "info";
    programs = {
      nixfmt.enable = true;
      ruff-format.enable = true;
      ruff-check.enable = true;
      yamlfmt.enable = true;
      # Keep single blank lines so grouped config sections stay readable.
      yamlfmt.settings.formatter = {
        type = "basic";
        retain_line_breaks_single = true;
      };
    };
  };
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

  # treefmt-nix evaluation for the given pkgs (formatter + check both derive
  # from this single config).
  treefmtEval = pkgs: inputs.treefmt-nix.lib.evalModule pkgs treefmtModule;
}

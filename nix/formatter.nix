{ pkgs, ... }:
# treefmt with nixfmt (Nix), ruff (Python), and yamlfmt (YAML). Replaces
# blueprint's default nixfmt-tree formatter. Run with `nix fmt`.
pkgs.treefmt.withConfig {
  name = "configarr-treefmt";

  runtimeInputs = with pkgs; [
    nixfmt
    ruff
    yamlfmt
  ];

  settings = {
    # Quietly skip files no formatter matches instead of warning.
    on-unmatched = "info";

    formatter = {
      nixfmt = {
        command = "nixfmt";
        includes = [ "*.nix" ];
      };

      # Import sorting; runs before ruff-format on the same files.
      ruff-check = {
        command = "ruff";
        options = [
          "check"
          "--fix"
          "--select"
          "I"
        ];
        includes = [ "*.py" ];
        excludes = [ "nix/packages/**" ];
        priority = 1;
      };

      ruff-format = {
        command = "ruff";
        options = [ "format" ];
        includes = [ "*.py" ];
        excludes = [ "nix/packages/**" ];
        priority = 2;
      };

      yamlfmt = {
        command = "yamlfmt";
        # Keep single blank lines so grouped config sections stay readable.
        options = [
          "-formatter"
          "retain_line_breaks_single=true"
        ];
        includes = [
          "*.yml"
          "*.yaml"
        ];
      };
    };
  };
}

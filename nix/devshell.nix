{pkgs, ...}:
pkgs.mkShell {
  packages = with pkgs; [
    python313
    python313Packages.pip
    ruff
    mypy
  ];
}

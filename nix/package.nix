{
  pkgs,
  perSystem,
  ...
}:
with pkgs;

python313.pkgs.buildPythonApplication rec {
  pname = "configarr";
  version = "2.0.0";
  pyproject = true;

  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../pyproject.toml
      ../configarr
    ];
  };

  build-system = with python313.pkgs; [
    setuptools
  ];

  dependencies = with python313.pkgs; [
    click
    pydantic
    pyyaml
    requests
    rich
    perSystem.self.bazarr-py
    perSystem.self.prowlarr-py
    perSystem.self.radarr-py
    perSystem.self.sonarr-py
  ];

  meta = with lib; {
    description = "Configuration manager for Radarr, Sonarr, Prowlarr, and Bazarr";
    homepage = "https://github.com/aldoborrero/configarr";
    license = licenses.asl20;
    maintainers = [];
    mainProgram = "configarr";
    platforms = platforms.linux ++ platforms.darwin;
  };
}

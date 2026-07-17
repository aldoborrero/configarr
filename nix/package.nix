{
  pkgs,
  ...
}:
with pkgs;

python313.pkgs.buildPythonApplication rec {
  pname = "configarr";
  version = "0.2.0";
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

  # The diffing engine talks to each service's HTTP API directly via requests,
  # so the generated *-py API clients are no longer needed.
  dependencies = with python313.pkgs; [
    click
    pydantic
    pyyaml
    requests
    rich
  ];

  # The `trash: { source: git }` import shells out to `git` to clone/update a
  # Guides repo, so put it on the wrapped program's PATH.
  makeWrapperArgs = [
    "--prefix"
    "PATH"
    ":"
    (lib.makeBinPath [ git ])
  ];

  meta = with lib; {
    description = "Configuration manager for Radarr, Sonarr, Prowlarr, Bazarr, and SABnzbd";
    homepage = "https://github.com/aldoborrero/configarr";
    license = licenses.asl20;
    maintainers = [ ];
    mainProgram = "configarr";
    platforms = platforms.linux ++ platforms.darwin;
  };
}

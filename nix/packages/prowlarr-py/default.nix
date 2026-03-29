{
  pkgs,
  ...
}:
with pkgs;

python313.pkgs.buildPythonPackage rec {
  pname = "prowlarr-py";
  version = "1.1.0";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "devopsarr";
    repo = "prowlarr-py";
    tag = "v${version}";
    hash = "sha256-o3Lt9yJmICCyAcgeBXDPGzlCD/xzL85diZL0Q1SBa6U=";
  };

  build-system = with python313.pkgs; [
    setuptools
  ];

  dependencies = with python313.pkgs; [
    urllib3
    python-dateutil
    pydantic
    typing-extensions
  ];

  # Tests require network access
  doCheck = false;

  pythonImportsCheck = [ "prowlarr" ];

  meta = with lib; {
    description = "Python client for Prowlarr API";
    homepage = "https://github.com/devopsarr/prowlarr-py";
    license = licenses.mit;
    maintainers = [ ];
    platforms = platforms.all;
  };
}

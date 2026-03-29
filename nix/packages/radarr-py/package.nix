{
  pkgs,
  ...
}:
with pkgs;

python313.pkgs.buildPythonPackage rec {
  pname = "radarr-py";
  version = "1.2.0";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "devopsarr";
    repo = "radarr-py";
    tag = "v${version}";
    hash = "sha256-B+Drs28I/4i4KhYAaLkMWTLwukVIwpBquQDUc8Pn+F4=";
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

  pythonImportsCheck = [ "radarr" ];

  meta = with lib; {
    description = "Python client for Radarr API";
    homepage = "https://github.com/devopsarr/radarr-py";
    license = licenses.mit;
    maintainers = [ ];
    platforms = platforms.all;
  };
}

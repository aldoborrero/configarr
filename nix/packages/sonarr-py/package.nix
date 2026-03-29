{
  pkgs,
  ...
}:
with pkgs;

python313.pkgs.buildPythonPackage rec {
  pname = "sonarr-py";
  version = "1.1.0";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "devopsarr";
    repo = "sonarr-py";
    tag = "v${version}";
    hash = "sha256-iDyq8yE3NPE4iTKlqKVrtJmxaKPmGJYvqbnF4Jqomfg=";
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

  pythonImportsCheck = [ "sonarr" ];

  meta = with lib; {
    description = "Python client for Sonarr API";
    homepage = "https://github.com/devopsarr/sonarr-py";
    license = licenses.mit;
    maintainers = [ ];
    platforms = platforms.all;
  };
}

{
  pkgs,
  ...
}:
with pkgs;

python313.pkgs.buildPythonPackage rec {
  pname = "bazarr-py";
  version = "1.0.0";
  pyproject = true;

  src = ./.;

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

  pythonImportsCheck = [ "bazarr" ];

  meta = with lib; {
    description = "Python client for Bazarr API";
    homepage = "https://github.com/morpheus65535/bazarr";
    license = licenses.gpl3;
    maintainers = [ ];
    platforms = platforms.all;
  };
}

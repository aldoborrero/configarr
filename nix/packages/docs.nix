{ pkgs, ... }:
# The mdbook user guide. Built with mdbook + mdbook-mermaid (diagrams) and the
# mdbook-linkcheck2 backend, which validates internal links during the build (it
# is offline — follow-web-links is false in book.toml). The schema reference
# chapter {{#include}}s skills/configarr-config/references/schema.md, so that file
# is part of the source set even though it lives outside docs/.
let
  fs = pkgs.lib.fileset;
in
pkgs.stdenvNoCC.mkDerivation {
  pname = "configarr-docs";
  # Track the tool version, sourced from pyproject.toml (imported at eval time,
  # so it need not be part of the build src below).
  version = (pkgs.lib.importTOML ../../pyproject.toml).project.version;

  src = fs.toSource {
    root = ../..;
    fileset = fs.unions [
      ../../docs
      ../../skills/configarr-config/references/schema.md
    ];
  };

  nativeBuildInputs = with pkgs; [
    mdbook
    mdbook-mermaid
    mdbook-linkcheck2
    cacert
  ];

  # mdbook-linkcheck2 builds a reqwest client at startup even with
  # follow-web-links disabled, which needs a CA bundle or it panics in the
  # sandbox. It never actually makes web requests.
  SSL_CERT_FILE = "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt";

  buildPhase = ''
    runHook preBuild
    cd docs
    mdbook build
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    mkdir -p $out
    cp -r book/html/. $out/
    runHook postInstall
  '';

  meta = with pkgs.lib; {
    description = "configarr user guide (mdbook)";
    homepage = "https://github.com/aldoborrero/configarr";
    license = licenses.asl20;
    platforms = platforms.all;
  };
}

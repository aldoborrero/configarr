{
  pkgs,
  perSystem,
  ...
}:
let
  configarr = perSystem.self.default;
in
pkgs.dockerTools.buildLayeredImage {
  name = "configarr";
  tag = "latest";

  # cacert is needed so requests can verify TLS when an *arr instance is
  # reachable over HTTPS; configarr itself carries no certificate bundle.
  contents = [
    configarr
    pkgs.cacert
  ];

  config = {
    Entrypoint = [ (pkgs.lib.getExe configarr) ];
    # configarr defaults to ./configarr.yml, so mounting the config at
    # /config/configarr.yml works with no extra arguments.
    WorkingDir = "/config";
    Env = [
      "SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"
    ];
    Labels = {
      "org.opencontainers.image.source" = "https://github.com/aldoborrero/configarr";
      "org.opencontainers.image.description" =
        "Configuration manager for Radarr, Sonarr, Prowlarr, Bazarr, and SABnzbd";
      "org.opencontainers.image.licenses" = "Apache-2.0";
    };
  };
}

#!/usr/bin/env bash
# Regenerate bazarr-py from running Bazarr instance
# Usage: ./update.sh [bazarr_url]

set -euo pipefail

BAZARR_URL="${1:-https://bazarr.homik.xyz}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Fetching swagger.json from ${BAZARR_URL}..."
curl -s "${BAZARR_URL}/api/swagger.json" | jq . >"${SCRIPT_DIR}/swagger.json"

echo "Regenerating Python SDK..."
rm -rf "${SCRIPT_DIR}/bazarr"

nix run nixpkgs#openapi-generator-cli -- generate \
  -i "${SCRIPT_DIR}/swagger.json" \
  -g python \
  -o "${SCRIPT_DIR}" \
  --package-name bazarr \
  --additional-properties=packageName=bazarr,projectName=bazarr-py,packageVersion=1.0.0

# Clean up template boilerplate
rm -rf "${SCRIPT_DIR}"/{.github,.gitlab-ci.yml,.travis.yml,git_push.sh}
rm -rf "${SCRIPT_DIR}"/{.openapi-generator,.openapi-generator-ignore}
rm -rf "${SCRIPT_DIR}"/{docs,test,tox.ini,test-requirements.txt}
rm -rf "${SCRIPT_DIR}"/{setup.cfg,setup.py,requirements.txt,.gitignore,README.md}

echo "Done. Generated files:"
ls -la "${SCRIPT_DIR}"

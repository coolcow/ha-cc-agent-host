#!/bin/bash
# Lint shell scripts, the Dockerfile and YAML files with pinned container images.
set -euo pipefail
cd "$(dirname "$0")/.."

mapfile -t scripts < <(grep -rlE '^#!.*(bash|sh|bashio)' cc_agent_host tools tests)

echo "== shellcheck"
docker run --rm -v "$PWD:/mnt" -w /mnt koalaman/shellcheck:v0.10.0 -x -s bash "${scripts[@]}"

echo "== hadolint"
docker run --rm -i hadolint/hadolint:v2.12.0 hadolint --ignore DL3018 - < cc_agent_host/Dockerfile

echo "== yamllint"
docker run --rm -v "$PWD:/mnt" -w /mnt cytopia/yamllint:1.26 -c .yamllint .

echo "lint ok"

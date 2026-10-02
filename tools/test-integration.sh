#!/bin/bash
# Run the integration tests in a Python 3.14 container (Home Assistant needs >= 3.14).
set -euo pipefail
cd "$(dirname "$0")/.."
docker run --rm -v "$PWD:/src" -v cc-agent-host-pip:/root/.cache/pip -w /src python:3.14-slim sh -c '
    pip install -q --root-user-action=ignore -r tests/integration/requirements.txt >/dev/null &&
    python -m pytest -q -p no:cacheprovider -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function tests/integration "$@"' -- "$@"

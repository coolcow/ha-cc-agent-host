#!/bin/bash
# Integration tests (Home Assistant needs Python >= 3.14; runs in a container if needed).
# Usage: tools/test-integration.sh [pytest args...]   Kept for muscle memory.
exec "$(dirname "$0")/../scripts/agent/test" integration "$@"

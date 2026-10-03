#!/bin/bash
# Lint shell scripts, the Dockerfile, YAML, workflows and Python (pinned tools). Kept for muscle memory.
exec "$(dirname "$0")/../scripts/agent/check" lint

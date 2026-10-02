#!/bin/bash
# Pin a Claude Code version in the Dockerfile with verified sha512 checksums from npm.
# Usage: tools/bump-claude-code.sh [version]   (default: latest)
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
dockerfile="$root/cc_agent_host/Dockerfile"
version="${1:-$(curl -fsSL https://registry.npmjs.org/@anthropic-ai/claude-code/latest | jq -r .version)}"

sha512_hex() {
    local integrity
    integrity="$(curl -fsSL "https://registry.npmjs.org/@anthropic-ai/claude-code-$1/$version" | jq -r .dist.integrity)"
    [[ "$integrity" == sha512-* ]] || { echo "no sha512 for $1 $version" >&2; exit 1; }
    echo "${integrity#sha512-}" | base64 -d | od -An -tx1 | tr -d ' \n'
}

arm64="$(sha512_hex linux-arm64-musl)"
x64="$(sha512_hex linux-x64-musl)"

sed -i \
    -e "s/^ARG CLAUDE_CODE_VERSION=.*/ARG CLAUDE_CODE_VERSION=$version/" \
    -e "s/^ARG SHA512_ARM64=.*/ARG SHA512_ARM64=$arm64/" \
    -e "s/^ARG SHA512_X64=.*/ARG SHA512_X64=$x64/" \
    "$dockerfile"

echo "Claude Code pinned to $version"

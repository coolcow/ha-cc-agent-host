#!/bin/bash
# Pin a Claude Code version in the Dockerfile with verified sha512 checksums from npm.
# If the version changes, the add-on patch version is raised and a CHANGELOG entry is added
# (docs/DEVELOPMENT.md: Claude Code version bumps raise the patch version).
# Usage: tools/bump-claude-code.sh [version]   (default: latest)
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
dockerfile="$root/cc_agent_host/Dockerfile"
config="$root/cc_agent_host/config.yaml"
changelog="$root/cc_agent_host/CHANGELOG.md"
version="${1:-$(curl -fsSL https://registry.npmjs.org/@anthropic-ai/claude-code/latest | jq -r .version)}"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "invalid version: $version" >&2; exit 1; }
current="$(grep -oP '^ARG CLAUDE_CODE_VERSION=\K.*' "$dockerfile")"

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

if [[ "$version" != "$current" ]]; then
    addon="$(grep -oP '^version: "\K[0-9]+\.[0-9]+\.[0-9]+(?=")' "$config")"
    new="${addon%.*}.$(( ${addon##*.} + 1 ))"
    sed -i "s/^version: \"$addon\"/version: \"$new\"/" "$config"
    sed -i "0,/^## /s//## $new\n\n- Claude Code $version\n\n## /" "$changelog"
    echo "add-on version $addon -> $new"
fi

echo "Claude Code pinned to $version"

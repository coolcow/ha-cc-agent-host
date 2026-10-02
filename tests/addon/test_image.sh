#!/bin/bash
# shellcheck disable=SC2016  # expressions are expanded inside the container
# Static checks against the built app image (no Home Assistant needed).
# Usage: tests/addon/test_image.sh [image]   (default: builds cc-agent-host:test)
set -euo pipefail
cd "$(dirname "$0")/../.."

image="${1:-}"
if [ -z "$image" ]; then
    image=cc-agent-host:test
    docker build -q -t "$image" cc_agent_host >/dev/null
fi

fail=0
check() {  # check <description> <command...>
    local desc="$1"; shift
    if docker run --rm --entrypoint /bin/bash "$image" -c "$*" >/dev/null 2>&1; then
        echo "ok   $desc"
    else
        echo "FAIL $desc"; fail=1
    fi
}

version="$(grep -oP '^ARG CLAUDE_CODE_VERSION=\K.*' cc_agent_host/Dockerfile)"
check "Claude Code $version runs" "claude --version | grep -q '^$version'"
check "claude binary root-owned, not writable by others" \
    "[ \"\$(stat -c %U:%a /usr/local/bin/claude)\" = root:755 ]"
check "auto-updater disabled" '[ "$DISABLE_AUTOUPDATER" = 1 ]'
check "login stored in /data" '[ "$CLAUDE_CONFIG_DIR" = /data/claude ] && [ "$HOME" = /data/home ]'
check "nginx config valid" "mkdir -p /run/ttyd && nginx -t -c /etc/nginx/nginx.conf"
check "nginx admits only the ingress gateway" \
    "grep -q 'allow 172.30.32.2;' /etc/nginx/nginx.conf && grep -q 'deny all;' /etc/nginx/nginx.conf"
check "ttyd listens on a unix socket only" "grep -q -- '--interface /run/ttyd/ttyd.sock' /etc/s6-overlay/s6-rc.d/ttyd/run"
check "tools present" "command -v ttyd tmux git jq bashio"
check "s6 services registered" \
    "for s in init-cc session ttyd nginx; do [ -e /etc/s6-overlay/s6-rc.d/user/contents.d/\$s ] || exit 1; done"
check "scripts executable" \
    "[ -x /usr/local/bin/cc-session ] && for f in /etc/s6-overlay/s6-rc.d/*/run; do [ -x \$f ] || exit 1; done"

exposed="$(docker image inspect -f '{{json .Config.ExposedPorts}}' "$image")"
if [ "$exposed" = "null" ] || [ "$exposed" = "{}" ]; then echo "ok   no exposed ports"; else echo "FAIL exposed ports: $exposed"; fail=1; fi
if ! grep -q '^ports:' cc_agent_host/config.yaml; then echo "ok   no ports in config.yaml"; else echo "FAIL ports in config.yaml"; fail=1; fi

exit "$fail"

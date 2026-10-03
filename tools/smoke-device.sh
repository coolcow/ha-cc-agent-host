#!/bin/bash
# Read-only smoke test of the installed add-on and integration on a Home Assistant OS device, over SSH
# (Terminal & SSH app: `ha` CLI, curl, jq, SUPERVISOR_TOKEN). Changes nothing on the device.
# Compares with the versions in this checkout. Output: ok / FAIL / skip / info per check; exit 1 on FAIL.
# Usage: tools/smoke-device.sh <ha-host>          SSH via DEPLOY_SSH (default: ssh)
set -euo pipefail
cd "$(dirname "$0")/.."
host="${1:?usage: tools/smoke-device.sh <ha-host>}"
read -r -a ssh_cmd <<<"${DEPLOY_SSH:-ssh}"
addon=$(sed -nE 's/^version: "([0-9.]+)".*/\1/p' cc_agent_host/config.yaml)
integration=$(sed -nE 's/.*"version": "([0-9.]+)".*/\1/p' custom_components/cc_agent_host/manifest.json)

# The remote part only reads: ha apps info/logs, a manifest file, GET requests. Tokens are never printed.
remote_script=$(cat <<'REMOTE'
set -u
want_addon="$1" want_integration="$2" config="${SMOKE_HA_CONFIG:-/homeassistant}"
ok() { echo "ok   $*"; }
fail() { echo "FAIL $*"; }
skip() { echo "skip $*"; }
info() { echo "info $*"; }
sv() { curl -fsS -m 10 -H "Authorization: Bearer ${SUPERVISOR_TOKEN:-}" "http://supervisor$1"; }

info=$(ha apps info local_cc_agent_host --raw-json 2>/dev/null)
version=$(printf '%s' "$info" | jq -r '.data.version // empty' 2>/dev/null)
state=$(printf '%s' "$info" | jq -r '.data.state // empty' 2>/dev/null)
if [ -z "$version" ]; then fail "add-on local_cc_agent_host not installed"
else
    [ "$version" = "$want_addon" ] && ok "add-on version $version" || fail "add-on version $version, checkout has $want_addon"
    [ "$state" = started ] && ok "add-on state started" || fail "add-on state ${state:-unknown}"
    n=$(ha apps logs local_cc_agent_host 2>/dev/null | tail -n 300 | grep -ciE 'traceback|error' || true)
    info "add-on log: $n error/traceback lines in the last 300"
fi

m="$config/custom_components/cc_agent_host/manifest.json"
if [ -f "$m" ]; then
    v=$(jq -r '.version // empty' "$m")
    [ "$v" = "$want_integration" ] && ok "integration version $v" || fail "integration version ${v:-?}, checkout has $want_integration"
else skip "integration not installed as custom component ($m)"; fi

if [ -z "${SUPERVISOR_TOKEN:-}" ]; then skip "job API / sensors: no SUPERVISOR_TOKEN in this SSH session"; exit 0; fi
disc=$(sv /discovery 2>/dev/null | jq -c '[.data.discovery[]? | select(.service == "cc_agent_host")][0].config // empty' 2>/dev/null)
if [ -z "$disc" ]; then skip "job API: no cc_agent_host discovery entry readable (Supervisor role of the SSH app?)"
else
    h=$(printf '%s' "$disc" | jq -r .host) p=$(printf '%s' "$disc" | jq -r .port) k=$(printf '%s' "$disc" | jq -r .api_key)
    st=$(curl -fsS -m 10 -H "Authorization: Bearer $k" "http://$h:$p/status" 2>/dev/null)
    if [ -z "$st" ]; then fail "job API http://$h:$p/status not reachable"
    else
        v=$(printf '%s' "$st" | jq -r .version)
        [ "$v" = "$want_addon" ] && ok "job API /status, version $v" || fail "job API reports version $v, checkout has $want_addon"
        info "job API: signed_in=$(printf '%s' "$st" | jq -r .signed_in) job_token=$(printf '%s' "$st" | jq -r .job_token) profiles=$(printf '%s' "$st" | jq -r '.profiles | join(",")')"
    fi
fi
states=$(sv /core/api/states 2>/dev/null)
if [ -z "$states" ]; then skip "sensors: Home Assistant API not readable from this SSH session"
else
    total=$(printf '%s' "$states" | jq '[.[] | select(.entity_id | test("cc_agent_host"))] | length')
    bad=$(printf '%s' "$states" | jq -r '[.[] | select((.entity_id | test("cc_agent_host")) and .state == "unavailable") | .entity_id] | join(" ")')
    [ "$total" -gt 0 ] && ok "sensors: $total cc_agent_host entities" || fail "sensors: no cc_agent_host entities (integration set up?)"
    [ -z "$bad" ] && ok "sensors: none unavailable" || fail "sensors unavailable: $bad"
fi
exit 0
REMOTE
)

echo "smoke test $host (checkout: add-on $addon, integration $integration)"
out=$("${ssh_cmd[@]}" "$host" bash -s -- "$addon" "$integration" <<<"$remote_script") || { echo "✗ ssh to $host failed" >&2; exit 2; }
printf '%s\n' "$out"
if grep -q '^FAIL' <<<"$out"; then echo "✗ smoke test failed"; exit 1; fi
echo "✓ smoke test passed"

#!/bin/bash
# Install the committed add-on and/or integration on a Home Assistant OS device over SSH
# (the "Advanced SSH & Web Terminal" / "Terminal & SSH" app). Guarded: clean git tree, full
# `scripts/agent/check`, version newer than the installed one. Never restarts Home Assistant.
#
# Usage: tools/deploy.sh <ha-host> [addon|integration|all] [--dry-run] [--redeploy]
#   addon        copy cc_agent_host/ to /local_apps, store reload, install or update   (default: all)
#   integration  copy custom_components/cc_agent_host/ to /homeassistant/custom_components
#   --dry-run    run all guards and print the remote commands, change nothing on the device
#   --redeploy   allow the installed version (rebuild); never allows an older version
# Only on the owner's explicit instruction (CLAUDE.md). SSH is configurable via DEPLOY_SSH (default: ssh).
set -euo pipefail
cd "$(dirname "$0")/.."

usage() { sed -n '5,10p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 64; }
host="" what=all dry=0 redeploy=0
for a in "$@"; do
    case "$a" in
        addon|integration|all) what="$a" ;;
        --dry-run) dry=1 ;;
        --redeploy) redeploy=1 ;;
        -h|--help|-*) usage ;;
        *) if [[ -z $host ]]; then host="$a"; else usage; fi ;;
    esac
done
[[ -n $host ]] || usage
read -r -a ssh_cmd <<<"${DEPLOY_SSH:-ssh}"
remote() { "${ssh_cmd[@]}" "$host" "$@"; }

slug=local_cc_agent_host
addon_dir=/local_apps/cc_agent_host
integration_dir=/homeassistant/custom_components/cc_agent_host
want_addon=0 want_integration=0
[[ $what == addon || $what == all ]] && want_addon=1
[[ $what == integration || $what == all ]] && want_integration=1

# 1. Clean tree: what is deployed is exactly a commit (git archive below)
if [[ -n $(git status --porcelain) ]]; then
    echo "✗ working tree not clean – commit or stash first:" >&2; git status --short >&2; exit 1
fi
commit=$(git rev-parse --short HEAD)

# 2. Full check
echo "== scripts/agent/check"
scripts/agent/check || { echo "✗ check failed – not deploying" >&2; exit 1; }

# 3. Versions: local must be newer than installed (equal only with --redeploy)
version_gt() { [[ $1 != "$2" && $(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -1) == "$1" ]]; }
check_version() {  # check_version <name> <local> <installed>
    if [[ -z $3 ]]; then echo "  $1: not installed → $2"; return 0; fi
    if version_gt "$2" "$3"; then echo "  $1: $3 → $2"; return 0; fi
    if [[ $2 == "$3" && $redeploy == 1 ]]; then echo "  $1: $3 (redeploy)"; return 0; fi
    echo "✗ $1: local version $2 is not newer than installed $3 – raise the version (or --redeploy for the same version)" >&2
    return 1
}
echo "== versions ($host, commit $commit)"
local_addon=$(sed -nE 's/^version: "([0-9.]+)".*/\1/p' cc_agent_host/config.yaml)
local_integration=$(sed -nE 's/.*"version": "([0-9.]+)".*/\1/p' custom_components/cc_agent_host/manifest.json)
installed_addon="" installed_integration=""
if (( want_addon )); then
    installed_addon=$(remote "ha apps info $slug --raw-json 2>/dev/null | jq -r '.data.version // empty'" || true)
    check_version add-on "$local_addon" "$installed_addon"
fi
if (( want_integration )); then
    installed_integration=$(remote "jq -r '.version // empty' $integration_dir/manifest.json 2>/dev/null" || true)
    check_version integration "$local_integration" "$installed_integration"
fi

# 4. Remote commands (staged extract, then swap: removed files do not linger on the device)
stage=/tmp/cc_agent_host.deploy
replace() {  # replace <target dir>: stdin is a tar of one directory "payload/"
    echo "set -e; rm -rf $stage; mkdir -p $stage; tar -xf - -C $stage; rm -rf $1; mv $stage/payload $1; rm -rf $stage"
}
archive() { git -c tar.umask=0022 archive --format=tar --prefix=payload/ "HEAD:$1"; }  # committed files only, owner root
if [[ -z $installed_addon ]]; then addon_action=install
elif [[ $installed_addon == "$local_addon" ]]; then addon_action=rebuild
else addon_action=update; fi
addon_cmd="ha store reload && ha apps $addon_action $slug"

if (( dry )); then
    echo "== dry run, nothing changed on $host. Would run:"
    if (( want_addon )); then
        printf "  git archive HEAD:cc_agent_host | %s %s '%s'\n" "${ssh_cmd[*]}" "$host" "$(replace "$addon_dir")"
        printf "  %s %s '%s'\n" "${ssh_cmd[*]}" "$host" "$addon_cmd"
    fi
    if (( want_integration )); then
        printf "  git archive HEAD:custom_components/cc_agent_host | %s %s '%s'\n" "${ssh_cmd[*]}" "$host" \
            "$(replace "$integration_dir")"
    fi
    exit 0
fi

if (( want_addon )); then
    echo "== add-on $local_addon → $addon_dir ($addon_action)"
    archive cc_agent_host | remote "$(replace "$addon_dir")"
    remote "$addon_cmd"
fi
if (( want_integration )); then
    echo "== integration $local_integration → $integration_dir"
    archive custom_components/cc_agent_host | remote "$(replace "$integration_dir")"
    echo "ℹ Home Assistant must be restarted to load the integration. Not done automatically – only on the"
    echo "  owner's explicit instruction: ${ssh_cmd[*]} $host 'ha core restart'"
fi

# 5. Read-only smoke test
echo "== smoke test"
DEPLOY_SSH="${DEPLOY_SSH:-ssh}" tools/smoke-device.sh "$host"

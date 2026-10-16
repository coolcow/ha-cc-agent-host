#!/bin/bash
# Security test in a running container: a job (fake claude, run by the real job API as cc_agent)
# tries to read every secret, write the HA configuration and reach root-only sockets.
# Usage: tests/addon/test_isolation.sh [image]
set -euo pipefail
cd "$(dirname "$0")/../.."
image="${1:-cc-agent-host:test}"

cid="$(docker run -d -e SUPERVISOR_TOKEN=supervisor-secret "$image")"
trap 'docker rm -f "$cid" >/dev/null' EXIT
for _ in $(seq 60); do
    docker exec "$cid" sh -c '[ -S /run/ttyd/ttyd.sock ] && [ -s /data/api_token ]' 2>/dev/null && break
    sleep 0.5
done

# Secrets a job must not reach (stand-ins for the real ones)
docker exec "$cid" sh -e -c '
    mkdir -p /srv/ha/config/.storage /data/claude
    echo "pw: geheim" > /srv/ha/config/secrets.yaml
    echo "{}" > /srv/ha/config/.storage/core.config_entries
    echo "{\"creds\":1}" > /data/claude/.credentials.json
    echo "{}" > /data/options.json && chmod 600 /data/options.json
    printf sk-ant-oat-test > /data/job_token && chmod 600 /data/job_token
    cat > /tmp/fake-claude <<"SH"
#!/bin/sh
cat >/dev/null
r=""
for f in /run/s6/container_environment/SUPERVISOR_TOKEN /data/api_token /data/job_token /data/options.json \
         /data/claude/.credentials.json /srv/ha/config/secrets.yaml /srv/ha/config/.storage/core.config_entries \
         /homeassistant/secrets.yaml /data/audit.log; do
    cat "$f" >/dev/null 2>&1 && r="$r read:$f"
done
ls /srv/ha >/dev/null 2>&1 && r="$r list:/srv/ha"
touch /srv/ha/config/x 2>/dev/null && r="$r write:config"
touch /usr/local/bin/x 2>/dev/null && r="$r write:bin"
tmux -S /tmp/tmux-0/default ls >/dev/null 2>&1 && r="$r tmux"
cat /proc/1/environ >/dev/null 2>&1 && r="$r proc-environ"
env | grep -q SUPERVISOR && r="$r env:supervisor"
cc-ha states 2>&1 | grep -q "no Supervisor token" || r="$r cc-ha:token"
printf "{\"result\":\"user=%s%s\",\"is_error\":false,\"num_turns\":1}" "$(id -un)" "$r"
SH
    chmod 755 /tmp/fake-claude
    printf "tools: [Read]\n" > /srv/ha/addon_config/profiles/probe.yaml
'
# Second API instance with the fake claude (same code, same job user)
docker exec -d "$cid" sh -c 'cd / && CC_CLAUDE=/tmp/fake-claude CC_PORT=8101 python3 /usr/lib/cc_agent_host/server.py'
sleep 2

fail=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got '$2', want '$3'"; fail=1; fi; }

token="$(docker exec "$cid" cat /data/api_token)"
res="$(docker exec "$cid" curl -s -H "Authorization: Bearer $token" -d '{"profile":"probe","prompt":"x"}' \
    http://127.0.0.1:8101/run | jq -r .result)"
check "job runs as cc_agent and reaches no secret, socket or write target" "$res" "user=cc_agent"

control="$(docker exec "$cid" sh -c 'echo | /tmp/fake-claude' | jq -r .result)"
case "$control" in
    *read:/run/s6/container_environment/SUPERVISOR_TOKEN*read:/data/api_token*write:config*)
        echo "ok   control: the same probe run as root finds the secrets" ;;
    *) echo "FAIL control probe as root: $control"; fail=1 ;;
esac

check "API without token" "$(docker exec "$cid" curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8100/status)" 401
check "API token file private" "$(docker exec "$cid" stat -c %U:%a /data/api_token)" root:600
check "container environment root-only" "$(docker exec "$cid" stat -c %a /run/s6/container_environment)" 700
check "/srv/ha root-only" "$(docker exec "$cid" stat -c %a /srv/ha)" 700
check "agent home owned by cc_agent" "$(docker exec "$cid" stat -c %U:%a /data/agent)" cc_agent:700
check "audit entry written" "$(docker exec "$cid" sh -c 'tail -1 /data/audit.log | jq -r .user')" cc_agent

exit "$fail"

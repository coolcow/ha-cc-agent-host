#!/usr/bin/with-contenv bashio
# Directories, permissions and defaults. Everything the job user cc_agent must not see is
# root-only: HA configuration mount, container environment (SUPERVISOR_TOKEN), add-on data.
set -e
mkdir -p /data

chmod 700 /run/s6/container_environment /srv/ha
chmod 711 /data
chmod 600 /data/options.json 2>/dev/null || true

mkdir -p "$HOME" "$CLAUDE_CONFIG_DIR"
chmod 700 "$HOME" "$CLAUDE_CONFIG_DIR"

# Job user: own home and Claude Code config, nothing else
mkdir -p /data/agent/home /data/agent/claude
chown -R cc_agent:cc_agent /data/agent
chmod 700 /data/agent

mkdir -p /run/ttyd /run/cc
chown root:nginx /run/ttyd
chmod 750 /run/ttyd
chmod 755 /run/cc

# Default profiles (existing files are never overwritten)
mkdir -p /srv/ha/addon_config/profiles
for f in /usr/share/cc_agent_host/profiles/*.yaml; do
    [ -e "/srv/ha/addon_config/profiles/$(basename "$f")" ] || cp "$f" /srv/ha/addon_config/profiles/
done

# Claude Code installed through the update entity: drop it once the image brings the same or a newer version
if [ -L /data/cli/current ]; then
    installed="$(readlink /data/cli/current)"
    image="$(/usr/lib/cc_agent_host/claude --version 2>/dev/null | cut -d' ' -f1)"
    if [ ! -x /data/cli/current/claude ] || python3 -c 'import sys; v = [tuple(map(int, a.split("."))) for a in sys.argv[1:]]; sys.exit(v[1] < v[0])' "$installed" "$image" 2>/dev/null; then
        bashio::log.info "Claude Code ${image} of the image replaces the installed update ${installed}"
        rm -rf /data/cli
    fi
fi
bashio::log.info "Claude Code $(claude --version 2>/dev/null)"
if [ -s "$CLAUDE_CONFIG_DIR/.credentials.json" ]; then
    bashio::log.info "Signed in"
else
    bashio::log.warning "Not signed in: open the web terminal and type /login"
fi
if [ -s /data/job_token ]; then
    bashio::log.info "Job token present"
else
    bashio::log.info "No job token: jobs are disabled until you run 'claude setup-token' and 'cc-job-token'"
fi

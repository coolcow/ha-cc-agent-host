#!/usr/bin/with-contenv bashio
# Persistent home and Claude Code configuration (login) in /data
mkdir -p "$HOME" "$CLAUDE_CONFIG_DIR" /run/ttyd
chmod 700 "$HOME" "$CLAUDE_CONFIG_DIR"
chown root:nginx /run/ttyd
chmod 750 /run/ttyd
bashio::log.info "Claude Code $(claude --version 2>/dev/null)"
if [ -s "$CLAUDE_CONFIG_DIR/.credentials.json" ]; then
    bashio::log.info "Signed in"
else
    bashio::log.warning "Not signed in: open the web terminal and type /login"
fi

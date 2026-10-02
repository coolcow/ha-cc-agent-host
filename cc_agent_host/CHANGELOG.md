# Changelog

## 0.4.0

- `/status` reports the plan of the sign-in (`plan`, `subscription`, `tier`, `multiplier` relative to Pro).
  The subscription type comes from `claude auth status`; Max 5x vs. Max 20x needs the opt-in `usage_api`.

## 0.3.0

- Opt-in option `usage_api`: full plan usage incl. usage credits and weekly breakdown from the usage
  API (5-minute cache, stale values kept on errors, token refresh left to Claude Code). Explained in
  the option description and in the documentation.

## 0.2.1

- Context provider `ha_system_log` (deduplicated errors/warnings via the HA websocket API); `log-digest`
  uses it. `ha_log` (raw core log) needs the Supervisor role `homeassistant`, which is not granted.

## 0.2.0

- Job API (`/run`, `/status`, `/profiles`, `/usage`) with profiles, announced to Home Assistant
- Jobs run as unprivileged user `cc_agent`; HA configuration, add-on data and Supervisor token are
  not reachable for it
- Context providers: Home Assistant log, states, filtered configuration copy
- Separate long-lived job token (`claude setup-token` + `cc-job-token`)
- Status line in the interactive session, plan usage for `/usage`

## 0.1.1

- Fix: nginx could not open the terminal socket (502 via ingress)

## 0.1.0

- Web terminal via ingress with a persistent tmux session
- Claude Code 2.1.287 (official musl build, checksum-verified)
- Optional Remote Control

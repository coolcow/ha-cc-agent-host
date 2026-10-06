# Changelog

## 0.7.0

- Claude Code updates without an add-on release: the job API reports the latest Claude Code version
  (npm, checked every 6 hours) in `/status` and installs a version on request (`POST /cli/update`),
  downloaded from npm, sha512-verified and kept in `/data/cli`. The companion integration (0.4.0) shows
  it as an update entity; nothing is installed automatically. Remote Control restarts with the new
  version. An add-on release with the same or a newer Claude Code version replaces the installed update.

## 0.6.1

- Claude Code 2.1.291 (2.1.287 could not store a permanent folder approval for cloud sessions; only
  "allow once" worked).

## 0.6.0

- Remote Control runs in server mode (`claude remote-control`) as its own service instead of being
  attached to the web terminal session. The add-on no longer shows a permanently open, mostly empty
  session in claude.ai/code and the Claude app; a session in `/homeassistant` starts only when you open
  one there (permission mode `default`, spawn mode `same-dir`: sessions work directly in the
  configuration, also when it is a git repository) and is archived when the add-on stops. The service starts by
  itself after the sign-in, no restart needed. The web terminal session is local only now.
- The server runs in the tmux session `rc`, so its one-time questions (Remote Control consent, workspace
  trust) can be answered in the web terminal; the add-on log points to a waiting question.
- Web terminal: tappable tabs **Terminal** and **Remote Control** in the status bar (no Ctrl key needed,
  e.g. on phones).

## 0.5.0

- Context provider `ha_history`: recorder history of selected entities as compact per-area timelines
  (numbers as min–max per time bucket, brief `unavailable`/`unknown` shorter than `min_duration_s` dropped, area names via the
  template API). Selection by domain, sensor device class and include/exclude globs.
- Fix: Home Assistant API responses were cut at 4 MB (the context limit), which broke `ha_states` on
  larger installations; reads now allow up to 64 MB, the context limit still applies to the files.

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

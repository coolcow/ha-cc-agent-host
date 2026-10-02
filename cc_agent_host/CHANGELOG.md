# Changelog

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

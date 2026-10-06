# Changelog

Integration `cc_agent_host` (the add-on has its own changelog in `cc_agent_host/CHANGELOG.md`).

## 0.4.0

- Update entity **CLI** (Claude Code): shows when a newer Claude Code version is available and installs it in
  the add-on on request (add-on 0.7.0 or newer; nothing is installed automatically)

## 0.3.1

- Manifest: documentation and issue tracker point to github.com/coolcow/ha-cc-agent-host, code owner
  `@coolcow` (metadata only, no behavior change)

## 0.3.0

- Plan sensor (subscription, tier and multiplier relative to Pro, from the add-on's `/status`)

## 0.2.0

- Usage credit sensors (used, remaining, limit, reset) and usage source (diagnostic), filled when the
  add-on's opt-in `usage_api` is enabled

## 0.1.0

- Setup through add-on discovery (or manually: host, port, API key), reauthentication
- Action `cc_agent_host.run` (profile, prompt, timeout) with response data
- Sensors: signed in, job token, job running, plan usage 5-hour/weekly window and resets

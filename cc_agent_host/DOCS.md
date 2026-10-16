# CC Agent Host

Runs the official, unmodified Claude Code CLI inside Home Assistant with your own
Claude subscription: a web terminal, optional Remote Control and jobs from automations.

Claude Code works directly in your Home Assistant configuration: it sees the real files and logs, so
you no longer copy YAML into a chat window or sync your configuration to another computer. You watch
and approve every change. *Deutsch: [DOCS.de.md](DOCS.de.md)*

Not affiliated with or endorsed by Anthropic. Claude and Claude Code are trademarks
of Anthropic, PBC.

## Requirements

- Home Assistant OS or Supervised, 64-bit (aarch64 or amd64): e.g. Home Assistant Green/Yellow,
  Raspberry Pi 4/5 with 64-bit HAOS, x86-64 mini PCs and VMs. There is no 32-bit build of Claude Code.
- 2 GB RAM or more (a running Claude Code process needs about 300-500 MB).
- A Claude subscription (Pro or Max).
- Nothing to change in Home Assistant itself: no configuration edits, no extra integrations required.

## First start

1. Open **CC Agent Host** in the sidebar.
2. Type `/login` in Claude Code and complete the sign-in in your browser.
3. Optional: enable **Remote Control** in the configuration and restart the add-on.

The web terminal session keeps running when you close the browser. Exiting Claude Code
drops you into a shell; `exit` starts Claude Code again.

## Remote Control

With **Remote Control** enabled, the add-on runs `claude remote-control` in server mode in
`/homeassistant`. It appears as an environment in claude.ai/code and the Claude app, but no session
stays open: a new session starts only when you open one there, directly in the configuration (spawn
mode `same-dir`, no worktrees) and in permission mode `default` (Claude asks before each change). Sessions end when the add-on stops. The service waits for your sign-in and
starts by itself. The web terminal session itself is not reachable remotely.

The server runs in its own tmux session `rc`. The first time, Claude Code asks
`Enable Remote Control? (y/n)` (and, if the folder is not trusted yet, whether to trust
`/homeassistant`); the add-on log then says so. Only you answer these questions: open the web terminal,
tap **Remote Control** at the bottom right of the status bar, answer, and tap **Terminal** to return
(works on phones too; on a keyboard, `Ctrl-b s` switches as well).

## Companion integration

Jobs and sensors need the companion integration (install through HACS as a custom repository with the
URL of this add-on repository, type *Integration*, then restart Home Assistant). The add-on announces
itself, so the integration appears under Settings → Devices & services, ready to confirm; no address
or key to type in. It adds:

- the action **`cc_agent_host.run`** (`profile`, `prompt`, optional `timeout` in seconds), which returns
  `ok`, `result` and `error` to your automation (`response_variable`);
- binary sensors **Signed in**, **Job token** and **Job running**;
- sensors for plan usage (5-hour and weekly window in %, reset times, usage credit with the usage API
  option, usage source, plan);
- the update entity **CLI** for Claude Code updates (see below).

## Jobs

Jobs run Claude Code unattended (`claude -p`) with a **profile** and return the result.
They use a separate long-lived token, so they never touch your interactive login:

1. In the terminal, exit Claude Code (`/exit`), then run `claude setup-token` and complete the sign-in.
2. Run `cc-job-token` and paste the printed token (input is hidden).
3. Type `exit` to return to Claude Code.

Profiles are YAML files in the add-on configuration folder (`profiles/`). Missing default profiles are
added on start; existing files are never overwritten. Defaults:

| Profile | Tools | Context files |
|---|---|---|
| `read` | Read, Grep, Glob | none |
| `read-config` | Read, Grep, Glob | filtered copy of the HA configuration |
| `log-digest` | Read, Grep, Glob | Home Assistant system log (errors, warnings) |

Profile keys: `description`, `model` (default `sonnet`), `max_turns`, `timeout` (seconds, max 1800),
`max_budget_usd`, `tools` (built-in Claude Code tools), `context` (`ha_system_log`, `ha_states`, `ha_history`, `ha_config`; `ha_log` needs the Supervisor role `homeassistant`),
`system_prompt`.

Context `ha_history` writes the recorder history as compact timelines, one file per area
(`ha_history/<area>.txt`, overview in `ha_history/INDEX.md`, local time). Options: `hours` (default 24,
max 240), `bucket_minutes` (numbers as min–max per bucket, default 10), `min_duration_s` (drop
`unavailable`/`unknown` shorter than this), `domains`, `sensor_device_classes`,
`skip_binary_device_classes`, `include` / `exclude` (entity id globs), `steps` (rounding per unit, e.g.
`{"°C": 0.5}`; other units: two significant digits).

### How jobs are isolated

- Jobs run as the unprivileged user `cc_agent` in a temporary directory with only their context files.
- The Home Assistant configuration, the add-on data (login, tokens, options) and the Supervisor token are
  not accessible to that user at all; context files are prepared by the add-on.
- Only the tools listed in the profile are available; everything else is denied without prompting.
- One job at a time, time limit per profile, output capped, every job logged (without the prompt text)
  in the add-on data (`audit.log`).

### API

Reachable only from the internal Home Assistant network, with a bearer token that the add-on announces
to the companion integration. `GET /status`, `GET /profiles`, `GET /usage`,
`POST /run {"profile": "...", "prompt": "...", "timeout": 300}`, `POST /cli/update {"version": "..."}`.

`/usage` returns the plan usage, see the next section.

## Plan usage

Two sources, chosen with the option **Full plan usage via usage API**:

| | Status line (default) | Usage API (opt-in) |
|---|---|---|
| Data | 5-hour and weekly usage, reset times | same, plus usage credits and the weekly breakdown (Claude Code, chat, …) |
| Freshness | only while the web terminal session is used | every 5 minutes, also when idle |
| Credentials | never touched | the add-on reads the access token of your interactive sign-in |
| Stability | official Claude Code feature | undocumented endpoint, may change or disappear |

**Plan detection.** `/status` reports the plan of your sign-in (`pro`, `max_5x`, `max_20x`, …) and its
usage multiplier relative to Pro (1, 5, 20). The subscription type comes from `claude auth status`; only the
usage API option can tell Max 5x from Max 20x (otherwise the plan is reported as `max`).

**Why the usage API is off by default.** To query it, add-on code has to read the access token of your
Claude sign-in. Anthropic's terms say third-party software must not collect, store or intermediate
Claude.ai credentials, and the endpoint itself is not a documented public API. The add-on keeps the
risk small (the token stays inside the add-on, is only sent to `api.anthropic.com`, and refreshing is
left to Claude Code itself), but whether that is acceptable is your decision, so it is opt-in.

## Claude Code updates

The add-on brings a pinned, checksum-verified Claude Code version. Newer versions do not need a new
add-on release: the add-on checks npm every 6 hours for the latest Claude Code version, and the
companion integration offers it as an update (entity **CLI** of the CC Agent Host device, under
Settings → Updates). Nothing is installed automatically: **Install** downloads the official package for your architecture, verifies the
registry's sha512 checksum and the reported version, and keeps it in the add-on data (`/data/cli`, the
new and the previous version). Remote Control restarts with the new version (open cloud sessions are
disconnected); the web terminal session uses it after its next start (`/exit`, then `exit`). An add-on
release with the same or a newer Claude Code version replaces the installed update.

## Long links

Long links (for example the sign-in link) wrap over several lines, and only the first line
is clickable. Hold **Shift** and select the whole link with the mouse: the selection is copied
automatically. Paste it into a new browser tab; the line breaks are removed on paste.

## Data

- Login and Claude Code settings: add-on data, included in backups.
- Claude Code installed through the update entity: add-on data (`/data/cli`).
- Working directory of the terminal: your Home Assistant configuration (`/homeassistant`).

## Security

- The web terminal is reachable only through Home Assistant ingress (admins only).
- No ports are exposed; the job API is reachable only on the internal add-on network, with a token.
- Claude Code is the official, unmodified binary, verified by its sha512 checksum; the add-on never
  reads, copies or sends your sign-in, except with the opt-in usage API option described above.
- Jobs cannot change anything: see [How jobs are isolated](#how-jobs-are-isolated).
- In the terminal and in Remote Control sessions Claude Code works with your permissions on your
  configuration and asks before each change. Keep backups, ideally your configuration in git.

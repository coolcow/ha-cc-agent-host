# CC Agent Host

Runs the official, unmodified Claude Code CLI inside Home Assistant with your own
Claude subscription: a web terminal, optional Remote Control and jobs from automations.

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

The session keeps running when you close the browser. Exiting Claude Code drops you
into a shell; `exit` starts Claude Code again.

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
`max_budget_usd`, `tools` (built-in Claude Code tools), `context` (`ha_system_log`, `ha_states`, `ha_config`; `ha_log` needs the Supervisor role `homeassistant`),
`system_prompt`.

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
`POST /run {"profile": "...", "prompt": "...", "timeout": 300}`.

`/usage` returns the plan usage (5-hour and weekly windows) as reported by Claude Code's status line in
the interactive session; it never reads credentials.

## Long links

Long links (for example the sign-in link) wrap over several lines, and only the first line
is clickable. Hold **Shift** and select the whole link with the mouse: the selection is copied
automatically. Paste it into a new browser tab; the line breaks are removed on paste.

## Data

- Login and Claude Code settings: add-on data, included in backups.
- Working directory of the terminal: your Home Assistant configuration (`/homeassistant`).

## Security

- The web terminal is reachable only through Home Assistant ingress (admins only).
- No ports are exposed.

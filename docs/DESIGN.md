# Design

Goals, architecture and the reasoning behind the main decisions. User-facing details are in
[`cc_agent_host/DOCS.md`](../cc_agent_host/DOCS.md), development details in [`DEVELOPMENT.md`](DEVELOPMENT.md).

## Goal and scope

A small Home Assistant add-on as a **runtime for Claude Code**, plus a thin integration as the bridge to
Home Assistant. The add-on knows no use cases: usage statistics, log digests, dashboards and the like are
Home Assistant configuration (automations, templates, dashboards) in the user's own setup that build on
the generic features. They are not part of this repository.

Rules from Anthropic that the design follows:

- Claude Code runs **unmodified** (the official binary).
- Sign-in happens **only inside Claude Code** (`/login` in the terminal, `claude setup-token` for jobs).
- The add-on does not pass credentials on.
- Use is meant for one person with their own subscription.

## Building blocks

### Add-on

| Part | Implementation |
|---|---|
| Base | Home Assistant base image (Alpine, for the musl build of Claude Code), aarch64 and amd64, s6-overlay v3 |
| Claude Code | official native musl binary from npm, version and sha512 pinned in the Dockerfile; newer official releases installable through the update entity into `/data/cli`, verified the same way |
| Sign-in | `/login` in the terminal; credentials stay in `/data` (root only) |
| Terminal | ttyd + tmux, **ingress only** (nginx admits only the ingress gateway) |
| Session know-how | Home Assistant instructions (`CLAUDE.md`) and skills copied into the interactive Claude Code settings on start (replaced while they carry the add-on's marker); `cc-ha` (check, reload, restart, states, system log through the Supervisor proxy with the add-on token, which only root sessions have); `yamllint` with a Home Assistant config, system `ripgrep`. Nothing of it reaches jobs |
| Remote Control | option `remote_control`: separate service `claude remote-control` in server mode in `/homeassistant`, sessions on demand |
| Job API | small HTTP service (Python stdlib, `py3-yaml`, `py3-aiohttp`), internal network only, bearer token, announced to the integration via Supervisor discovery |
| Profiles | YAML files in the add-on configuration folder, extendable without changing the add-on |
| Audit log | every job with profile, duration, result size and tool calls in `/data/audit.log`, rotated |

### Jobs

Every job is isolated the same way:

- It runs as the separate Linux user **`cc_agent`**, without root and without access to the Home
  Assistant configuration, the add-on data or any Home Assistant or Supervisor token.
- `claude -p` starts with the settings from the profile: allowed tools (everything else is denied without
  prompting), model, maximum turns, time limit, budget.
- **Context data** is prepared by the add-on itself (trusted code) as files in the job's working
  directory: Home Assistant log, system log, states, history, a filtered copy of the configuration. The
  profile chooses which. Read-only jobs therefore need neither a Home Assistant token nor network access.
- One job at a time, output capped, prompt size capped.

There are no writing jobs. Changes are reserved for the interactive session (terminal or Remote Control),
where the user watches and approves.

### Integration

- Set up through Supervisor discovery (host, port and token come from the add-on).
- Action `cc_agent_host.run` (profile, prompt, timeout) with a response, for automations via
  `response_variable`.
- Sensors: signed in, job token present, job running, plan usage of the 5-hour and weekly windows, reset
  times, usage credit (usage API only), plan.
- Update entity for Claude Code releases.

## Decisions

**A – Context data for jobs.** The add-on fetches logs, states and history itself and hands them to the
job as files. The alternative, giving Claude Code access to a Home Assistant MCP server, is more powerful
but much harder to restrict to read-only operations.

**B – Plan usage.**

- *Status line (default):* Claude Code reports the 5-hour and weekly usage in its status line; the add-on
  records the values. No credentials are touched, but values only exist while a session is used.
- *Usage API (opt-in, option `usage_api`):* the add-on queries the usage endpoint with the access token
  of the interactive sign-in. Complete and always fresh, including usage credit, but add-on code reads
  the token and the endpoint is undocumented. Hence off by default; the token never leaves the add-on
  except to `api.anthropic.com`.

**C – Secrets in the configuration folder.** The profile `read-config` gets a filtered copy of the
configuration without `secrets.yaml`, `.storage/`, `.git/`, keys and certificates (`*.pem`, `*.key`);
the job user cannot reach the original folder at all. Nothing in the user's configuration is changed
(no permission changes on `secrets.yaml`).

## Permissions of the add-on

| Permission | Value | Reason |
|---|---|---|
| `homeassistant_config` | rw | interactive editing (root); jobs as `cc_agent` have no access |
| `addon_config` | rw | profiles |
| `hassio_api` | yes | context data (logs) and discovery |
| `homeassistant_api` | yes | context data (states, history) |
| AppArmor | enabled | |
| Ports | none | ingress and internal network only |
| SSH, Docker access, `privileged`, `host_network` | no | |

## Resources

- Idle: ttyd, tmux, nginx and the job API, a few tens of MB.
- A running Claude Code process (interactive session or job) needs about 300–500 MB; at most one job
  runs at a time, next to the interactive session.
- Disk: about 300–400 MB (image and Claude Code).

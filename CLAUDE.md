# CC Agent Host

Home Assistant app (add-on) that runs the official Claude Code CLI inside Home Assistant with the
user's own subscription (web terminal via ingress, optional Remote Control, headless jobs with
permission profiles), plus a thin companion integration (`cc_agent_host.run` action, sensors).
Private repository, not published yet. Owner-facing plan and decisions (German): `docs/PLAN.md`.

```
cc_agent_host/                    the add-on: config.yaml (version, options, permissions), Dockerfile
                                  (Claude Code pin + sha512), CHANGELOG.md, DOCS.md, translations/
  rootfs/usr/lib/cc_agent_host/   server.py (job API: /run /status /profiles /usage, context providers
                                  ha_log/ha_system_log/ha_states/ha_config/ha_history), statusline.py
  rootfs/usr/local/bin/           cc-session (tmux session command), cc-job-token (job token setup)
  rootfs/usr/share/cc_agent_host/ profiles/*.yaml (read, read-config, log-digest), interactive settings
  rootfs/etc/                     s6-overlay services (init-cc, session, ttyd, nginx, api), nginx, tmux
custom_components/cc_agent_host/  integration: config_flow (discovery), coordinator, api, sensor,
                                  binary_sensor, services.yaml, strings.json + translations/, CHANGELOG.md
tests/api/                        job API (pytest, fake claude), incl. security tests of profile `read`
tests/integration/                pytest-homeassistant-custom-component (Python 3.14, mocked API)
tests/addon/                      image checks + isolation test against the built image (docker)
tests/repo/                       consistency: versions/CHANGELOG, Claude Code pin, translations, naming
scripts/agent/                    check/test wrappers (below)      tools/   bump, lint/test aliases
docs/                             PLAN.md, DEVELOPMENT.md, agentic-roadmap.md
```

## Commands

Setup once: `scripts/setup` (`.venv` with ruff, pytest, pyyaml). Lint, integration and image steps need
Docker. Wrappers print one line per step on success, a capped digest + log path (`.agent-logs/`) on
failure; CI runs the same commands.

| Purpose | Command |
|---|---|
| Full check (lint → repo → api → integration → image) | `scripts/agent/check` |
| Fast check (lint, consistency, job API; seconds) | `scripts/agent/check fast` |
| Single steps | `scripts/agent/check lint` · `… repo` · `… api` · `… integration` · `… image` |
| Tests, narrowed | `scripts/agent/test api -k profile` · `scripts/agent/test tests/api/test_server.py::test_x` |
| Version raised for changed parts | `scripts/agent/version-check [base]` (default `origin/main`) |
| Latest CI failure of this branch | `scripts/agent/ci-failures` (needs `gh auth login`) |
| Install on the owner's HA (**explicit instruction only**) | `tools/deploy.sh <ha-host> [addon\|integration] [--dry-run]` |
| Read-only check of the installed add-on/integration | `tools/smoke-device.sh <ha-host>` (also explicit only: contacts the device) |
| Pin a Claude Code version | `tools/bump-claude-code.sh [version]` (also raises add-on patch version + CHANGELOG) |

Skills (`.claude/skills/`): `bump-claude-code`, `release-addon`, `ci-failures`. A PostToolUse hook lints
every edited file (ruff, shellcheck, yamllint/actionlint, hadolint) and reports findings immediately.

The image step builds for the local architecture only and needs GHCR access (base image); aarch64 is
covered by CI. If the image cannot be built locally, say so and rely on CI, don't skip silently.

## Definition of Done

1. `scripts/agent/check` green (or `fast` plus a green CI run when the image cannot be built locally).
2. Changed add-on → `version` in `cc_agent_host/config.yaml` raised + entry in `cc_agent_host/CHANGELOG.md`;
   changed integration → `version` in `custom_components/cc_agent_host/manifest.json` raised + entry in its
   `CHANGELOG.md` (newest first; Markdown-only changes exempt). `scripts/agent/version-check` passes.
3. New/changed behavior has tests (`tests/api`, `tests/integration`, `tests/addon`, `tests/repo`).
4. Docs updated: `cc_agent_host/DOCS.md` (user-facing), `README.md`, `docs/DEVELOPMENT.md`; new option →
   `config.yaml` schema + `translations/en.yaml` and `de.yaml`; new entity/service field → `strings.json`,
   `translations/en.json` (identical to strings.json) and `de.json`.
5. Small, themed pull request, Conventional Commits in English, motivation in the body.

## Hard rules

- **Claude Code is the official native musl binary from npm, pinned with sha512 for both architectures
  and never modified** (no patching, wrapping of the binary, or alternative builds). Version bumps only via
  `tools/bump-claude-code.sh`. Auto-updater stays disabled in the image.
- **No project code reads, copies or sends credentials.** Sign-in happens only inside Claude Code
  (`/login`). Sole exception: the opt-in option `usage_api` (default `false`, off in releases), which reads
  the interactive token only to query the usage endpoint at api.anthropic.com. Never widen this.
- **Nothing in the Home Assistant core system is changed** by the add-on or the integration (no edits to
  the user's configuration, no core patches). Interactive editing happens only in the user's session.
- **Minimal privileges:** no exposed ports (`ports:` stays absent), terminal only via ingress (nginx admits
  only the ingress gateway), job API only on the internal network with a bearer token, no `privileged`,
  `host_network`, Docker or SSH access, AppArmor stays enabled. Jobs run as `cc_agent` without root, without write
  access to `/homeassistant` and without HA/Supervisor tokens (`tests/addon/test_isolation.sh`).
- **Naming (trademark):** no "Claude" in names or identifiers. Display name "CC Agent Host", identifier
  `cc_agent_host`. In descriptions refer to the product only as "for Claude Code" / "Claude Code". Never
  explain the abbreviation "cc". Enforced in part by `tests/repo`.
- **Use cases are not part of this repository** (usage statistics, log digests, dashboards, …): they are
  Home Assistant configuration in the user's own setup. The add-on stays generic.
- **64-bit only** (aarch64, amd64): there is no 32-bit Claude Code.
- **Deploying to a real Home Assistant and restarting Home Assistant only on the owner's explicit
  instruction**, never on your own initiative (also not "to test"). This includes `ssh`/`scp` to the device.
- Never make the repository public, create releases/tags or push images without the owner's instruction.

## Conventions & gotchas

- Job API server: Python stdlib plus Alpine's `py3-yaml` and `py3-aiohttp` (no pip in the image; add
  dependencies only as Alpine packages in the Dockerfile). Tests import it from `cc_agent_host/rootfs/usr/lib/cc_agent_host` and configure it via
  `CC_*` environment variables (`tests/api/conftest.py`).
- s6-overlay v3 (`init: false` in config.yaml); base image `ghcr.io/home-assistant/base`, no build.yaml.
- Integration tests need Python ≥ 3.14 and `python -m pytest` (repo root on `sys.path`); the wrapper
  handles both (container fallback).
- Profiles are YAML in the image and extendable by the user under `/addon_configs/…/profiles/`; schema in
  `normalize_profile()` of server.py.
- HACS validation only runs in CI once the repository is public; file-level HACS checks live in `tests/repo`.
- Local installation on a device: `tools/deploy.sh` (guards: clean tree, full check, newer version; never
  restarts HA), details in `docs/DEVELOPMENT.md`. Only on explicit instruction, see above.

Background docs: `docs/PLAN.md` (goals, decisions A/B/C, permissions table, backlog),
`docs/DEVELOPMENT.md` (tests, CI, versioning), `docs/agentic-roadmap.md` (tooling decisions).

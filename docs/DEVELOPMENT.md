# Development

## Principles

- Claude Code is the official native build, pinned and checksum-verified, never modified.
- Sign-in happens only inside Claude Code. No project code reads, copies or sends credentials
  (exception: the opt-in usage option B2, see `PLAN.md`, off by default and off in releases).
- Small image, minimal privileges, no exposed ports.
- Use cases (usage statistics, log digests, …) are Home Assistant configuration, not part of
  the app.

## Local installation (Home Assistant OS)

Only on the owner's decision. Needs SSH access to the device (Terminal & SSH app).

```bash
tools/deploy.sh <ha-host> --dry-run        # guards only, prints the remote commands
tools/deploy.sh <ha-host> [addon|integration|all] [--redeploy]
tools/smoke-device.sh <ha-host>            # read-only: versions, add-on state, job API, sensors
```

`tools/deploy.sh` refuses a dirty working tree, runs the full `scripts/agent/check`, requires a version newer
than the installed one (`--redeploy` allows the same version, never an older one), then copies the
*committed* files (`git archive`) to `/local_apps/cc_agent_host` and `/homeassistant/custom_components/cc_agent_host`
(staged, so removed files do not linger) and runs `ha store reload` plus `ha apps install|update|rebuild
local_cc_agent_host` (Supervisor refuses `rebuild` after a version change). It never restarts Home
Assistant; a new integration version needs `ha core restart`, done by the owner. Afterwards it runs the
smoke test. Both scripts are tested against a fake device in `tests/repo/test_device_tools.py`.

Manual equivalent:

```bash
tar -cf - --owner=0 --group=0 cc_agent_host | ssh <ha-host> 'tar -xf - -C /local_apps'
ssh <ha-host> 'ha store reload && ha apps install local_cc_agent_host'   # first time
ssh <ha-host> 'ha store reload && ha apps update local_cc_agent_host'    # after a version bump
```

Raise `version` in `cc_agent_host/config.yaml` (add-on) or `custom_components/cc_agent_host/manifest.json`
(integration) and add an entry to the matching `CHANGELOG.md` for every change (Markdown-only changes
exempt). Enforced by `scripts/agent/version-check` (CI on pull requests) and the consistency tests.

## Tests

One entry point for humans, agents and CI: `scripts/agent/check` (one line per step on success, a capped
failure digest plus the full log in `.agent-logs/` on failure). Setup once: `scripts/setup` (creates
`.venv` with ruff, pytest, pyyaml); lint, integration and image steps need Docker.

| Step | What | Command |
|---|---|---|
| `lint` | shellcheck, hadolint, yamllint (strict), actionlint, ruff | `scripts/agent/check lint` |
| `repo` | consistency: versions, CHANGELOG, Dockerfile pin, translations, naming | `scripts/agent/test repo` |
| `api` | job API (pytest): auth, IP guard, limits, profiles; security: profile `read` cannot write, run commands, read secrets or reach tokens | `scripts/agent/test api` |
| `integration` | pytest-homeassistant-custom-component (Python 3.14, mocked API; container if needed) | `scripts/agent/test integration` |
| `image` | builds, Claude Code runs, nginx config valid, ttyd socket mode, services, no ports; job isolation | `scripts/agent/check image` |
| – | hassfest; HACS validation (public repository only) | CI only |
| On device | read-only smoke test after installing (versions, state, job API, sensors) | `tools/smoke-device.sh <ha-host>` |

`scripts/agent/check` runs all steps (fail-fast), `scripts/agent/check fast` only lint, repo and api.
Narrow tests with pytest selectors: `scripts/agent/test tests/api/test_server.py -k profile`.
Latest CI failure of the current branch: `scripts/agent/ci-failures` (needs `gh auth login`).

## CI (GitHub Actions)

- `ci.yaml` on push to `main`, pull requests, nightly and on dispatch:
  - `lint` (shellcheck, hadolint, yamllint, ruff), `api` (pytest, Python 3.12), `integration`
    (pytest-homeassistant-custom-component, Python 3.14), `hassfest`
  - `hacs` only once the repository is public (HACS cannot read a private repository)
  - `image`: amd64 always; aarch64 (native arm runner) only when `cc_agent_host/` or `tests/addon/`
    changed, and nightly. Builds the image and runs `tests/addon/test_image.sh` and `test_isolation.sh`.
  - `CI Gate`: aggregates all jobs; the single check to require in branch protection.
- `bump-claude-code.yaml`, daily: `tools/bump-claude-code.sh` pins the latest npm release (version,
  checksums), raises the add-on patch version, adds the CHANGELOG entry, opens a pull request and
  dispatches CI for it. No auto-merge.
- `release.yaml` on tag `v*` *(planned)*: builds multi-arch images and pushes them to GHCR. Later, set
  `image:` in `config.yaml` so users pull prebuilt images instead of building on device.
- Dependabot for GitHub Actions (pinned to commit SHAs), the integration test harness and the base image.
  Base image bumps need a version + CHANGELOG commit before merge.

## Versioning

- App version: SemVer in `config.yaml`, tag `vX.Y.Z`.
- Claude Code version bumps raise the patch version.

## Scope

The project is the add-on plus the generic integration (the bridge to Home Assistant). Use cases such as
log digests or usage statistics are *not* part of it: they are automations/packages in the user's own
configuration (later possibly shared as blueprints in a separate repository).

## Installing the integration locally

`tools/deploy.sh <ha-host> integration` (see above), then restart Home Assistant; the add-on's discovery
offers the setup under Settings → Devices & services.

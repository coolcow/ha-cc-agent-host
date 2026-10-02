# Development

## Principles

- Claude Code is the official native build, pinned and checksum-verified, never modified.
- Sign-in happens only inside Claude Code. No project code reads, copies or sends credentials
  (exception: the opt-in usage option B2, see `PLAN.md`, off by default and off in releases).
- Small image, minimal privileges, no exposed ports.
- Use cases (usage statistics, log digests, …) are Home Assistant configuration, not part of
  the app.

## Local installation (Home Assistant OS)

```bash
tar -cf - --owner=0 --group=0 cc_agent_host | ssh <ha-host> 'tar -xf - -C /local_apps'
ssh <ha-host> 'ha store reload && ha apps install local_cc_agent_host'   # first time
ssh <ha-host> 'ha store reload && ha apps rebuild local_cc_agent_host'   # after changes
```

Raise `version` in `cc_agent_host/config.yaml` and add a `CHANGELOG.md` entry for every change.

## Tests

| Level | What | How |
|---|---|---|
| Lint | shell (shellcheck), Dockerfile (hadolint), YAML (yamllint); later Python (ruff) | `tools/lint.sh` (docker) |
| Image | builds, Claude Code runs, nginx config valid, ttyd socket mode, services present, no ports | `tests/addon/test_image.sh` (docker) |
| Job API *(phase 2)* | pytest: auth, IP guard, limits, profiles; security: profile `read` cannot write, run commands, read secrets or reach tokens | `pytest tests/api` |
| Integration *(phase 3)* | pytest-homeassistant-custom-component; hassfest and HACS validation in CI | `pytest tests/integration` |
| On device | install on the device, manual checklist per phase | `docs/PLAN.md` |

## CI strategy (GitHub Actions, once published)

- `ci.yaml` on push and pull request:
  - lint job (shellcheck, hadolint, yamllint, ruff)
  - build job, matrix amd64 + aarch64 (buildx with QEMU), then `tests/addon/test_image.sh` against
    the built image
  - pytest jobs for the job API and the integration *(when they exist)*
  - hassfest and HACS validation for the integration *(when it exists)*
- `bump-claude-code.yaml`, scheduled daily: runs `tools/bump-claude-code.sh` against the latest npm
  release and opens a pull request (version, checksums, changelog). CI must pass before merge;
  no auto-merge.
- `release.yaml` on tag `v*`: builds multi-arch images and pushes them to GHCR. Later, set `image:`
  in `config.yaml` so users pull prebuilt images instead of building on device.
- Dependabot for GitHub Actions; actions pinned to commit SHAs.

## Versioning

- App version: SemVer in `config.yaml`, tag `vX.Y.Z`.
- Claude Code version bumps raise the patch version.

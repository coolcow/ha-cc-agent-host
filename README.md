# CC Agent Host

Home Assistant app (add-on) that runs the official, unmodified Claude Code CLI inside
Home Assistant with your own Claude subscription:

- web terminal in the Home Assistant sidebar (ingress only)
- optional Claude Code Remote Control in server mode (sessions on demand)
- jobs from automations with permission profiles *(planned)*
- companion integration with a `cc_agent_host.run` action and sensors *(planned)*

Not affiliated with or endorsed by Anthropic. Claude and Claude Code are trademarks of
Anthropic, PBC. You sign in with your own account inside Claude Code; this project never
handles your credentials.

## Repository layout

| Path | Content |
|---|---|
| `cc_agent_host/` | the app (add-on) |
| `custom_components/cc_agent_host/` | the integration *(planned)* |
| `tests/` | tests for app and integration |
| `tools/` | maintenance scripts (Claude Code version bump, deploy, smoke test) |
| `scripts/` | setup and check/test wrappers (`scripts/agent/`) |
| `docs/` | plan and development notes |

## Installation

Not published yet. See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for local installation.

## Development

Dev container (`.devcontainer/`: Python 3.14, Docker CLI → host Docker, gh, Claude Code; logins in the shared
volumes `devcontainer-claude-config` / `devcontainer-gh-config`): `npx @devcontainers/cli up --workspace-folder .`,
then `npx @devcontainers/cli exec --workspace-folder . claude` (or VS Code "Reopen in Container").
Without it: `scripts/setup`. Checks: `scripts/agent/check`. Details: [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md),
agent rules: [`CLAUDE.md`](CLAUDE.md).

## License

MIT, see [LICENSE](LICENSE).

# CC Agent Host

Home Assistant app (add-on) that runs the official, unmodified Claude Code CLI inside
Home Assistant with your own Claude subscription:

- web terminal in the Home Assistant sidebar (ingress only)
- optional Claude Code Remote Control, always on
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
| `tools/` | maintenance scripts (e.g. Claude Code version bump) |
| `docs/` | plan and development notes |

## Installation

Not published yet. See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for local installation.

## License

MIT, see [LICENSE](LICENSE).

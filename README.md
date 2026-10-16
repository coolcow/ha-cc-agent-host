# CC Agent Host

**Claude Code, running inside Home Assistant, next to your configuration.**
A Home Assistant app (add-on) plus a small companion integration that let you use the official
Claude Code CLI with your own Claude subscription: in the Home Assistant sidebar, from the Claude app
on your phone, and from your automations.

*Deutsch: [README.de.md](README.de.md)*

> Not affiliated with or endorsed by Anthropic. Claude and Claude Code are trademarks of Anthropic, PBC.
> You sign in with your own account inside Claude Code; this project never handles your credentials.

## Why?

Claude Code is very good at the kind of work a Home Assistant setup needs: writing and fixing YAML,
untangling automations and templates, reading through logs to find out why something broke. But it
works on files, and your configuration lives on the Home Assistant machine. Today that usually means one
of these:

- copying YAML and log excerpts into a chat window and the answers back, without the assistant ever
  seeing the rest of your setup;
- mounting the configuration over Samba or SSH on a computer that has Claude Code installed, and
  keeping both in sync;
- installing tools on the Home Assistant host by hand, which Home Assistant OS does not support.

CC Agent Host removes that gap. Claude Code runs as a regular add-on on the same machine, with your
Home Assistant configuration as its working directory. It sees the real files, can read the logs, and
you watch and approve every change it makes. Nothing to install on your computer, nothing to sync.

## What you get

- **Web terminal in the sidebar.** Claude Code in your browser, on any device that can open Home
  Assistant. The session keeps running when you close the tab.
- **Remote Control (optional).** The add-on shows up as an environment in claude.ai/code and the Claude
  app. Open a session from your phone while you are away and fix that automation from the sofa or the
  train; Claude Code still asks before each change.
- **Jobs from automations.** The action `cc_agent_host.run` sends a prompt to Claude Code and returns
  the answer to your automation, for example "summarize what broke in the last 24 hours" every morning,
  sent to your phone only when there is something new. Jobs run read-only in a sandbox (details below).
- **Sensors.** Signed in, job running, plan usage of the 5-hour and weekly windows with reset times,
  and the detected plan, ready for dashboards and alerts.
- **Claude Code updates as Home Assistant updates.** The add-on brings a pinned, checksum-verified
  version and offers newer official releases under Settings → Updates. Nothing updates on its own.

## Is it for you?

Good fit if you

- already have a Claude Pro or Max subscription and would rather use it than pay per API token;
- edit your configuration as YAML (or want to start) and want an assistant that sees the whole picture;
- want to ask your Home Assistant questions on a schedule without giving an AI write access.

Requirements and limits:

- Home Assistant OS or Supervised on 64-bit hardware (aarch64 or amd64), for example Home Assistant
  Green or Yellow, Raspberry Pi 4/5 with 64-bit OS, x86-64 mini PCs and VMs. Container and Core
  installations have no add-ons. There is no 32-bit build of Claude Code.
- 2 GB RAM or more: a running Claude Code process needs about 300–500 MB.
- Meant for one person with their own subscription, as Anthropic's terms intend.
- In the terminal and in Remote Control sessions Claude Code can change your configuration (after
  asking you). Keep backups, or better, keep your configuration in git.

## Safety at a glance

- Claude Code is the **official, unmodified** binary from npm, pinned with its sha512 checksum.
- **Sign-in only inside Claude Code** (`/login`). The add-on does not read, copy or send your
  credentials. The single exception is the opt-in option *Full plan usage via usage API* (off by
  default), explained in the [documentation](cc_agent_host/DOCS.md#plan-usage).
- **No open ports.** The terminal is reachable only through Home Assistant ingress (admins only); the job
  API only on the internal add-on network, with a token.
- **Jobs are sandboxed:** an unprivileged user without access to your configuration, secrets, login or
  Home Assistant tokens, only the tools the profile allows, one job at a time, every job logged.
- **Nothing in Home Assistant itself is changed** by the add-on or the integration.

## Installation

The repository is not published yet; the steps below describe the setup once it is.

1. **Add-on:** Settings → Add-ons → Add-on store → ⋮ → Repositories, add
   `https://github.com/coolcow/ha-cc-agent-host`, then install **CC Agent Host** and start it.
   The image is built on your device during installation; that takes a few minutes.
2. **Sign in:** open **CC Agent Host** in the sidebar, type `/login` and finish the sign-in in your browser.
3. **Integration (optional, for jobs and sensors):** in HACS → ⋮ → Custom repositories, add the same URL
   as type *Integration*, install **CC Agent Host** and restart Home Assistant. The add-on is then
   discovered under Settings → Devices & services.
4. **Jobs (optional):** create a job token once, as described in the
   [documentation](cc_agent_host/DOCS.md#jobs).

## Example: a morning log digest

```yaml
automation:
  - alias: Morning log digest
    triggers:
      - trigger: time
        at: "07:30:00"
    actions:
      - action: cc_agent_host.run
        data:
          profile: log-digest
          prompt: >-
            List new errors and warnings from the last 24 hours in at most five bullet points.
            Answer exactly "nothing new" if there are none.
        response_variable: digest
      - if: "{{ digest.ok and digest.result | trim != 'nothing new' }}"
        then:
          - action: notify.mobile_app_my_phone
            data:
              title: Home Assistant log
              message: "{{ digest.result }}"
```

## Documentation

- [Add-on documentation](cc_agent_host/DOCS.md): terminal, Remote Control, jobs and profiles, plan
  usage, updates, security ([Deutsch](cc_agent_host/DOCS.de.md))
- [Design](docs/DESIGN.md): goals, architecture and the reasoning behind the main decisions
- [Development](docs/DEVELOPMENT.md): tests, CI, versioning, local installation

## Development

Dev container (`.devcontainer/`: Python 3.14, Docker CLI → host Docker, gh, Claude Code):
`npx @devcontainers/cli up --workspace-folder .`, then
`npx @devcontainers/cli exec --workspace-folder . claude` (or VS Code "Reopen in Container").
Without it: `scripts/setup`. Checks: `scripts/agent/check`. Details in
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md), rules for coding agents in [`CLAUDE.md`](CLAUDE.md).

## License

MIT, see [LICENSE](LICENSE).

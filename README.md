# CC Agent Host

**Claude Code, running inside Home Assistant, next to your configuration.**
A Home Assistant app (add-on) plus a small companion integration that let you use the official
Claude Code CLI with your own Claude subscription: in the Home Assistant sidebar, from the Claude app
on your phone, and from your automations.

**Stop building dashboards, automations and scripts by hand like it's the Stone Age.** Tell Claude what
you want, then just use it. Claude Code builds it right in your configuration, keeps an eye on things
with scheduled jobs and suggests improvements, so your setup gets better with every round of using it
and talking it over. And unlike an assistant connected from outside via MCP, everything runs inside
Home Assistant: nothing else to install, no second computer.

*Deutsch: [README.de.md](README.de.md)*

> Not affiliated with or endorsed by Anthropic. Claude and Claude Code are trademarks of Anthropic, PBC.
> You sign in with your own account inside Claude Code; this project never handles your credentials.

## What you get

Claude Code runs on the Home Assistant machine itself, with your configuration as its working directory.
It sees the real files and logs; no copying YAML into a chat, no syncing to another computer.

- **Web terminal in the sidebar**, on any device that opens Home Assistant. The session keeps running
  when you close the tab.
- **Remote Control (optional):** open a session from claude.ai/code or the Claude app on your phone.
- **Jobs from automations:** the action `cc_agent_host.run` sends a prompt and returns the answer to your
  automation. Jobs run read-only in a sandbox.
- **Sensors** for sign-in, running jobs and plan usage, and **Claude Code updates** under Settings → Updates
  (pinned and checksum-verified, never automatic).

## Use cases

**In the terminal or from your phone** (Claude Code asks before every change):

- "Why didn't the hallway light turn on last night?" It reads the automation, its trace and the log.
- "Write an automation that turns off the heating when a window has been open for five minutes."
- "Which automations, scripts and dashboards still use entities that no longer exist?"
- "Move the climate automations into a package and turn the three similar ones into a blueprint."
- "Read the breaking changes of the latest release and check my configuration against them."
- "Add a temperature sensor to my ESPHome device `office` and explain the wiring."

**As jobs from automations** (read-only, answer back to the automation):

- A morning digest of new errors, sent only when there is something new (example below).
- A weekly check for unavailable devices and low batteries, with your own profile (example below).
- "Summarize heating and energy of the last week and point out anything unusual" (context `ha_history`).
- "Does my configuration still reference `light.old_lamp`?" before you remove a device (`read-config`).

Morning log digest with the built-in profile `log-digest`:

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

Your own profile, as `profiles/house-check.yaml` in the add-on configuration folder, then used with
`profile: house-check` and a prompt such as "Which devices have been unavailable for more than a day,
and which batteries are below 20 %?":

```yaml
description: Weekly look at devices and batteries
model: sonnet
max_turns: 10
timeout: 300
tools: [Read, Grep, Glob]
context:
  - ha_states:
      domains: [sensor, binary_sensor, light, switch, climate]
```

## Requirements

- **Home Assistant OS** on 64-bit hardware (aarch64 or amd64): Home Assistant Green or Yellow,
  Raspberry Pi 4/5, x86-64 mini PCs and VMs. Supervised installations work too but are no longer
  supported by Home Assistant; Container and Core installations have no apps. There is no 32-bit build
  of Claude Code.
- 2 GB RAM or more: a running Claude Code process needs about 300–500 MB.
- A Claude Pro or Max subscription, meant for one person, as Anthropic's terms intend.

## Safety

There are two ways to work, with different rights:

- **Terminal and Remote Control: you are in charge.** Claude Code works in your configuration and can
  create or change automations and other files, but asks before every change and shows it to you first.
  Keep backups, or better, keep your configuration in git.
- **Jobs from automations: read-only.** A job runs as an unprivileged user and sees only the data its
  profile provides (for example the log or a filtered copy of the configuration), never the real
  configuration, secrets, sign-in or Home Assistant tokens. It can use only the tools the profile allows
  and changes nothing; every job is logged.

In both cases:

- Claude Code is the **official, unmodified** binary from npm, pinned with its sha512 checksum.
- **Sign-in only inside Claude Code** (`/login`); the add-on never reads, copies or sends your
  credentials, except with the opt-in option *Full plan usage via usage API*
  ([details](cc_agent_host/DOCS.md#plan-usage)).
- **No open ports:** terminal only through Home Assistant ingress (admins), job API only on the internal
  network with a token.

## Installation

The repository is not published yet; the steps below describe the setup once it is.

1. **App:** Settings → Apps → app store → ⋮ → Repositories, add
   `https://github.com/coolcow/ha-cc-agent-host`, then install **CC Agent Host** and start it.
   The image is built on your device during installation; that takes a few minutes.
2. **Sign in:** open **CC Agent Host** in the sidebar, type `/login` and finish the sign-in in your browser.
3. **Integration (optional, for jobs and sensors):** in HACS → ⋮ → Custom repositories, add the same URL
   as type *Integration*, install **CC Agent Host** and restart Home Assistant. The add-on is then
   discovered under Settings → Devices & services.
4. **Jobs (optional):** create a job token once, as described in the
   [documentation](cc_agent_host/DOCS.md#jobs).

## Documentation

- [Add-on documentation](cc_agent_host/DOCS.md): terminal, Remote Control, jobs and profiles, plan
  usage, updates, security ([Deutsch](cc_agent_host/DOCS.de.md))
- [Design](docs/DESIGN.md) · [Development](docs/DEVELOPMENT.md) (dev container, tests, CI) ·
  [Security policy](SECURITY.md) · rules for coding agents in [CLAUDE.md](CLAUDE.md)

## License

MIT, see [LICENSE](LICENSE).

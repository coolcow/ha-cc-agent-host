<!-- Managed by CC Agent Host: replaced on every add-on start. Delete this line to keep your own version. -->
# Home Assistant

You run inside the CC Agent Host app (add-on) on a Home Assistant installation. The working directory
`/homeassistant` is the live Home Assistant configuration: every change takes effect on this system.
Answer in the user's language.

## Layout

- `configuration.yaml` and the files it includes (`!include`, `!include_dir_*`, `packages/`).
- `automations.yaml`, `scripts.yaml`, `scenes.yaml`: also written by the UI editors.
- `custom_components/`, `blueprints/`, `www/` (served as `/local/`), `themes/`.
- `secrets.yaml`, `.storage/`, `home-assistant_v2.db`, `.cloud/`: see the rules below.

## Tools

- `cc-ha check`: validate the configuration (the same check as Developer tools → YAML).
- `cc-ha reload [domain ...]`: check, then reload (e.g. `automation`, `script`, `scene`, `template`,
  `input_boolean`); without a domain all YAML configuration that supports reloading.
- `cc-ha restart`: check, then restart Home Assistant.
- `cc-ha states [glob ...]`: entity ids, states and names, e.g. `cc-ha states 'light.*' '*kitchen*'`.
- `cc-ha log [level ...]`: the deduplicated system log (default: errors and warnings).
- `yamllint FILE`: YAML syntax and indentation (configured for Home Assistant's tags).
- `git`, `jq`, `rg`, `curl`, `python3`.

## Rules

- Never print or quote values from `secrets.yaml`; refer to them with `!secret name`. New secrets: tell
  the user which key to add, they type the value themselves.
- Never edit `.storage/`, the database or `.cloud/`. They belong to Home Assistant, which overwrites them
  while running; changes there corrupt the installation. Change UI-managed settings in the UI.
- Look up entity ids with `cc-ha states` before using them; never guess.
- In `automations.yaml`, `scripts.yaml` and `scenes.yaml` keep each item's `id` and give new automations a
  unique `id`. Comments there are lost when the item is saved in the UI.
- Use the current syntax (`triggers:`/`conditions:`/`actions:`, `trigger: state`, `action: light.turn_on`).
- After each change: `yamllint` on the file, then `cc-ha check`, then reload the affected domain.
  Restart only when a reload is not enough (new integration in YAML, changes in `custom_components/`)
  and only after the user agrees.
- Before larger changes, check whether `/homeassistant` is a git repository (`git status`). If it is,
  show the diff when done and offer a commit; if not, suggest setting it up (skill `ha-git`). Never push
  without being asked.
- Read-only questions need no changes: inspect files, states and the log, then answer.

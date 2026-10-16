---
name: ha-automation
description: Create or change a Home Assistant automation, script or scene in YAML, validate it and reload it. Use when the user asks for a new automation, script or scene, or to change an existing one.
---

# Automation, script or scene

1. **Understand the goal.** Trigger, conditions, actions, and edge cases (night, nobody home, device
   unavailable). Ask only what cannot be read from the configuration.
2. **Find the entities.** `cc-ha states '<domain>.*'` or `cc-ha states '*<room>*'`. Use only ids that
   exist; if one is missing, say so instead of inventing it.
3. **Find the place.** Look at how the configuration is organised (`configuration.yaml`: `automation:`
   with `!include automations.yaml`, `!include_dir_*` or `packages/`) and follow it. Changing an
   existing item: find it by `alias` or `id` with `rg`.
4. **Write it.** Current syntax (`triggers:`, `conditions:`, `actions:`, `trigger: state`,
   `action: light.turn_on`, `target:`). A new automation in `automations.yaml` gets a unique `id`
   (e.g. the current Unix time in milliseconds) and an `alias`; add a short `description`. Keep the
   `id` of existing items. Prefer `mode: restart` or `single` deliberately, not by default.
5. **Validate.** `yamllint <file>`, then `cc-ha check`. Fix every error before going on.
6. **Reload.** `cc-ha reload automation` (or `script`, `scene`). No restart needed.
7. **Check it loaded.** `cc-ha states 'automation.*'` shows the new entity (`on`); `cc-ha log` shows no
   new errors for it.
8. **Hand over.** Show the final YAML or the diff, say how to test it (run it from the UI, or trigger
   it, then look at the trace under Settings → Automations → ⋮ → Traces). With git, offer a commit.

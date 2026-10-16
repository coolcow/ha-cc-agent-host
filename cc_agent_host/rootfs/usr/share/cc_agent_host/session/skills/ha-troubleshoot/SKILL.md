---
name: ha-troubleshoot
description: Find the cause of Home Assistant errors, warnings, unavailable entities or a configuration that does not load, and propose a fix. Use when the user reports a problem, an error in the log, or asks what is wrong.
---

# Troubleshooting

1. **Collect.** `cc-ha log` (errors and warnings, deduplicated, with counts), `cc-ha check`, and for a
   concrete device `cc-ha states '*<name>*'` (look for `unavailable` and `unknown`).
2. **Group.** Sort the entries by integration (logger name `homeassistant.components.<x>` or
   `custom_components.<x>`), most frequent and most recent first. Separate noise (one-off timeouts,
   deprecation warnings) from real faults.
3. **Find the cause.** Read the configuration of the affected integration (`rg -n '<x>' --glob '*.yaml'`),
   compare it with the error message and with the integration's documentation. For a custom integration
   check its version in `custom_components/<x>/manifest.json`. Do not open `.storage/` or `secrets.yaml`.
4. **Report.** Per problem: what happens, the likely cause (say how sure you are), and the fix. Name
   what only the user can do (a device that is offline, a credential in the UI, an update).
5. **Fix only with consent.** Change YAML as the user agrees, then `yamllint`, `cc-ha check` and
   `cc-ha reload <domain>`, and look at `cc-ha log` again. A restart only when needed and agreed.

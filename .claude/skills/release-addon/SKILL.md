---
name: release-addon
description: Prepare a release of the add-on and/or the integration – version bump, CHANGELOG entry, checks, release PR – and (only on explicit owner instruction) the tag. Use when asked to release, cut a version, or bump the add-on/integration version.
allowed-tools: Bash(scripts/agent/check *) Bash(scripts/agent/check) Bash(scripts/agent/version-check *) Bash(scripts/agent/version-check) Bash(git diff *) Bash(git log *)
---

Versions: SemVer. Add-on in `cc_agent_host/config.yaml` (`version: "X.Y.Z"`, quoted), integration in
`custom_components/cc_agent_host/manifest.json`. Each has its own `CHANGELOG.md`, newest entry first,
heading `## X.Y.Z`, user-facing bullet points (what changed for the user, not how).

1. Find what changed since the last version: `git log --oneline <last-version-commit>..HEAD -- cc_agent_host`
   (resp. `custom_components/cc_agent_host`). Markdown-only changes need no release.
2. Choose the bump: patch = fixes and Claude Code bumps; minor = new options, endpoints, context providers,
   sensors, profiles; major = breaking changes to options, profiles, the job API or entity IDs (call these out
   in the CHANGELOG with migration steps).
3. Raise the version and write the CHANGELOG entry. Options/entities changed → translations (`en`/`de`) and
   `DOCS.md` updated in the same change.
4. `scripts/agent/check` (or `fast` + CI for the image) and `scripts/agent/version-check` must be green;
   `tests/repo` enforces version == newest CHANGELOG entry.
5. Pull request `chore(release): add-on X.Y.Z` (and/or `integration X.Y.Z`).
6. **Tags, GitHub releases and image pushes only when the owner explicitly asks for them** (the repository is
   private and unpublished). Then: tag `vX.Y.Z` on the merged `main` commit for the add-on version.
7. **Installing on the owner's Home Assistant is a separate, explicit instruction** (`tools/deploy.sh`), never
   part of a release by default.

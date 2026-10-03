---
name: bump-claude-code
description: Pin a new Claude Code version in the add-on (Dockerfile version + sha512 for both architectures, add-on patch version, CHANGELOG). Use when asked to update/bump Claude Code, or when reviewing a bump PR from the bump-claude-code workflow.
allowed-tools: Bash(tools/bump-claude-code.sh *) Bash(tools/bump-claude-code.sh) Bash(scripts/agent/check *) Bash(scripts/agent/version-check *) Bash(git diff *)
---

Claude Code must stay the official, unmodified npm build, verified by sha512. Never edit the
`ARG CLAUDE_CODE_VERSION` / `SHA512_*` lines by hand.

1. Run `tools/bump-claude-code.sh` (latest) or `tools/bump-claude-code.sh <X.Y.Z>`. It reads the
   `dist.integrity` (sha512) of `@anthropic-ai/claude-code-linux-{arm64,x64}-musl` from the npm registry,
   updates the Dockerfile and, if the version changed, raises the add-on patch version in
   `cc_agent_host/config.yaml` and adds `## <new>` / `- Claude Code <version>` to `cc_agent_host/CHANGELOG.md`.
   If the add-on has unreleased changes already (newest CHANGELOG entry not yet merged to `main`), fold the
   line into that entry instead of a second version bump.
2. `git diff`: exactly three Dockerfile ARG lines, the version, one CHANGELOG entry. Nothing else.
3. `scripts/agent/check fast` and `scripts/agent/version-check`. The image step (`scripts/agent/check image`)
   proves the checksum and `claude --version`; if the image cannot be built locally (no GHCR access), CI
   (`image` jobs, both architectures) is the proof – say so.
4. Commit `build: bump Claude Code to X.Y.Z`; skim the upstream changelog for changes that affect the add-on
   (CLI flags used in `server.py` `build_command()`, `--remote-control`, `auth status`, status line JSON) and
   mention them in the PR body.

Downgrades work the same way (`tools/bump-claude-code.sh <older>`), but still raise the add-on version.

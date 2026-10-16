---
name: ha-git
description: Put the Home Assistant configuration under git version control with a safe .gitignore, or check an existing setup. Use when the user wants versioning or backups of their configuration, or before larger changes when /homeassistant is not a git repository yet.
---

# Configuration under git

1. **Look first.** `git -C /homeassistant status`. If it already is a repository, check that the
   `.gitignore` covers the entries below and that none of them is tracked
   (`git ls-files | rg -n 'secrets.yaml|\.storage/|\.db|\.log|\.cloud/'`); report what you find, change
   nothing without asking.
2. **Ask** before creating the repository; explain that it stays local (nothing leaves the device unless
   the user adds a remote later).
3. **`.gitignore`** (extend, never shrink an existing one):

   ```gitignore
   secrets.yaml
   .storage/
   .cloud/
   .cache/
   deps/
   tts/
   backups/
   *.db
   *.db-shm
   *.db-wal
   *.log
   *.log.*
   *.pem
   *.key
   .HA_VERSION
   __pycache__/
   ```

4. **Create.** `git init`, set a local identity only if none is configured (ask the user for name and
   e-mail; a neutral local identity is fine too), `git add -A`, then show
   `git status --short` and check again that no secret file is staged before the first commit.
5. **Afterwards.** Each later change: show `git diff`, commit with a short message on request. Never
   push, add a remote or rewrite history unless the user asks; never commit `secrets.yaml`.

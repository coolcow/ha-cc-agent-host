#!/usr/bin/env python3
"""Status line command for the interactive session.

Prints a short status line and stores the plan usage that Claude Code reports
(rate_limits) for the job API's /usage endpoint. Never touches credentials."""
import json
import os
import sys
import time

USAGE_FILE = os.environ.get("CC_USAGE_FILE", "/run/cc/usage.json")

try:
    d = json.load(sys.stdin)
except ValueError:
    d = {}

limits = d.get("rate_limits") or {}
if limits:
    tmp = USAGE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"updated_at": int(time.time()), "rate_limits": limits}, f)
    os.replace(tmp, USAGE_FILE)

parts = [(d.get("model") or {}).get("display_name") or "Claude"]
ctx = (d.get("context_window") or {}).get("used_percentage")
if ctx is not None:
    parts.append(f"ctx {ctx:.0f}%")
for key, label in (("five_hour", "5h"), ("seven_day", "week")):
    pct = (limits.get(key) or {}).get("used_percentage")
    if pct is not None:
        parts.append(f"{label} {pct:.0f}%")
print(" · ".join(parts))

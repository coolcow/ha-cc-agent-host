#!/usr/bin/env python3
"""CC Agent Host job API.

Runs Claude Code headless jobs (`claude -p`) as the unprivileged user cc_agent, with the
tools, model and context files defined by a profile. Listens on the internal Home Assistant
network only and requires a bearer token.

Endpoints:
    GET  /status    add-on state, sign-in, job token, running job, profiles
    GET  /profiles  profile names and descriptions
    GET  /usage     plan usage as last reported by Claude Code's status line
    POST /run       {"profile": str, "prompt": str, "timeout": int?} -> job result
    POST /cli/update  {"version": str?} -> installs that Claude Code version (default: latest)
"""
import fnmatch
import functools
import hashlib
import hmac
import base64
import ipaddress
import json
import os
import platform
import re
import secrets
import shutil
import signal
import subprocess
import tarfile
import threading
import time
import urllib.request
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

ENV = os.environ.get
DATA = Path(ENV("CC_DATA", "/data"))
HA_CONFIG = Path(ENV("CC_HA_CONFIG", "/srv/ha/config"))
PROFILES = Path(ENV("CC_PROFILES", "/srv/ha/addon_config/profiles"))
JOBS = Path(ENV("CC_JOBS", "/tmp/cc-jobs"))
USAGE_FILE = Path(ENV("CC_USAGE_FILE", "/run/cc/usage.json"))
CLAUDE = ENV("CC_CLAUDE", "claude")
RUN_AS = ENV("CC_RUN_AS", "cc_agent:cc_agent")  # empty: run as the server user (tests)
AGENT_HOME = Path(ENV("CC_AGENT_HOME", "/data/agent"))
SUPERVISOR = ENV("CC_SUPERVISOR", "http://supervisor")
PORT = int(ENV("CC_PORT", "8100"))
ALLOWED_NETS = [ipaddress.ip_network(n) for n in
                ENV("CC_ALLOWED_NETS", "172.30.32.0/23,127.0.0.0/8").split(",") if n]
VERSION = ENV("CC_VERSION", "dev")
CLI_DIR = Path(ENV("CC_CLI_DIR", str(DATA / "cli")))
IMAGE_CLAUDE = ENV("CC_IMAGE_CLAUDE", "/usr/lib/cc_agent_host/claude")
NPM_REGISTRY = ENV("CC_NPM_REGISTRY", "https://registry.npmjs.org")

API_TOKEN_FILE = DATA / "api_token"
JOB_TOKEN_FILE = DATA / "job_token"
AUDIT_LOG = DATA / "audit.log"
INTERACTIVE_CREDENTIALS = DATA / "claude" / ".credentials.json"
OPTIONS_FILE = DATA / "options.json"
USAGE_API_URL = ENV("CC_USAGE_API_URL", "https://api.anthropic.com/api/oauth/usage")
USAGE_API_TTL = 300

MAX_BODY = 64 * 1024
MAX_PROMPT = 16 * 1024
MAX_OUTPUT = 1024 * 1024
MAX_CONTEXT = 4 * 1024 * 1024
MAX_FETCH = 64 * 1024 * 1024  # Home Assistant API responses (all states incl. attributes can exceed 4 MB)
TIMEOUT_DEFAULT, TIMEOUT_MAX = 300, 1800
AUDIT_MAX, AUDIT_KEEP = 1024 * 1024, 3

PROFILE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
CONFIG_INCLUDE = ["*.yaml", "packages/**/*.yaml", "blueprints/**/*.yaml", "custom_templates/*.jinja"]
CONFIG_EXCLUDE = ["secrets.yaml", "**/secrets.yaml", ".storage/**", "*.pem", "*.key", ".git/**"]
SYSTEM_PROMPT = (
    "You run unattended as a job of a Home Assistant add-on. Nobody can answer questions. "
    "Context files for this job are in the current directory (see CONTEXT.md). "
    "Answer concisely; your final message is returned to the caller as the result."
)

job_lock = threading.Lock()
running = {"id": None, "profile": None, "since": None}


class JobError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


# --- profiles ---------------------------------------------------------------------------

def load_profiles():
    profiles = {}
    for f in sorted(PROFILES.glob("*.yaml")):
        name = f.stem
        if not PROFILE_NAME.match(name):
            continue
        try:
            p = yaml.safe_load(f.read_text()) or {}
            profiles[name] = normalize_profile(p)
        except (yaml.YAMLError, ValueError, TypeError) as e:
            print(f"profile {f.name} ignored: {e}", flush=True)
    return profiles


def normalize_profile(p):
    if not isinstance(p, dict):
        raise ValueError("profile must be a mapping")
    tools = p.get("tools", ["Read", "Grep", "Glob"])
    if not isinstance(tools, list) or not all(isinstance(t, str) and re.fullmatch(r"[A-Za-z]+", t) for t in tools):
        raise ValueError("tools must be a list of built-in tool names")
    context = p.get("context", [])
    if not isinstance(context, list):
        raise ValueError("context must be a list")
    ctx = []
    for c in context:
        name, opts = (c, {}) if isinstance(c, str) else next(iter(c.items()))
        if name not in CONTEXT_PROVIDERS:
            raise ValueError(f"unknown context provider {name}")
        ctx.append((name, opts or {}))
    budget = p.get("max_budget_usd")
    return {
        "description": str(p.get("description", "")),
        "model": str(p.get("model", "sonnet")),
        "max_turns": int(p.get("max_turns", 10)),
        "timeout": min(int(p.get("timeout", TIMEOUT_DEFAULT)), TIMEOUT_MAX),
        "max_budget_usd": float(budget) if budget is not None else None,
        "tools": tools,
        "context": ctx,
        "system_prompt": str(p.get("system_prompt", "")),
    }


# --- context providers ------------------------------------------------------------------

def supervisor_get(path, accept="application/json", headers=None):
    req = urllib.request.Request(SUPERVISOR + path, headers={
        "Authorization": "Bearer " + ENV("SUPERVISOR_TOKEN", ""), "Accept": accept, **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read(MAX_FETCH + 1)
    if len(body) > MAX_FETCH:
        raise RuntimeError(f"{path}: response larger than {MAX_FETCH} bytes")
    return body


def ctx_ha_log(job_dir, opts):
    """Raw core log; requires hassio_role homeassistant (not granted by default)."""
    lines = int(opts.get("lines", 2000))
    raw = supervisor_get("/core/logs", "text/plain", {"Range": f"entries=:-{lines}:"})
    text = re.sub(r"\x1b\[[0-9;]*m", "", raw.decode("utf-8", "replace"))
    (job_dir / "ha_log.txt").write_text(text)
    return f"ha_log.txt: last {lines} lines of the Home Assistant core log"


def ha_websocket(command):
    """One command over the Home Assistant websocket API (via the Supervisor proxy)."""
    import asyncio

    import aiohttp

    async def call():
        async with aiohttp.ClientSession() as session, session.ws_connect(
                SUPERVISOR.replace("http", "ws", 1) + "/core/websocket", max_msg_size=MAX_CONTEXT) as ws:
            await ws.receive_json()  # auth_required
            await ws.send_json({"type": "auth", "access_token": ENV("SUPERVISOR_TOKEN", "")})
            if (await ws.receive_json()).get("type") != "auth_ok":
                raise RuntimeError("websocket auth failed")
            await ws.send_json({"id": 1, **command})
            msg = await ws.receive_json()
            if not msg.get("success"):
                raise RuntimeError(f"websocket command failed: {msg.get('error')}")
            return msg["result"]

    return asyncio.run(asyncio.wait_for(call(), 30))


def ctx_ha_system_log(job_dir, opts):
    levels = opts.get("levels", ["ERROR", "CRITICAL", "WARNING"])
    entries = [e for e in ha_websocket({"type": "system_log/list"}) if e.get("level") in levels]
    (job_dir / "ha_system_log.json").write_text(json.dumps(entries, ensure_ascii=False, indent=1))
    return (f"ha_system_log.json: {len(entries)} deduplicated Home Assistant log entries ({', '.join(levels)}) "
            "with count, first_occurred and timestamp (last occurrence, Unix time), logger name, source, message")


def ctx_ha_states(job_dir, opts):
    states = json.loads(supervisor_get("/core/api/states"))
    domains = opts.get("domains")
    out = [{"entity_id": s["entity_id"], "state": s["state"], "last_changed": s.get("last_changed"),
            "name": s.get("attributes", {}).get("friendly_name")}
           for s in states if not domains or s["entity_id"].split(".")[0] in domains]
    (job_dir / "ha_states.json").write_text(json.dumps(out, ensure_ascii=False, indent=0))
    return f"ha_states.json: {len(out)} entity states (entity_id, state, last_changed, name)"


def ctx_ha_config(job_dir, opts):
    include = opts.get("include", CONFIG_INCLUDE)
    exclude = CONFIG_EXCLUDE + opts.get("exclude", [])
    target, total, count = job_dir / "ha_config", 0, 0
    for f in sorted(HA_CONFIG.rglob("*")):
        rel = f.relative_to(HA_CONFIG).as_posix()
        if not f.is_file() or f.is_symlink():
            continue
        if not any(fnmatch.fnmatch(rel, pat) for pat in include) or any(fnmatch.fnmatch(rel, pat) for pat in exclude):
            continue
        size = f.stat().st_size
        if total + size > MAX_CONTEXT:
            break
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, dest)
        total, count = total + size, count + 1
    return f"ha_config/: {count} Home Assistant configuration files (secrets and .storage excluded)"


HISTORY_DOMAINS = ["binary_sensor", "cover", "light", "media_player", "person", "climate", "vacuum",
                   "lawn_mower", "lock", "fan", "alarm_control_panel"]
HISTORY_SENSOR_CLASSES = ["temperature", "humidity", "power", "carbon_dioxide", "pm25", "illuminance"]
HISTORY_SKIP_BINARY = ["problem", "battery", "connectivity", "update", "safety", "running"]
HISTORY_STEPS = {"°C": 0.5, "°F": 1, "%": 1, "ppm": 25, "µg/m³": 5}
AREA_TEMPLATE = "{{ entities | map('area_name') | map('default', '', true) | list | tojson }}"


def supervisor_post(path, body):
    req = urllib.request.Request(SUPERVISOR + path, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": "Bearer " + ENV("SUPERVISOR_TOKEN", ""), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(MAX_FETCH)


def history_select(states, opts):
    """Entity ids for ha_history: domains, sensor device classes, include/exclude globs."""
    domains = opts.get("domains", HISTORY_DOMAINS)
    classes = opts.get("sensor_device_classes", HISTORY_SENSOR_CLASSES)
    skip_binary = opts.get("skip_binary_device_classes", HISTORY_SKIP_BINARY)
    include, exclude = opts.get("include", []), opts.get("exclude", [])
    out = []
    for s in states:
        e, attrs = s["entity_id"], s.get("attributes", {})
        domain, dc = e.split(".")[0], attrs.get("device_class")
        if any(fnmatch.fnmatch(e, p) for p in exclude):
            continue
        if (any(fnmatch.fnmatch(e, p) for p in include)
                or (domain in domains and not (domain == "binary_sensor" and dc in skip_binary))
                or (domain == "sensor" and dc in classes and attrs.get("unit_of_measurement"))):
            out.append(e)
    return out


def history_round(value, unit, steps):
    """Rounds noise away: fixed step per unit, otherwise two significant digits."""
    if unit in steps:
        return round(round(value / steps[unit]) * steps[unit], 2)
    return float(f"{value:.2g}") if value else 0.0


def history_debounce(points, min_duration):
    """Drops unavailable/unknown states that lasted less than min_duration seconds (connection
    glitches); real states are always kept, however short."""
    if min_duration <= 0:
        return points
    kept = [p for p, nxt in zip(points, points[1:], strict=False)
            if p[1] not in ("unavailable", "unknown") or (nxt[0] - p[0]).total_seconds() >= min_duration]
    return kept + points[-1:]


def history_lines(points, unit, bucket, steps, tz):
    """Compact timeline in local time. Without unit: every state change. With unit: numbers as
    min-max per bucket (labelled with its first change), listed when the text changes;
    non-numeric states (unavailable …) in between."""
    lines, prev, current = [], None, None  # current: [label time, bucket key, lo, hi]

    def emit(when, text):
        nonlocal prev
        if text != prev:
            lines.append(f"{when:%a %d.%m %H:%M} {text}")
            prev = text

    def flush():
        if current:
            when, _, lo, hi = current
            emit(when, f"{lo:g}" if lo == hi else f"{lo:g}-{hi:g}")

    for changed, state in points:
        t = changed.astimezone(tz)
        try:
            v = history_round(float(state), unit, steps) if unit else None
        except ValueError:
            v = None
        if v is None:
            flush()
            current = None
            emit(t, state)
            continue
        k = t.replace(minute=t.minute // bucket * bucket, second=0, microsecond=0)
        if current and current[1] == k:
            current = [current[0], k, min(current[2], v), max(current[3], v)]
        else:
            flush()
            current = [t, k, v, v]
    flush()
    return lines


def ctx_ha_history(job_dir, opts):
    """Recorder history of selected entities as compact per-area timelines (local time)."""
    from datetime import UTC, timedelta
    from urllib.parse import quote, urlencode
    from zoneinfo import ZoneInfo

    hours = min(float(opts.get("hours", 24)), 240)
    bucket = max(1, min(int(opts.get("bucket_minutes", 10)), 60))
    steps = {**HISTORY_STEPS, **opts.get("steps", {})}
    min_duration = float(opts.get("min_duration_s", 0))
    states = json.loads(supervisor_get("/core/api/states"))
    meta = {s["entity_id"]: s.get("attributes", {}) for s in states}
    selected = history_select(states, opts)
    tz = ZoneInfo(json.loads(supervisor_get("/core/api/config")).get("time_zone") or "UTC")
    areas = dict(zip(selected, json.loads(supervisor_post(
        "/core/api/template", {"template": AREA_TEMPLATE, "variables": {"entities": selected}})), strict=True))
    end = datetime.now(UTC)
    start = end - timedelta(hours=hours)
    per_area, count = {}, 0
    for i in range(0, len(selected), 50):
        query = urlencode({"filter_entity_id": ",".join(selected[i:i + 50]), "end_time": end.isoformat(),
                           "minimal_response": "", "no_attributes": "", "significant_changes_only": ""})
        for hist in json.loads(supervisor_get(f"/core/api/history/period/{quote(start.isoformat())}?{query}")):
            if not hist:
                continue
            e = hist[0]["entity_id"]
            attrs = meta.get(e, {})
            unit = attrs.get("unit_of_measurement") or ""
            points = history_debounce([(datetime.fromisoformat(h["last_changed"]), h["state"]) for h in hist],
                                      min_duration)
            lines = history_lines(points, unit, bucket, steps, tz)
            head = f"## {e} | {attrs.get('friendly_name') or ''}" + (f" | {unit}" if unit else "")
            per_area.setdefault(areas.get(e) or "", []).append((head, lines))
            count += 1
    target = job_dir / "ha_history"
    target.mkdir()
    index = [f"# History {start.astimezone(tz):%a %d.%m %H:%M} – {end.astimezone(tz):%a %d.%m %H:%M} ({tz})",
             "", f"One file per area. Numbers: min-max per {bucket} min, listed only when they change; "
             "other states: each change"
             + (f" (unavailable/unknown only if longer than {min_duration:g} s)" if min_duration else "")
             + ". First line of each entity = state at the start.", ""]
    total = 0
    for area in sorted(per_area, key=lambda a: (a == "", a)):
        name = re.sub(r"[^a-z0-9]+", "_", area.lower().translate(str.maketrans("äöüß", "aous"))).strip("_")
        name = name or "no_area"
        text = "\n\n".join(h + "\n" + "\n".join(lines) for h, lines in per_area[area]) + "\n"
        if total + len(text) > MAX_CONTEXT:
            index.append(f"- (truncated: further areas left out, context limit {MAX_CONTEXT} bytes)")
            break
        (target / f"{name}.txt").write_text(text)
        total += len(text)
        index.append(f"- {name}.txt: {area or 'no area'} – " + ", ".join(
            f"{h.split(' | ')[0][3:]} ({len(lines)})" for h, lines in per_area[area]))
    (target / "INDEX.md").write_text("\n".join(index) + "\n")
    return (f"ha_history/: recorder history of {count} entities over the last {hours:g} h, one file per area, "
            "overview with line counts in ha_history/INDEX.md")


CONTEXT_PROVIDERS = {"ha_log": ctx_ha_log, "ha_system_log": ctx_ha_system_log,
                     "ha_states": ctx_ha_states, "ha_config": ctx_ha_config, "ha_history": ctx_ha_history}


# --- jobs -------------------------------------------------------------------------------

def read_secret(path):
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return ""


def build_command(profile):
    cmd = [CLAUDE, "-p", "--output-format", "json",
           "--model", profile["model"], "--max-turns", str(profile["max_turns"]),
           "--tools", ",".join(profile["tools"]),
           "--permission-mode", "dontAsk", "--permission-prompts", "none",
           "--strict-mcp-config", "--no-session-persistence", "--setting-sources", "",
           "--append-system-prompt", (SYSTEM_PROMPT + " " + profile["system_prompt"]).strip()]
    if profile["max_budget_usd"] is not None:
        cmd += ["--max-budget-usd", str(profile["max_budget_usd"])]
    if RUN_AS:
        cmd = [shutil.which("su-exec") or "/sbin/su-exec", RUN_AS] + cmd
    return cmd


def job_env(token):
    return {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
            "HOME": str(AGENT_HOME / "home"), "CLAUDE_CONFIG_DIR": str(AGENT_HOME / "claude"),
            "CLAUDE_CODE_OAUTH_TOKEN": token, "DISABLE_AUTOUPDATER": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}


def run_job(profile_name, prompt, timeout=None):
    profiles = load_profiles()
    if profile_name not in profiles:
        raise JobError(404, f"unknown profile {profile_name!r}")
    profile = profiles[profile_name]
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT:
        raise JobError(400, f"prompt must be 1..{MAX_PROMPT} characters")
    timeout = min(int(timeout or profile["timeout"]), profile["timeout"])
    token = read_secret(JOB_TOKEN_FILE)
    if not token:
        raise JobError(503, "no job token: run 'claude setup-token' and 'cc-job-token' in the terminal")
    if not job_lock.acquire(blocking=False):
        raise JobError(429, "another job is running")

    job_id = uuid.uuid4().hex[:12]
    job_dir = JOBS / job_id
    started = time.monotonic()
    audit = {"id": job_id, "profile": profile_name, "prompt_len": len(prompt),
             "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
    running.update(id=job_id, profile=profile_name, since=time.time())
    try:
        job_dir.mkdir(parents=True, mode=0o700)
        notes = [CONTEXT_PROVIDERS[name](job_dir, opts) for name, opts in profile["context"]]
        (job_dir / "CONTEXT.md").write_text("# Context files\n\n" + "\n".join(f"- {n}" for n in notes) + "\n")
        if RUN_AS:
            user = RUN_AS.split(":")[0]
            subprocess.run(["chown", "-R", RUN_AS, str(job_dir)], check=True)
            audit["user"] = user
        out, timed_out, rc = execute(build_command(profile), job_dir, prompt, token, timeout)
        result = parse_result(out, rc, timed_out)
        audit.update(exit=rc, timed_out=timed_out, is_error=result["is_error"], turns=result.get("num_turns"),
                     cost_usd=result.get("cost_usd"), denials=result.get("permission_denials"),
                     result_len=len(result.get("result") or ""))
        return {"job_id": job_id, **result}
    except JobError:
        raise
    except Exception as e:  # context fetch failures etc.
        audit["error"] = f"{type(e).__name__}: {e}"
        raise JobError(500, audit["error"]) from e
    finally:
        audit["duration_s"] = round(time.monotonic() - started, 1)
        write_audit(audit)
        shutil.rmtree(job_dir, ignore_errors=True)
        running.update(id=None, profile=None, since=None)
        job_lock.release()


def execute(cmd, cwd, prompt, token, timeout):
    proc = subprocess.Popen(cmd, cwd=cwd, env=job_env(token), stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
    buf, timed_out = bytearray(), False

    def reader():
        while chunk := proc.stdout.read(65536):
            if len(buf) < MAX_OUTPUT:
                buf.extend(chunk[:MAX_OUTPUT - len(buf)])

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        proc.stdin.write(prompt.encode())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    t.join(5)
    return bytes(buf), timed_out, proc.returncode


def parse_result(out, rc, timed_out):
    if timed_out:
        return {"ok": False, "is_error": True, "error": "timeout", "result": None}
    try:
        d = json.loads(out)
    except ValueError:
        return {"ok": False, "is_error": True, "error": f"claude exited with {rc}, no JSON result", "result": None}
    denials = [x.get("tool_name") for x in d.get("permission_denials") or []]
    is_error = bool(d.get("is_error")) or rc != 0
    return {"ok": not is_error, "is_error": is_error, "result": d.get("result"),
            "error": d.get("terminal_reason") if is_error else None,
            "num_turns": d.get("num_turns"), "duration_s": round((d.get("duration_ms") or 0) / 1000, 1),
            "cost_usd": d.get("total_cost_usd"), "permission_denials": denials}


def write_audit(entry):
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **entry}
    try:
        if AUDIT_LOG.exists() and AUDIT_LOG.stat().st_size > AUDIT_MAX:
            for i in range(AUDIT_KEEP - 1, 0, -1):  # audit.log.1 -> .2, audit.log -> .1
                src = AUDIT_LOG if i == 1 else AUDIT_LOG.with_name(f"audit.log.{i - 1}")
                if src.exists():
                    src.rename(AUDIT_LOG.with_name(f"audit.log.{i}"))
        with AUDIT_LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        os.chmod(AUDIT_LOG, 0o600)
    except OSError as e:
        print(f"audit log: {e}", flush=True)


# --- HTTP -------------------------------------------------------------------------------

def api_token():
    token = read_secret(API_TOKEN_FILE)
    if not token:
        token = secrets.token_urlsafe(32)
        API_TOKEN_FILE.write_text(token)
        os.chmod(API_TOKEN_FILE, 0o600)
    return token


PLAN_MULTIPLIERS = {"pro": 1, "max_5x": 5, "max_20x": 20}  # usage relative to Pro (Anthropic's plan names)
_plan_cache = {"at": 0.0, "data": None}


def plan():
    """Plan of the interactive sign-in.

    The subscription type comes from `claude auth status` (official CLI). Max 5x and Max 20x can only be
    told apart by the rate limit tier stored with the sign-in, which is read (that field only) when the
    opt-in usage API is enabled; otherwise a Max plan is reported as "max" without multiplier.
    """
    if _plan_cache["data"] and time.time() - _plan_cache["at"] < 600:
        return _plan_cache["data"]
    subscription, tier = None, None
    try:
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": ENV("HOME", "/data/home"),
               "CLAUDE_CONFIG_DIR": str(DATA / "claude"), "DISABLE_AUTOUPDATER": "1", "LANG": "C.UTF-8"}
        out = subprocess.run([CLAUDE, "auth", "status", "--json"], env=env, capture_output=True, text=True,
                             timeout=30, cwd="/tmp").stdout
        subscription = json.loads(out).get("subscriptionType")
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    if option("usage_api", False):
        try:
            tier = json.loads(INTERACTIVE_CREDENTIALS.read_text())["claudeAiOauth"].get("rateLimitTier")
        except (OSError, ValueError, KeyError):
            pass
    name = subscription or "unknown"
    if subscription == "max" and tier:
        name = "max_20x" if "20x" in tier else "max_5x" if "5x" in tier else "max"
    data = {"plan": name, "subscription": subscription, "tier": tier, "multiplier": PLAN_MULTIPLIERS.get(name)}
    if subscription:
        _plan_cache.update(at=time.time(), data=data)
    return data


def status():
    return {"version": VERSION, "claude_version": claude_version(), "plan": plan(),
            "signed_in": INTERACTIVE_CREDENTIALS.exists(), "job_token": bool(read_secret(JOB_TOKEN_FILE)),
            "running": running["id"] is not None, "running_profile": running["profile"],
            "profiles": sorted(load_profiles()), "claude_image_version": image_claude_version(), **cli_status()}


_claude_version = None


@functools.cache
def image_claude_version():
    try:
        return subprocess.run([IMAGE_CLAUDE, "--version"], capture_output=True, text=True,
                              timeout=20).stdout.split()[0]
    except (OSError, IndexError, subprocess.SubprocessError):
        return None


def claude_version():
    global _claude_version
    if _claude_version is None:
        try:
            _claude_version = subprocess.run([CLAUDE, "--version"], capture_output=True, text=True,
                                             timeout=20).stdout.split()[0]
        except (OSError, IndexError, subprocess.SubprocessError):
            _claude_version = "unknown"
    return _claude_version


# --- Claude Code updates ------------------------------------------------------------------
# The image pins a checksum-verified Claude Code version. Newer versions are offered to Home Assistant
# (update entity of the integration) and installed only on request, from the official npm package with
# the registry's sha512 integrity, into /data/cli/<version>; /usr/local/bin/claude prefers /data/cli/current.

CLI_CHECK_TTL = 6 * 3600
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_cli = {"latest": None, "checked_at": 0.0, "checking": False, "updating": False, "error": None}
_cli_lock = threading.Lock()


def version_key(v):
    return tuple(int(x) for x in v.split(".")) if v and VERSION_RE.match(v) else (0,)


def npm_package():
    arch = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "x64", "amd64": "x64"}.get(platform.machine())
    if arch is None:
        raise JobError(500, f"unsupported architecture {platform.machine()}")
    return f"@anthropic-ai/claude-code-linux-{arch}-musl"


def npm_manifest(version):
    with urllib.request.urlopen(f"{NPM_REGISTRY}/{npm_package()}/{version}", timeout=30) as r:
        return json.loads(r.read())


def check_latest():
    """Latest Claude Code version from npm, refreshed in the background at most every 6 hours."""
    with _cli_lock:
        if _cli["checking"] or time.time() - _cli["checked_at"] < CLI_CHECK_TTL:
            return
        _cli["checking"] = True

    def run():
        try:
            latest = npm_manifest("latest").get("version")
            if VERSION_RE.match(latest or ""):
                _cli["latest"] = latest
            _cli["checked_at"] = time.time()
        except (OSError, ValueError, JobError) as e:
            print(f"Claude Code version check failed: {e}", flush=True)
            _cli["checked_at"] = time.time() - CLI_CHECK_TTL + 600  # retry in 10 minutes
        finally:
            _cli["checking"] = False

    threading.Thread(target=run, daemon=True).start()


def cli_status():
    check_latest()
    return {"claude_latest": _cli["latest"], "claude_updating": _cli["updating"],
            "claude_update_error": _cli["error"]}


def install_cli(version=None):
    global _claude_version
    if not job_lock.acquire(blocking=False):
        raise JobError(429, "a job is running, try again when it has finished")
    _cli.update(updating=True, error=None)
    tmp = None
    try:
        manifest = npm_manifest(version or "latest")
        version = manifest.get("version", "")
        tarball, integrity = manifest["dist"]["tarball"], manifest["dist"].get("integrity", "")
        if not VERSION_RE.match(version) or not integrity.startswith("sha512-") \
                or not tarball.startswith(f"{NPM_REGISTRY}/{npm_package()}/-/"):
            raise JobError(502, "unexpected package data from npm")
        CLI_DIR.mkdir(mode=0o755, exist_ok=True)
        os.chmod(CLI_DIR, 0o755)  # noqa: S103 - the job user cc_agent runs this binary too
        tmp = CLI_DIR / f".tmp-{uuid.uuid4().hex[:8]}"
        tmp.mkdir(mode=0o755)
        digest = hashlib.sha512()
        with urllib.request.urlopen(tarball, timeout=60) as r, open(tmp / "package.tgz", "wb") as f:
            while chunk := r.read(1024 * 1024):
                digest.update(chunk)
                f.write(chunk)
        if not hmac.compare_digest(base64.b64encode(digest.digest()).decode(), integrity[7:]):
            raise JobError(502, "checksum mismatch, nothing installed")
        with tarfile.open(tmp / "package.tgz") as t, open(tmp / "claude", "wb") as out:
            member = t.getmember("package/claude")
            if not member.isfile():
                raise JobError(502, "package/claude missing")
            shutil.copyfileobj(t.extractfile(member), out)
        os.chmod(tmp / "claude", 0o755)  # noqa: S103 - executable for the job user, owned by root
        reported = subprocess.run([str(tmp / "claude"), "--version"], capture_output=True, text=True,
                                  timeout=60, env={"PATH": "/usr/bin:/bin", "HOME": str(tmp),
                                                   "DISABLE_AUTOUPDATER": "1"}).stdout
        if not reported.startswith(version):
            raise JobError(502, f"downloaded binary reports {reported.strip()!r}, expected {version}")
        (tmp / "package.tgz").unlink()
        target = CLI_DIR / version
        shutil.rmtree(target, ignore_errors=True)
        tmp.rename(target)
        tmp = None
        previous = os.readlink(CLI_DIR / "current") if (CLI_DIR / "current").is_symlink() else None
        link = CLI_DIR / ".current-new"
        link.unlink(missing_ok=True)
        link.symlink_to(version)
        link.replace(CLI_DIR / "current")
        for old in CLI_DIR.iterdir():  # keep the new and the previous version
            if old.is_dir() and not old.is_symlink() and old.name not in (version, previous):
                shutil.rmtree(old, ignore_errors=True)
        _claude_version = None
        _cli["error"] = None
        restart_remote_control()
        print(f"Claude Code {version} installed", flush=True)
        return {"version": version, "remote_control_restarted": True,
                "note": "the web terminal session uses the new version after its next start"}
    except JobError as e:
        _cli["error"] = str(e)
        raise
    except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.SubprocessError) as e:
        _cli["error"] = f"{type(e).__name__}: {e}"
        raise JobError(502, _cli["error"]) from e
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
        _cli["updating"] = False
        job_lock.release()


def restart_remote_control():
    """The Remote Control service starts again by itself (with the new version) when its tmux session ends."""
    subprocess.run(["tmux", "kill-session", "-t", "rc"], capture_output=True, timeout=10)


def option(name, default=None):
    try:
        return json.loads(OPTIONS_FILE.read_text()).get(name, default)
    except (FileNotFoundError, ValueError):
        return default


def usage():
    if option("usage_api", False):
        return usage_api()
    return usage_statusline()


def usage_statusline():
    try:
        d = json.loads(USAGE_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return {"source": "statusline", "available": False}
    return {"source": "statusline", "available": True, **d}


# --- opt-in: usage API (option "usage_api") ------------------------------------------------
# Reads the access token of the interactive sign-in to query Anthropic's (undocumented) plan usage
# endpoint, which also reports usage credits. The token is only sent to api.anthropic.com and never
# leaves the add-on otherwise; refreshing is left to Claude Code itself (a tiny prompt).

_usage_cache = {"at": 0.0, "data": None, "refresh_at": 0.0}
_usage_lock = threading.Lock()


def interactive_token():
    cred = json.loads(INTERACTIVE_CREDENTIALS.read_text())["claudeAiOauth"]
    return cred["accessToken"], cred.get("expiresAt", 0) / 1000


def refresh_interactive_login():
    """Let Claude Code refresh its own token with a minimal prompt (rate-limited)."""
    if time.time() - _usage_cache["refresh_at"] < 600:
        return
    _usage_cache["refresh_at"] = time.time()
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": ENV("HOME", "/data/home"),
           "CLAUDE_CONFIG_DIR": str(DATA / "claude"), "DISABLE_AUTOUPDATER": "1", "LANG": "C.UTF-8"}
    subprocess.run([CLAUDE, "-p", "ok", "--model", "haiku", "--max-turns", "1", "--tools", "",
                    "--no-session-persistence"], env=env, cwd="/tmp", capture_output=True, timeout=120)


def usage_api():
    with _usage_lock:
        if _usage_cache["data"] and time.time() - _usage_cache["at"] < USAGE_API_TTL:
            return _usage_cache["data"]
        try:
            token, expires = interactive_token()
            if expires - time.time() < 900:
                refresh_interactive_login()
                token, expires = interactive_token()
            req = urllib.request.Request(USAGE_API_URL, headers={
                "Authorization": "Bearer " + token, "anthropic-beta": "oauth-2025-04-20",
                "User-Agent": "cc-agent-host"})
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = json.loads(r.read())
            data = {"source": "api", "available": True, **parse_usage_api(raw)}
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
            data = {"source": "api", "available": False, "error": type(e).__name__}
            if _usage_cache["data"]:  # keep the last good values, flagged as stale
                data = {**_usage_cache["data"], "stale": True, "error": type(e).__name__}
            return data
        _usage_cache.update(at=time.time(), data=data)
        return data


def parse_usage_api(raw):
    def epoch(s):
        try:
            return int(datetime.fromisoformat(s).timestamp())
        except (TypeError, ValueError):
            return None

    limits = {}
    for key in ("five_hour", "seven_day"):
        v = raw.get(key) or {}
        if v.get("utilization") is not None:
            limits[key] = {"used_percentage": v["utilization"], "resets_at": epoch(v.get("resets_at"))}
    credits = [{"key": k, "used": v.get("used_dollars"), "limit": v.get("limit_dollars"),
                "remaining": v.get("remaining_dollars"), "used_percentage": v.get("utilization"),
                "resets_at": epoch(v.get("resets_at"))}
               for k, v in raw.items() if isinstance(v, dict) and v.get("limit_dollars") is not None]
    breakdown = {r["key"]: r.get("percent") for r in (raw.get("seven_day_breakdown") or {}).get("rows") or []}
    return {"updated_at": int(time.time()), "rate_limits": limits, "credits": credits,
            "weekly_breakdown": breakdown}


class Handler(BaseHTTPRequestHandler):
    server_version = "cc-agent-host"
    token = None

    def log_message(self, *args):
        pass

    def reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        try:
            ip = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return False
        if not any(ip in n for n in ALLOWED_NETS):
            self.reply(403, {"error": "forbidden"})
            return False
        auth = self.headers.get("Authorization", "")
        if not (auth.startswith("Bearer ") and hmac.compare_digest(auth[7:].encode(), self.token.encode())):
            self.reply(401, {"error": "unauthorized"})
            return False
        return True

    def do_GET(self):
        if not self.authorized():
            return
        if self.path == "/status":
            self.reply(200, status())
        elif self.path == "/profiles":
            self.reply(200, {n: {"description": p["description"], "model": p["model"], "tools": p["tools"],
                                 "context": [c for c, _ in p["context"]]} for n, p in load_profiles().items()})
        elif self.path == "/usage":
            self.reply(200, usage())
        else:
            self.reply(404, {"error": "not found"})

    def do_POST(self):
        if not self.authorized():
            return
        if self.path not in ("/run", "/cli/update"):
            return self.reply(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self.reply(413, {"error": "body too large"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self.reply(400, {"error": "invalid JSON"})
        try:
            if self.path == "/cli/update":
                version = body.get("version")
                if version is not None and not VERSION_RE.match(str(version)):
                    raise JobError(400, "version must look like 2.1.291")
                return self.reply(200, install_cli(version))
            self.reply(200, run_job(str(body.get("profile", "")), body.get("prompt"), body.get("timeout")))
        except JobError as e:
            self.reply(e.status, {"error": str(e)})


def announce(token):
    """Publish address and token to Home Assistant (Supervisor discovery) for the integration."""
    if not ENV("SUPERVISOR_TOKEN"):
        return
    body = json.dumps({"service": "cc_agent_host", "config": {
        "host": ENV("HOSTNAME", "local-cc-agent-host"), "port": PORT, "api_key": token}}).encode()
    req = urllib.request.Request(SUPERVISOR + "/discovery", data=body, method="POST", headers={
        "Authorization": "Bearer " + ENV("SUPERVISOR_TOKEN", ""), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15):
            print("announced to Home Assistant (discovery)", flush=True)
    except OSError as e:
        print(f"discovery failed: {e}", flush=True)


def main():
    JOBS.mkdir(parents=True, exist_ok=True)
    os.chmod(JOBS, 0o711)  # noqa: S103 - traverse only; job dirs themselves are 700
    Handler.token = api_token()
    announce(Handler.token)
    # internal add-on network only (no published port); IP guard and bearer token apply
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)  # noqa: S104
    print(f"job API listening on :{PORT}, profiles: {', '.join(sorted(load_profiles())) or '-'}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

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
"""
import fnmatch
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import threading
import time
import urllib.request
import uuid
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

API_TOKEN_FILE = DATA / "api_token"
JOB_TOKEN_FILE = DATA / "job_token"
AUDIT_LOG = DATA / "audit.log"
INTERACTIVE_CREDENTIALS = DATA / "claude" / ".credentials.json"

MAX_BODY = 64 * 1024
MAX_PROMPT = 16 * 1024
MAX_OUTPUT = 1024 * 1024
MAX_CONTEXT = 4 * 1024 * 1024
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
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(MAX_CONTEXT)


def ctx_ha_log(job_dir, opts):
    lines = int(opts.get("lines", 2000))
    raw = supervisor_get("/core/logs", "text/plain", {"Range": f"entries=:-{lines}:"})
    text = re.sub(r"\x1b\[[0-9;]*m", "", raw.decode("utf-8", "replace"))
    (job_dir / "ha_log.txt").write_text(text)
    return f"ha_log.txt: last {lines} lines of the Home Assistant core log"


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


CONTEXT_PROVIDERS = {"ha_log": ctx_ha_log, "ha_states": ctx_ha_states, "ha_config": ctx_ha_config}


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


def status():
    return {"version": VERSION, "claude_version": claude_version(),
            "signed_in": INTERACTIVE_CREDENTIALS.exists(), "job_token": bool(read_secret(JOB_TOKEN_FILE)),
            "running": running["id"] is not None, "running_profile": running["profile"],
            "profiles": sorted(load_profiles())}


_claude_version = None


def claude_version():
    global _claude_version
    if _claude_version is None:
        try:
            _claude_version = subprocess.run([CLAUDE, "--version"], capture_output=True, text=True,
                                             timeout=20).stdout.split()[0]
        except (OSError, IndexError, subprocess.SubprocessError):
            _claude_version = "unknown"
    return _claude_version


def usage():
    try:
        d = json.loads(USAGE_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return {"source": "statusline", "available": False}
    return {"source": "statusline", "available": True, **d}


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
        if self.path != "/run":
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

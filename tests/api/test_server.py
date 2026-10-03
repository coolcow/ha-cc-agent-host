import json
import os
import threading

import pytest


def result_of(resp):
    return json.loads(resp["result"])


def test_auth_required(http):
    assert http("GET", "/status", token=None)[0] == 401
    assert http("GET", "/status", token="wrong")[0] == 401
    assert http("GET", "/status")[0] == 200


def test_ip_guard(env, http, monkeypatch):
    import ipaddress
    env["server"].ALLOWED_NETS[:] = [ipaddress.ip_network("172.30.32.0/23")]
    assert http("GET", "/status")[0] == 403


def test_api_token_file_private(env, http):
    f = env["data"] / "api_token"
    assert f.exists() and oct(f.stat().st_mode & 0o777) == "0o600"


def test_status_and_profiles(http):
    code, st = http("GET", "/status")
    assert code == 200 and st["job_token"] is True and st["profiles"] == ["read"] and st["running"] is False
    code, pr = http("GET", "/profiles")
    assert pr["read"]["tools"] == ["Read", "Grep"]


def test_run_ok_and_command_flags(env, http):
    code, r = http("POST", "/run", {"profile": "read", "prompt": "hallo"})
    assert code == 200 and r["ok"] and r["cost_usd"] == 0.01 and r["permission_denials"] == ["Bash"]
    inner = result_of(r)
    assert inner["prompt"] == "hallo"
    argv = inner["argv"]
    for flag in ("-p", "--strict-mcp-config", "--no-session-persistence"):
        assert flag in argv
    assert argv[argv.index("--tools") + 1] == "Read,Grep"
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert argv[argv.index("--permission-prompts") + 1] == "none"
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert "CONTEXT.md" in inner["files"]


def test_job_env_is_minimal(http):
    env_names = result_of(http("POST", "/run", {"profile": "read", "prompt": "x"})[1])["env"]
    assert "SUPERVISOR_TOKEN" not in env_names and "CLAUDE_CODE_OAUTH_TOKEN" in env_names
    assert set(env_names) <= {"PATH", "LANG", "HOME", "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN",
                              "DISABLE_AUTOUPDATER", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
                              "PWD", "SHLVL", "_", "OLDPWD", "LC_CTYPE"}


def test_job_dir_removed_and_audited(env, http):
    http("POST", "/run", {"profile": "read", "prompt": "x"})
    assert list(env["jobs"].iterdir()) == []
    entry = json.loads((env["data"] / "audit.log").read_text().splitlines()[-1])
    assert entry["profile"] == "read" and entry["prompt_len"] == 1 and "prompt" not in entry
    assert oct((env["data"] / "audit.log").stat().st_mode & 0o777) == "0o600"


@pytest.mark.parametrize("body,code", [
    ({"profile": "nope", "prompt": "x"}, 404),
    ({"profile": "read", "prompt": ""}, 400),
    ({"profile": "read", "prompt": "x" * 20000}, 400),
    ({"profile": "read"}, 400),
])
def test_validation(http, body, code):
    assert http("POST", "/run", body)[0] == code


def test_no_job_token(env, http):
    (env["data"] / "job_token").unlink()
    assert http("POST", "/run", {"profile": "read", "prompt": "x"})[0] == 503


def test_busy(env, http):
    env["mode"].write_text("sleep")
    t = threading.Thread(target=http, args=("POST", "/run", {"profile": "read", "prompt": "x", "timeout": 2}))
    t.start()
    import time
    time.sleep(0.5)
    assert http("POST", "/run", {"profile": "read", "prompt": "y"})[0] == 429
    t.join()


def test_timeout_kills_job(env, http):
    env["mode"].write_text("sleep")
    code, r = http("POST", "/run", {"profile": "read", "prompt": "x", "timeout": 1})
    assert code == 200 and r["ok"] is False and r["error"] == "timeout"


def test_timeout_capped_by_profile(env, http):
    env["mode"].write_text("sleep")
    import time
    t0 = time.monotonic()
    http("POST", "/run", {"profile": "read", "prompt": "x", "timeout": 999})
    assert time.monotonic() - t0 < 10  # profile timeout is 5 s


@pytest.mark.parametrize("mode,error", [("garbage", "no JSON result"), ("error", "api_error")])
def test_errors(env, http, mode, error):
    env["mode"].write_text(mode)
    code, r = http("POST", "/run", {"profile": "read", "prompt": "x"})
    assert code == 200 and r["ok"] is False and error in r["error"]


def test_ha_config_context_excludes_secrets(env, http):
    ha = env["ha"]
    (ha / "configuration.yaml").write_text("a: 1")
    (ha / "secrets.yaml").write_text("pw: geheim")
    (ha / "packages").mkdir()
    (ha / "packages" / "x.yaml").write_text("b: 2")
    (ha / "packages" / "secrets.yaml").write_text("pw: geheim")
    (ha / ".storage").mkdir()
    (ha / ".storage" / "core.config_entries").write_text("{}")
    (ha / "key.pem").write_text("k")
    (ha / "extra.yaml").write_text("c: 3")
    (env["profiles"] / "cfg.yaml").write_text(
        "tools: [Read]\ncontext:\n  - ha_config:\n      exclude: [extra.yaml]\n")
    code, r = http("POST", "/run", {"profile": "cfg", "prompt": "x"})
    assert code == 200 and "ha_config" in result_of(r)["files"]
    seen = []
    job = env["tmp"] / "probe"
    job.mkdir()
    env["server"].ctx_ha_config(job, {"exclude": ["extra.yaml"]})
    for root, _, files in os.walk(job / "ha_config"):
        seen += [os.path.relpath(os.path.join(root, f), job / "ha_config") for f in files]
    assert sorted(seen) == ["configuration.yaml", "packages/x.yaml"]


def test_invalid_profiles_ignored(env, http):
    (env["profiles"] / "bad.yaml").write_text("tools: [Read; rm -rf]\n")
    (env["profiles"] / "Bad Name.yaml").write_text("tools: [Read]\n")
    (env["profiles"] / "ctx.yaml").write_text("context: [unknown]\n")
    assert http("GET", "/status")[1]["profiles"] == ["read"]


def test_usage(env, http):
    assert http("GET", "/usage")[1]["available"] is False
    (env["tmp"] / "usage.json").write_text(json.dumps({"updated_at": 1, "rate_limits": {"five_hour": {}}}))
    assert http("GET", "/usage")[1]["available"] is True


def test_system_log_context(env, http, monkeypatch):
    entries = [{"level": "ERROR", "count": 3, "message": ["boom"]}, {"level": "INFO", "count": 1, "message": ["x"]}]
    monkeypatch.setattr(env["server"], "ha_websocket", lambda cmd: entries)
    (env["profiles"] / "log.yaml").write_text("context:\n  - ha_system_log:\n      levels: [ERROR]\n")
    code, r = http("POST", "/run", {"profile": "log", "prompt": "x"})
    assert code == 200 and "ha_system_log.json" in result_of(r)["files"]
    job = env["tmp"] / "probe2"
    job.mkdir()
    env["server"].ctx_ha_system_log(job, {"levels": ["ERROR"]})
    assert json.loads((job / "ha_system_log.json").read_text()) == entries[:1]


def test_context_failure_reported(env, http, monkeypatch):
    def broken(cmd):
        raise RuntimeError("websocket auth failed")
    monkeypatch.setattr(env["server"], "ha_websocket", broken)
    (env["profiles"] / "log.yaml").write_text("context: [ha_system_log]\n")
    code, r = http("POST", "/run", {"profile": "log", "prompt": "x"})
    assert code == 500 and "websocket auth failed" in r["error"]
    assert list(env["jobs"].iterdir()) == []


HISTORY_STATES = [
    {"entity_id": "sensor.bad_feuchte", "state": "70", "attributes": {
        "device_class": "humidity", "unit_of_measurement": "%", "friendly_name": "Bad Feuchte"}},
    {"entity_id": "light.bad", "state": "on", "attributes": {"friendly_name": "Bad Licht"}},
    {"entity_id": "binary_sensor.batterie", "state": "off", "attributes": {"device_class": "battery"}},
    {"entity_id": "sensor.cpu", "state": "3", "attributes": {"unit_of_measurement": "%"}},
    {"entity_id": "switch.tor", "state": "off", "attributes": {}},
    {"entity_id": "light.privat", "state": "off", "attributes": {}},
]


def test_history_select(env):
    sel = env["server"].history_select(HISTORY_STATES, {"include": ["switch.tor"], "exclude": ["*privat*"]})
    assert sel == ["sensor.bad_feuchte", "light.bad", "switch.tor"]


def history_points(*pairs):
    from datetime import UTC, datetime
    return [(datetime(2026, 10, 3, h, m, s, tzinfo=UTC), v) for (h, m, s), v in pairs]


def test_history_lines_numbers(env):
    from zoneinfo import ZoneInfo
    pts = history_points(((7, 0, 0), "55.2"), ((7, 3, 0), "61.6"), ((7, 8, 0), "64"),
                         ((7, 12, 0), "64.4"), ((7, 25, 0), "unavailable"), ((7, 26, 0), "63"))
    lines = env["server"].history_lines(pts, "%", 10, env["server"].HISTORY_STEPS, ZoneInfo("Europe/Paris"))
    assert lines == ["Sat 03.10 09:00 55-64", "Sat 03.10 09:12 64", "Sat 03.10 09:25 unavailable",
                     "Sat 03.10 09:26 63"]


def test_history_lines_states_and_debounce(env):
    from zoneinfo import ZoneInfo
    srv = env["server"]
    pts = history_points(((6, 0, 0), "off"), ((6, 30, 0), "unavailable"), ((6, 30, 5), "off"),
                         ((6, 40, 0), "on"), ((6, 45, 0), "on"), ((7, 0, 0), "off"))
    lines = srv.history_lines(srv.history_debounce(pts, 60), "", 10, {}, ZoneInfo("UTC"))
    assert lines == ["Sat 03.10 06:00 off", "Sat 03.10 06:40 on", "Sat 03.10 07:00 off"]
    assert srv.history_round(3068.1, "W", {}) == 3100 and srv.history_round(21.3, "°C", srv.HISTORY_STEPS) == 21.5


def test_history_context(env, monkeypatch):
    srv = env["server"]
    hist = [[{"entity_id": "sensor.bad_feuchte", "state": "55", "last_changed": "2026-10-03T07:00:00+00:00"},
             {"state": "68", "last_changed": "2026-10-03T07:05:00+00:00"}],
            [{"entity_id": "light.bad", "state": "off", "last_changed": "2026-10-03T07:00:00+00:00"}]]
    for h in hist:  # minimal_response: entity_id only in the first entry
        for later in h[1:]:
            later["entity_id"] = h[0]["entity_id"]
    calls = []

    def get(path, *a, **k):
        calls.append(path)
        if path == "/core/api/states":
            return json.dumps(HISTORY_STATES).encode()
        if path == "/core/api/config":
            return b'{"time_zone": "Europe/Paris"}'
        return json.dumps(hist).encode()
    monkeypatch.setattr(srv, "supervisor_get", get)
    monkeypatch.setattr(srv, "supervisor_post", lambda path, body: json.dumps(
        ["Badezimmer" if e != "switch.tor" else "" for e in body["variables"]["entities"]]).encode())
    job = env["tmp"] / "probe3"
    job.mkdir()
    note = srv.ctx_ha_history(job, {"hours": 24, "include": ["switch.tor"]})
    assert "2 entities" in note
    assert "filter_entity_id=sensor.bad_feuchte%2Clight.bad%2Cswitch.tor" in calls[-1]
    text = (job / "ha_history" / "badezimmer.txt").read_text()
    assert "## sensor.bad_feuchte | Bad Feuchte | %\nSat 03.10 09:00 55-68" in text
    assert "badezimmer.txt: Badezimmer" in (job / "ha_history" / "INDEX.md").read_text()


def usage_api_env(env, monkeypatch, expires_in=3600, status=200):
    import threading as th
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    calls = []

    class Fake(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            calls.append(self.headers.get("Authorization"))
            body = json.dumps({
                "five_hour": {"utilization": 27.0, "resets_at": "2026-10-02T11:20:00.706150+00:00"},
                "seven_day": {"utilization": 4.0, "resets_at": "2026-10-08T20:00:00+00:00"},
                "iguana_necktie": {"utilization": 12.1, "resets_at": "2026-11-05T07:59:00+00:00",
                                   "limit_dollars": 250, "used_dollars": 30.27, "remaining_dollars": 219.73},
                "extra_usage": {"is_enabled": False},
                "seven_day_breakdown": {"rows": [{"key": "claude_code", "percent": 50}]}}).encode()
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    th.Thread(target=srv.serve_forever, daemon=True).start()
    s = env["server"]
    monkeypatch.setattr(s, "USAGE_API_URL", f"http://127.0.0.1:{srv.server_address[1]}/usage")
    monkeypatch.setattr(s, "INTERACTIVE_CREDENTIALS", env["data"] / "credentials.json")
    import time
    (env["data"] / "credentials.json").write_text(json.dumps(
        {"claudeAiOauth": {"accessToken": "tok", "expiresAt": (time.time() + expires_in) * 1000}}))
    (env["data"] / "options.json").write_text(json.dumps({"usage_api": True}))
    s._usage_cache.update(at=0.0, data=None, refresh_at=0.0)
    return calls


def test_usage_api_off_by_default(env, http):
    assert http("GET", "/usage")[1]["source"] == "statusline"


def test_usage_api(env, http, monkeypatch):
    calls = usage_api_env(env, monkeypatch)
    u = http("GET", "/usage")[1]
    assert u["source"] == "api" and u["available"] is True
    assert u["rate_limits"]["five_hour"] == {"used_percentage": 27.0, "resets_at": 1790940000}
    assert u["credits"] == [{"key": "iguana_necktie", "used": 30.27, "limit": 250, "remaining": 219.73,
                             "used_percentage": 12.1, "resets_at": 1793865540}]
    assert u["weekly_breakdown"] == {"claude_code": 50}
    http("GET", "/usage")
    assert calls == ["Bearer tok"]  # cached for 5 minutes


def test_usage_api_refreshes_expiring_token(env, http, monkeypatch):
    usage_api_env(env, monkeypatch, expires_in=60)
    refreshed = []
    monkeypatch.setattr(env["server"], "refresh_interactive_login", lambda: refreshed.append(1))
    http("GET", "/usage")
    assert refreshed == [1]


def test_usage_api_error_keeps_stale_values(env, http, monkeypatch):
    usage_api_env(env, monkeypatch)
    http("GET", "/usage")
    env["server"]._usage_cache["at"] = 0.0
    (env["data"] / "credentials.json").write_text("{}")
    u = http("GET", "/usage")[1]
    assert u["stale"] is True and u["rate_limits"]["five_hour"]["used_percentage"] == 27.0


def test_plan_without_usage_api(env, http):
    p = http("GET", "/status")[1]["plan"]
    assert p == {"plan": "max", "subscription": "max", "tier": None, "multiplier": None}


@pytest.mark.parametrize(("tier", "plan", "mult"), [("default_claude_max_5x", "max_5x", 5),
                                                    ("default_claude_max_20x", "max_20x", 20)])
def test_plan_with_usage_api(env, http, monkeypatch, tier, plan, mult):
    usage_api_env(env, monkeypatch)
    cred = json.loads((env["data"] / "credentials.json").read_text())
    cred["claudeAiOauth"]["rateLimitTier"] = tier
    (env["data"] / "credentials.json").write_text(json.dumps(cred))
    env["server"]._plan_cache.update(at=0.0, data=None)
    p = http("GET", "/status")[1]["plan"]
    assert p["plan"] == plan and p["multiplier"] == mult

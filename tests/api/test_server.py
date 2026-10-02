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

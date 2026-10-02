import importlib
import json
import socket
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[2] / "cc_agent_host/rootfs/usr/lib/cc_agent_host"

FAKE_CLAUDE = """#!/bin/sh
# Fake claude: echoes its arguments and stdin as the JSON result; behaviour via FAKE_MODE file
mode=$(cat "@MODE@" 2>/dev/null)
if [ "$1" = auth ]; then echo '{"loggedIn": true, "subscriptionType": "max"}'; exit 0; fi
prompt=$(cat)
case "$mode" in
  sleep) sleep 30 ;;
  garbage) echo "not json"; exit 1 ;;
  error) printf '{"is_error":true,"terminal_reason":"api_error","result":null}'; exit 1 ;;
esac
python3 - "$prompt" "$@" <<'PY'
import json, os, sys
print(json.dumps({"result": json.dumps({"prompt": sys.argv[1], "argv": sys.argv[2:], "cwd": os.getcwd(),
                  "files": sorted(os.listdir(".")), "env": sorted(os.environ)}),
                  "is_error": False, "num_turns": 1, "duration_ms": 1200, "total_cost_usd": 0.01,
                  "permission_denials": [{"tool_name": "Bash"}]}))
PY
"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def env(tmp_path, monkeypatch):
    data, ha, profiles, jobs = (tmp_path / d for d in ("data", "ha", "profiles", "jobs"))
    for d in (data, ha, profiles, jobs):
        d.mkdir()
    fake = tmp_path / "claude"
    mode = tmp_path / "mode"
    fake.write_text(FAKE_CLAUDE.replace("@MODE@", str(mode)))
    fake.chmod(0o755)
    vals = {"CC_DATA": data, "CC_HA_CONFIG": ha, "CC_PROFILES": profiles, "CC_JOBS": jobs,
            "CC_CLAUDE": fake, "CC_RUN_AS": "", "CC_AGENT_HOME": tmp_path / "agent",
            "CC_USAGE_FILE": tmp_path / "usage.json",
            "CC_ALLOWED_NETS": "127.0.0.0/8"}
    for k, v in vals.items():
        monkeypatch.setenv(k, str(v))
    (data / "job_token").write_text("sk-ant-oat-test")
    (profiles / "read.yaml").write_text("description: test\ntools: [Read, Grep]\ntimeout: 5\n")
    sys.path.insert(0, str(SERVER_DIR))
    server = importlib.reload(importlib.import_module("server"))
    sys.path.remove(str(SERVER_DIR))
    return {"server": server, "tmp": tmp_path, "data": data, "ha": ha, "profiles": profiles,
            "jobs": jobs, "mode": mode}


@pytest.fixture
def http(env):
    srv = env["server"]
    srv.Handler.token = srv.api_token()
    port = free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    import urllib.request

    def call(method, path, body=None, token=srv.Handler.token):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {token}"} if token else {})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    yield call
    httpd.shutdown()

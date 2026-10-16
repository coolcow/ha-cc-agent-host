"""cc-ha, the Home Assistant helper of the interactive session, against a fake Supervisor proxy."""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

CC_HA = Path(__file__).resolve().parents[2] / "cc_agent_host/rootfs/usr/local/bin/cc-ha"
STATES = [
    {"entity_id": "light.kitchen", "state": "on", "attributes": {"friendly_name": "Kitchen"}},
    {"entity_id": "sensor.temp", "state": "21.5", "attributes": {}},
    {"entity_id": "light.hall", "state": "off", "attributes": {"friendly_name": "Hall"}},
]


@pytest.fixture
def supervisor():
    """Fake Supervisor proxy: records requests, answers /core/api/... from `responses`."""
    state = {"requests": [], "check": {"result": "valid", "errors": None}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def answer(self, body):
            state["requests"].append((self.command, self.path, self.headers.get("Authorization")))
            if self.path == "/core/api/states":
                payload = STATES
            elif self.path == "/core/api/config/core/check_config":
                payload = state["check"]
            elif self.path.startswith("/core/api/services/"):
                payload = []
            else:
                self.send_response(404)
                self.end_headers()
                return
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.answer(None)

        def do_POST(self):
            self.answer(self.rfile.read(int(self.headers.get("Content-Length") or 0)))

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()


def run(supervisor, *args, auth="tok"):
    env = {**os.environ, "CC_SUPERVISOR": supervisor["url"], "CC_TOKEN_FILE": "/nonexistent"}
    env.pop("SUPERVISOR_TOKEN", None)
    if auth:
        env["SUPERVISOR_TOKEN"] = auth
    return subprocess.run([sys.executable, str(CC_HA), *args], env=env, capture_output=True, text=True,
                          timeout=30)


def posts(supervisor):
    return [p for m, p, _ in supervisor["requests"] if m == "POST"]


def test_check_valid(supervisor):
    r = run(supervisor, "check")
    assert r.returncode == 0 and "valid" in r.stdout
    assert supervisor["requests"] == [("POST", "/core/api/config/core/check_config", "Bearer tok")]


def test_check_invalid(supervisor):
    supervisor["check"] = {"result": "invalid", "errors": "Integration error: foo"}
    r = run(supervisor, "check")
    assert r.returncode == 1 and "Integration error: foo" in r.stdout


def test_reload_domains_after_check(supervisor):
    r = run(supervisor, "reload", "automation", "script")
    assert r.returncode == 0
    assert posts(supervisor) == ["/core/api/config/core/check_config", "/core/api/services/automation/reload",
                                 "/core/api/services/script/reload"]


def test_reload_all(supervisor):
    assert run(supervisor, "reload").returncode == 0
    assert posts(supervisor)[-1] == "/core/api/services/homeassistant/reload_all"


@pytest.mark.parametrize("cmd", ["reload", "restart"])
def test_invalid_configuration_blocks_reload_and_restart(supervisor, cmd):
    supervisor["check"] = {"result": "invalid", "errors": "bad"}
    r = run(supervisor, cmd)
    assert r.returncode == 1
    assert posts(supervisor) == ["/core/api/config/core/check_config"]


def test_restart(supervisor):
    assert run(supervisor, "restart").returncode == 0
    assert posts(supervisor)[-1] == "/core/api/services/homeassistant/restart"


def test_states_filtered_and_sorted(supervisor):
    r = run(supervisor, "states", "light.*")
    assert r.stdout.splitlines() == ["light.hall\toff\tHall", "light.kitchen\ton\tKitchen"]
    assert len(run(supervisor, "states").stdout.splitlines()) == 3


def test_without_token(supervisor):
    r = run(supervisor, "check", auth=None)
    assert r.returncode != 0 and "no Supervisor token" in r.stderr
    assert supervisor["requests"] == []


def test_unknown_command_prints_usage(supervisor):
    r = run(supervisor, "frobnicate")
    assert r.returncode == 2 and "cc-ha check" in r.stdout


def test_log(monkeypatch, capsys):
    loader = importlib.machinery.SourceFileLoader("cc_ha", str(CC_HA))
    spec = importlib.util.spec_from_loader("cc_ha", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    entries = [
        {"level": "WARNING", "name": "homeassistant.components.foo", "message": ["slow"], "timestamp": 2,
         "count": 3, "source": ["components/foo/__init__.py", 10]},
        {"level": "INFO", "name": "x", "message": ["ignored"], "timestamp": 1},
        {"level": "ERROR", "name": "custom_components.bar", "message": ["boom"], "timestamp": 1,
         "exception": "Traceback\n  line"},
    ]
    monkeypatch.setattr(mod, "websocket", lambda cmd: entries)
    assert mod.main(["log"]) == 0
    out = capsys.readouterr().out
    assert out.index("custom_components.bar") < out.index("homeassistant.components.foo")
    assert "ignored" not in out and "(3x) components/foo/__init__.py:10" in out and "    Traceback" in out
    assert mod.main(["log", "info"]) == 0
    assert "ignored" in capsys.readouterr().out

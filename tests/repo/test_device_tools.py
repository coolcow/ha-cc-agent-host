"""tools/deploy.sh and tools/smoke-device.sh against a fake SSH host (no real device involved).

The fake `ssh` logs every remote command, answers the read-only version queries and runs the smoke
test's remote script locally with fake `ha` and `curl` (real `jq`).
"""

import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ADDON_VERSION = yaml.safe_load((ROOT / "cc_agent_host/config.yaml").read_text())["version"]

pytestmark = pytest.mark.skipif(not shutil.which("jq"), reason="jq not installed")

FAKE_SSH = r"""#!/bin/bash
# Stateful fake device: uploads are unpacked, install/update/rebuild take over the uploaded version.
host="$1"; shift
if [[ $1 == bash && $2 == -s ]]; then echo "SMOKE $host" >> "$FAKE_LOG"; shift 2; exec bash -s "$@"; fi
cmd="$*"
addon_version() { cat "$FAKE_DIR/addon_version" 2>/dev/null || echo "${FAKE_ADDON:-}"; }
case "$cmd" in
  *"ha apps info"*) echo "READ $cmd" >> "$FAKE_LOG"; addon_version ;;
  *"jq -r"*"manifest.json"*) echo "READ $cmd" >> "$FAKE_LOG"
      jq -r '.version // empty' "$SMOKE_HA_CONFIG/custom_components/cc_agent_host/manifest.json" 2>/dev/null ;;
  *)
    n=$(ls "$FAKE_DIR" | grep -c '^stdin' || true); cat > "$FAKE_DIR/stdin-$n"
    echo "WRITE $cmd" >> "$FAKE_LOG"
    case "$cmd" in
      *"mv /tmp/cc_agent_host.deploy/payload /local_apps/cc_agent_host"*)
        rm -rf "$FAKE_DIR/upload"; mkdir -p "$FAKE_DIR/upload"; tar -xf "$FAKE_DIR/stdin-$n" -C "$FAKE_DIR/upload" ;;
      *"mv /tmp/cc_agent_host.deploy/payload /homeassistant/custom_components/cc_agent_host"*)
        d="$SMOKE_HA_CONFIG/custom_components"; rm -rf "$d/cc_agent_host"; mkdir -p "$d"
        tar -xf "$FAKE_DIR/stdin-$n" -C "$d" && mv "$d/payload" "$d/cc_agent_host" ;;
      *"ha apps "*)
        grep -oP '^version: "\K[0-9.]+' "$FAKE_DIR/upload/payload/config.yaml" > "$FAKE_DIR/addon_version" ;;
    esac ;;
esac
"""

FAKE_HA = r"""#!/bin/bash
case "$1 $2" in
  "apps info") v=$(cat "$FAKE_DIR/addon_version" 2>/dev/null || echo "${FAKE_ADDON:-}"); [[ -n $v ]] || exit 1
               printf '{"result":"ok","data":{"version":"%s","state":"%s","ip_address":"172.30.33.5"}}' \
                      "$v" "${FAKE_STATE:-started}" ;;
  "apps logs") echo "INFO all good" ;;
esac
"""

FAKE_CURL = r"""#!/bin/bash
# FAKE_SV_DENIED=1: the SSH app's Supervisor role may not read /discovery or the core API (HTTP 403)
url="${@: -1}"
wcode=0; [[ " $* " == *" -w "* ]] && wcode=1
disc='{"service":"cc_agent_host","config":{"host":"h","port":8100,"api_key":"k"}}'
ent='{"entity_id":"sensor.cc_agent_host_plan","state":"max"},{"entity_id":"light.x","state":"on"}'
deny() { if (( wcode )); then printf 403; exit 0; fi; exit 22; }
case "$url" in
  */discovery) [[ -n ${FAKE_SV_DENIED:-} ]] && deny; echo "{\"data\":{\"discovery\":[$disc]}}" ;;
  http://172.30.33.5:8100/status) if (( wcode )); then printf "${FAKE_LIVENESS:-401}"; else exit 22; fi ;;
  */status) v=$(cat "$FAKE_DIR/addon_version" 2>/dev/null || echo "${FAKE_ADDON:-}")
            printf '{"version":"%s","signed_in":true,"job_token":false,"profiles":["read"]}' \
                   "${FAKE_API_VERSION:-$v}" ;;
  */core/api/states) [[ -n ${FAKE_SV_DENIED:-} ]] && deny; echo "[$ent]" ;;
  *) exit 7 ;;
esac
"""


def write_exe(path, text):
    path.write_text(text)
    path.chmod(0o755)


@pytest.fixture
def repo(tmp_path):
    """Copy of the working tree (tracked + untracked, not ignored) as a fresh git repo, check stubbed."""
    dst = tmp_path / "repo"
    files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, check=True,
                           capture_output=True, text=True).stdout.split("\n")
    for f in filter(None, files):
        if (ROOT / f).is_file():
            (dst / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / f, dst / f)
    write_exe(dst / "scripts/agent/check", "#!/bin/bash\necho '✓ stub check'\nexit ${FAKE_CHECK_RC:-0}\n")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "init", "-q"], cwd=dst, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dst, check=True)
    subprocess.run([*git, "commit", "-qm", "snapshot"], cwd=dst, check=True)
    return dst


@pytest.fixture
def fake(tmp_path):
    bin_dir, state = tmp_path / "bin", tmp_path / "state"
    bin_dir.mkdir()
    state.mkdir()
    write_exe(bin_dir / "ssh", FAKE_SSH)
    write_exe(bin_dir / "ha", FAKE_HA)
    write_exe(bin_dir / "curl", FAKE_CURL)
    config = tmp_path / "haconfig/custom_components/cc_agent_host"
    config.mkdir(parents=True)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_LOG": str(state / "log"),
           "FAKE_DIR": str(state), "SMOKE_HA_CONFIG": str(tmp_path / "haconfig"),
           "SUPERVISOR_TOKEN": "t", "DEPLOY_SSH": "ssh"}
    env.pop("FAKE_ADDON", None)

    class Fake:
        def run(self, repo, *args, **extra):
            return subprocess.run([str(repo / args[0]), *args[1:]], cwd=repo, env={**env, **extra},
                                  capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)

        def log(self):
            p = state / "log"
            return p.read_text().splitlines() if p.exists() else []

        def writes(self):
            return [line for line in self.log() if line.startswith("WRITE")]

        def stdin(self, n):
            return state / f"stdin-{n}"

        def install_integration(self, version):
            (config / "manifest.json").write_text(f'{{"version": "{version}"}}')

    return Fake()


def older(version):
    major, minor, patch = map(int, version.split("."))
    return f"{major}.{minor}.{patch - 1}" if patch else f"{major}.{minor - 1}.99"


# ---- deploy guards ----------------------------------------------------------------------------------

def test_deploy_requires_host(repo, fake):
    r = fake.run(repo, "tools/deploy.sh")
    assert r.returncode == 64 and fake.log() == []


def test_deploy_refuses_dirty_tree(repo, fake):
    (repo / "cc_agent_host/DOCS.md").write_text("changed")
    r = fake.run(repo, "tools/deploy.sh", "ha.local")
    assert r.returncode == 1 and "not clean" in r.stderr and fake.log() == []


def test_deploy_refuses_failed_check(repo, fake):
    r = fake.run(repo, "tools/deploy.sh", "ha.local", FAKE_CHECK_RC="1")
    assert r.returncode == 1 and "check failed" in r.stderr and fake.log() == []


def test_deploy_refuses_same_version(repo, fake):
    r = fake.run(repo, "tools/deploy.sh", "ha.local", "addon", FAKE_ADDON=ADDON_VERSION)
    assert r.returncode == 1 and "not newer" in r.stderr
    assert fake.writes() == []


def test_deploy_never_downgrades(repo, fake):
    r = fake.run(repo, "tools/deploy.sh", "ha.local", "addon", "--redeploy", FAKE_ADDON="99.0.0")
    assert r.returncode == 1 and "not newer" in r.stderr
    assert fake.writes() == []


def test_deploy_dry_run_changes_nothing(repo, fake):
    r = fake.run(repo, "tools/deploy.sh", "ha.local", "--dry-run", FAKE_ADDON=older(ADDON_VERSION))
    assert r.returncode == 0, r.stderr
    assert fake.writes() == [] and not any(line.startswith("SMOKE") for line in fake.log())
    assert "ha apps update local_cc_agent_host" in r.stdout and "dry run" in r.stdout


# ---- deploy against the fake host -------------------------------------------------------------------

def test_deploy_addon_update(repo, fake):
    r = fake.run(repo, "tools/deploy.sh", "ha.local", "addon", FAKE_ADDON=older(ADDON_VERSION))
    assert r.returncode == 0, r.stdout + r.stderr
    writes = fake.writes()
    assert len(writes) == 2
    assert "tar -xf - -C /tmp/cc_agent_host.deploy" in writes[0] and "mv /tmp/cc_agent_host.deploy/payload " \
        "/local_apps/cc_agent_host" in writes[0]
    assert writes[1] == "WRITE ha store reload && ha apps update local_cc_agent_host"
    with tarfile.open(fake.stdin(0)) as tar:
        names = tar.getnames()
        assert "payload/config.yaml" in names and "payload/Dockerfile" in names
        assert all(m.uname == "root" and not m.mode & 0o022 for m in tar.getmembers())
    assert "SMOKE ha.local" in fake.log() and f"ok   add-on version {ADDON_VERSION}" in r.stdout
    assert "Home Assistant must be restarted" not in r.stdout


def test_deploy_addon_first_install_and_redeploy(repo, fake):
    r = fake.run(repo, "tools/deploy.sh", "ha.local", "addon")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "WRITE ha store reload && ha apps install local_cc_agent_host" in fake.writes()
    assert f"ok   add-on version {ADDON_VERSION}" in r.stdout
    r = fake.run(repo, "tools/deploy.sh", "ha.local", "addon", "--redeploy", FAKE_ADDON=ADDON_VERSION)
    assert r.returncode == 0, r.stdout + r.stderr
    assert fake.writes()[-1] == "WRITE ha store reload && ha apps rebuild local_cc_agent_host"


def test_deploy_integration_never_restarts(repo, fake):
    fake.install_integration("0.0.1")
    r = fake.run(repo, "tools/deploy.sh", "ha.local", "integration", FAKE_ADDON=ADDON_VERSION)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"ok   integration version {manifest_version()}" in r.stdout
    writes = fake.writes()
    assert len(writes) == 1 and "/homeassistant/custom_components/cc_agent_host" in writes[0]
    assert not any("restart" in w for w in writes)
    assert "Home Assistant must be restarted" in r.stdout
    with tarfile.open(fake.stdin(0)) as tar:
        assert "payload/manifest.json" in tar.getnames()


# ---- smoke test -------------------------------------------------------------------------------------

def manifest_version():
    import json
    return json.loads((ROOT / "custom_components/cc_agent_host/manifest.json").read_text())["version"]


def test_smoke_all_ok(repo, fake):
    fake.install_integration(manifest_version())
    r = fake.run(repo, "tools/smoke-device.sh", "ha.local", FAKE_ADDON=ADDON_VERSION)
    assert r.returncode == 0, r.stdout
    assert "FAIL" not in r.stdout and r.stdout.count("\nok ") >= 6
    assert "k" not in [w for line in r.stdout.splitlines() for w in line.split()]  # api key not printed


def test_smoke_reports_mismatches(repo, fake):
    fake.install_integration("0.0.1")
    r = fake.run(repo, "tools/smoke-device.sh", "ha.local", FAKE_ADDON="0.0.1", FAKE_STATE="stopped",
                 FAKE_API_VERSION="0.0.1")
    assert r.returncode == 1
    for text in ("FAIL add-on version 0.0.1", "FAIL add-on state stopped", "FAIL integration version 0.0.1",
                 "FAIL job API reports version 0.0.1"):
        assert text in r.stdout


def test_smoke_without_supervisor_token_skips_api(repo, fake):
    fake.install_integration(manifest_version())
    r = fake.run(repo, "tools/smoke-device.sh", "ha.local", FAKE_ADDON=ADDON_VERSION, SUPERVISOR_TOKEN="")
    assert r.returncode == 0, r.stdout
    assert "ok   job API on 172.30.33.5:8100 answers" in r.stdout  # liveness needs no token
    assert "skip sensors: Home Assistant API not readable from this SSH session (no SUPERVISOR_TOKEN)" in r.stdout


def test_smoke_without_supervisor_access_checks_liveness(repo, fake):
    """The owner's SSH app may not read /discovery or the core API: job API liveness via the add-on IP."""
    fake.install_integration(manifest_version())
    r = fake.run(repo, "tools/smoke-device.sh", "ha.local", FAKE_ADDON=ADDON_VERSION, FAKE_SV_DENIED="1")
    assert r.returncode == 0, r.stdout
    assert "ok   job API on 172.30.33.5:8100 answers (HTTP 401" in r.stdout
    assert "skip sensors: Home Assistant API not readable from this SSH session (HTTP 403)" in r.stdout


def test_smoke_liveness_failure(repo, fake):
    fake.install_integration(manifest_version())
    r = fake.run(repo, "tools/smoke-device.sh", "ha.local", FAKE_ADDON=ADDON_VERSION, FAKE_SV_DENIED="1",
                 FAKE_LIVENESS="000")
    assert r.returncode == 1
    assert "FAIL job API on 172.30.33.5:8100 not answering as expected (HTTP 000)" in r.stdout

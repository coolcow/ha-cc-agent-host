# Shared helpers for scripts/agent/*. Source, do not execute.
# Contract: full output goes to .agent-logs/<step>-<timestamp>.log, stdout gets one line per step on
# success or a capped failure digest plus the log path, the exit code is passed through.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$ROOT/.agent-logs"
MAX_LINES="${AGENT_MAX_LINES:-150}"
mkdir -p "$LOG_DIR"

export CI="${CI:-1}" NO_COLOR=1 PY_COLORS=0 PIP_DISABLE_PIP_VERSION_CHECK=1

# Pinned tool images (same in CI and locally)
SHELLCHECK_IMAGE=koalaman/shellcheck:v0.10.0
HADOLINT_IMAGE=hadolint/hadolint:v2.12.0
YAMLLINT_IMAGE=cytopia/yamllint:1.26
ACTIONLINT_IMAGE=rhysd/actionlint:1.7.7
INTEGRATION_IMAGE=python:3.14-slim

# Python for the fast checks: repo venv (scripts/setup) if present, else python3 on PATH (CI).
if [[ -x "$ROOT/.venv/bin/python" ]]; then PY="$ROOT/.venv/bin/python"; else PY="$(command -v python3)"; fi

log_file() { echo "$LOG_DIR/$1-$(date +%Y%m%d-%H%M%S).log"; }
now_s() { date +%s; }

# cap <digest> <log>: at most MAX_LINES lines of the digest, then the path of the full log.
cap() {
    local digest="$1" log="$2" n
    n=$(wc -l < "$digest")
    head -n "$MAX_LINES" "$digest"
    if (( n > MAX_LINES )); then echo "… $((n - MAX_LINES)) more lines truncated (AGENT_MAX_LINES=$MAX_LINES)"; fi
    echo "full log: ${log#"$ROOT/"}"
}

need_python_deps() {
    if ! "$PY" -c "import pytest, yaml" 2>/dev/null; then
        echo "✗ python deps missing for $PY – run scripts/setup" >&2
        return 2
    fi
}

need_docker() {
    if ! docker info >/dev/null 2>&1; then
        echo "✗ $1 needs docker, which is not available" >&2
        return 2
    fi
}

# Extra `docker run` arguments when this machine reaches the internet through a local HTTPS proxy
# with its own CA (e.g. sandboxed agent sessions): host network, proxy and CA bundle passed through.
docker_proxy_args() {
    DOCKER_PROXY_ARGS=()
    local proxy="${HTTPS_PROXY:-${https_proxy:-}}" ca="${PIP_CERT:-${SSL_CERT_FILE:-${REQUESTS_CA_BUNDLE:-}}}"
    [[ -n $proxy ]] || return 0
    DOCKER_PROXY_ARGS+=(--network host -e "HTTPS_PROXY=$proxy" -e "NO_PROXY=${NO_PROXY:-${no_proxy:-}}")
    if [[ -n $ca && -f $ca ]]; then
        DOCKER_PROXY_ARGS+=(-v "$ca:/etc/agent-ca.crt:ro" -e PIP_CERT=/etc/agent-ca.crt -e SSL_CERT_FILE=/etc/agent-ca.crt)
    fi
}

# Shell scripts to lint: every file with a bash/sh/bashio shebang in the tracked source directories.
shell_scripts() {
    (cd "$ROOT" && grep -rlIE --exclude-dir=__pycache__ --exclude-dir=.venv '^#!.*(bash|/sh|bashio)' \
        cc_agent_host tools tests scripts .claude .devcontainer 2>/dev/null | sort)
}

# ---- steps -----------------------------------------------------------------
# Each step_* prints its own summary and returns the tool's exit code.

# step_lint: shellcheck, hadolint, yamllint, actionlint (docker, pinned images) and ruff (.venv).
step_lint() {
    need_python_deps || return $?
    need_docker lint || return $?
    local log t0 rc=0 r tool scripts; log=$(log_file lint); t0=$(now_s)
    mapfile -t scripts < <(shell_scripts)
    : > "$log.digest"
    run_tool() {  # run_tool <name> <command...>: output to the log, and to the digest on failure
        local out
        out=$(cd "$ROOT" && "${@:2}" 2>&1); r=$?
        printf '== %s (exit %s)\n%s\n' "$1" "$r" "$out" >> "$log"
        if (( r != 0 )); then printf '%s\n' "$out" | sed "s/^/[$1] /" >> "$log.digest"; rc=$r; fi
    }
    local mnt=(docker run --rm -v "$ROOT:/mnt" -w /mnt)
    run_tool shellcheck "${mnt[@]}" "$SHELLCHECK_IMAGE" -x -s bash -f gcc "${scripts[@]}"
    run_tool hadolint "${mnt[@]}" "$HADOLINT_IMAGE" hadolint --ignore DL3018 cc_agent_host/Dockerfile
    run_tool yamllint "${mnt[@]}" "$YAMLLINT_IMAGE" -c .yamllint --strict -f parsable .
    run_tool actionlint "${mnt[@]}" "$ACTIONLINT_IMAGE" -no-color -oneline
    run_tool ruff "$PY" -m ruff check --no-cache --output-format concise .
    if (( rc == 0 )); then
        echo "✓ lint (shellcheck ${#scripts[@]} scripts, hadolint, yamllint, actionlint, ruff) clean in $(( $(now_s) - t0 ))s"
        rm -f "$log.digest"; return 0
    fi
    echo "✗ lint failed:"
    cap "$log.digest" "$log"; rm -f "$log.digest"; return $rc
}

# pytest_digest <name> <log> <rc> <t0> <args...>: shared summary/digest for pytest runs.
pytest_digest() {
    local name="$1" log="$2" rc="$3" t0="$4" summary; shift 4
    summary=$(grep -E '[0-9]+ (passed|failed|errors?|skipped|deselected).* in [0-9.]+s|no tests ran' "$log" | tail -1 | sed -E 's/=+//g; s/^ +| +$//g')
    if (( rc == 0 )); then echo "✓ $name: ${summary:-ok} ($(( $(now_s) - t0 ))s)"; return 0; fi
    if (( rc == 5 )); then echo "✗ $name: no tests collected for: $* (exit 5)"; return "$rc"; fi
    echo "✗ $name failed (exit $rc): ${summary:-see log}"
    awk '/^=+ (FAILURES|ERRORS) =+$/{p=1} p' "$log" | grep -vE '^=+ (warnings summary|short test summary)' > "$log.digest"
    [[ -s "$log.digest" ]] || tail -n 40 "$log" > "$log.digest"
    cap "$log.digest" "$log"; rm -f "$log.digest"; return "$rc"
}

PYTEST_OPTS=(-q --tb=short --no-header -rfE --show-capture=no -p no:warnings -p no:cacheprovider)

# step_pytest <name> [pytest args...]: fast suites (tests/api, tests/repo) with the .venv / CI python.
step_pytest() {
    local name="$1"; shift
    need_python_deps || return $?
    local log t0 rc; log=$(log_file "$name"); t0=$(now_s)
    (cd "$ROOT" && "$PY" -m pytest "${PYTEST_OPTS[@]}" "$@") > "$log" 2>&1; rc=$?
    pytest_digest "$name" "$log" "$rc" "$t0" "$@"
}

# with_suite <dir> [args...]: prints args with <dir> prepended unless a tests/ selector is given
with_suite() {
    local dir="$1" a; shift
    for a in "$@"; do [[ $a == tests/* ]] && { printf '%s\n' "$@"; return; }; done
    printf '%s\n' "$dir" "$@"
}
step_api() { local a; mapfile -t a < <(with_suite tests/api "$@"); step_pytest api "${a[@]}"; }
step_repo() { local a; mapfile -t a < <(with_suite tests/repo "$@"); step_pytest repo "${a[@]}"; }

# step_integration [pytest args...]: Home Assistant tests (Python 3.14). Uses python3 directly when it
# already has the test harness (CI after `pip install`), otherwise a python:3.14 container.
step_integration() {
    local args log t0 rc
    mapfile -t args < <(with_suite tests/integration "$@")
    local opts=("${PYTEST_OPTS[@]}" -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function)
    log=$(log_file integration); t0=$(now_s)
    if python3 -c 'import sys, pytest_homeassistant_custom_component; sys.exit(sys.version_info < (3, 14))' 2>/dev/null; then
        (cd "$ROOT" && python3 -m pytest "${opts[@]}" "${args[@]}") > "$log" 2>&1; rc=$?
    else
        need_docker "integration tests (no local Python 3.14 with the test harness)" || return $?
        docker_proxy_args
        docker run --rm "${DOCKER_PROXY_ARGS[@]}" -v "$ROOT:/src" -v cc-agent-host-pip:/root/.cache/pip -w /src \
            "$INTEGRATION_IMAGE" sh -c '
                pip install -q --root-user-action=ignore -r tests/integration/requirements.txt || exit 3
                exec python -m pytest "$@"' -- "${opts[@]}" "${args[@]}" > "$log" 2>&1; rc=$?
        if (( rc == 3 )); then echo "✗ integration: pip install failed"; tail -n 20 "$log" > "$log.digest"; cap "$log.digest" "$log"; rm -f "$log.digest"; return 3; fi
    fi
    pytest_digest integration "$log" "$rc" "$t0" "${args[@]}"
}

# step_image: build the add-on image for the local architecture, then image and isolation tests.
# IMAGE=<tag> skips the build and tests an existing image.
step_image() {
    need_docker "image tests" || return $?
    local log t0 rc image="${IMAGE:-}"; log=$(log_file image); t0=$(now_s)
    if [[ -z $image ]]; then
        image=cc-agent-host:check
        (cd "$ROOT" && docker build --progress=plain -t "$image" cc_agent_host) > "$log" 2>&1; rc=$?
        if (( rc != 0 )); then
            echo "✗ image: docker build failed (exit $rc)"
            grep -E 'ERROR|error:|failed|FAILED|denied|not found' "$log" | tail -n 30 > "$log.digest"
            [[ -s "$log.digest" ]] || tail -n 30 "$log" > "$log.digest"
            cap "$log.digest" "$log"; rm -f "$log.digest"; return $rc
        fi
    fi
    local t r out
    rc=0
    for t in test_image test_isolation; do
        out=$(cd "$ROOT" && "tests/addon/$t.sh" "$image" 2>&1); r=$?
        printf '== %s (exit %s)\n%s\n' "$t" "$r" "$out" >> "$log"
        if (( r != 0 )); then printf '%s\n' "$out" | grep -E '^FAIL|rror' | sed "s/^/[$t] /" >> "$log.digest"; rc=$r; fi
    done
    if (( rc == 0 )); then
        echo "✓ image: build + $(grep -c '^ok ' "$log") checks passed ($(( $(now_s) - t0 ))s)"; return 0
    fi
    echo "✗ image tests failed:"
    [[ -s "$log.digest" ]] || tail -n 30 "$log" > "$log.digest"
    cap "$log.digest" "$log"; rm -f "$log.digest"; return $rc
}

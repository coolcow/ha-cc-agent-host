#!/usr/bin/env bash
# PostToolUse (Edit|Write|MultiEdit): lint only the edited file, with the same pinned tools as
# scripts/agent/check lint. Python → ruff (.venv), shell → shellcheck, YAML → yamllint (+ actionlint for
# workflows), Dockerfile → hadolint; docker images run when the tool is not installed locally.
# Silent on success or when a tool is unavailable; on findings exit 2 so the message reaches Claude.
input=$(cat)
path=$(printf '%s' "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("tool_input") or {}).get("file_path") or "")' 2>/dev/null)
[[ -n $path && -f $path ]] || exit 0
root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
rel="${path#"$root"/}"
[[ $rel == /* ]] && exit 0  # outside the repository

have_docker() { docker info >/dev/null 2>&1; }
in_docker() { docker run --rm -v "$root:/mnt" -w /mnt "$@"; }

out="" rc=0
case "$rel" in
    *.py)
        ruff="$root/.venv/bin/ruff"; [[ -x $ruff ]] || ruff=$(command -v ruff) || exit 0
        out=$(cd "$root" && NO_COLOR=1 "$ruff" check --no-cache --quiet --output-format concise "$rel" 2>&1); rc=$? ;;
    *.yaml|*.yml)
        if command -v yamllint >/dev/null; then out=$(cd "$root" && yamllint -c .yamllint --strict -f parsable "$rel" 2>&1); rc=$?
        elif have_docker; then out=$(in_docker cytopia/yamllint:1.26 -c .yamllint --strict -f parsable "$rel" 2>&1); rc=$?
        else exit 0; fi
        if (( rc == 0 )) && [[ $rel == .github/workflows/* ]] && have_docker; then
            out=$(in_docker rhysd/actionlint:1.7.7 -no-color -oneline "$rel" 2>&1); rc=$?
        fi ;;
    */Dockerfile|Dockerfile)
        have_docker || exit 0
        out=$(in_docker hadolint/hadolint:v2.12.0 hadolint --ignore DL3018 "$rel" 2>&1); rc=$? ;;
    *)
        if [[ $rel == *.sh ]] || head -n1 "$path" 2>/dev/null | grep -qE '^#!.*(bash|/sh|bashio)'; then
            if command -v shellcheck >/dev/null; then out=$(cd "$root" && shellcheck -x -s bash -f gcc "$rel" 2>&1); rc=$?
            elif have_docker; then out=$(in_docker koalaman/shellcheck:v0.10.0 -x -s bash -f gcc "$rel" 2>&1); rc=$?
            else exit 0; fi
        fi ;;
esac
(( rc == 0 )) && exit 0
printf 'Lint findings in the file you just edited (%s):\n%s\n' "$rel" "$(printf '%s\n' "$out" | head -n 20)" >&2
exit 2

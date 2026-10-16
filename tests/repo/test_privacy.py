"""No private or local information in the repository: working tree, every reachable commit, authors.

Generic patterns (e-mail addresses, private IP addresses, local host names, home directories) are checked
here. Personal terms that must not appear either (names, own domains, host names) belong in the untracked
file `.private-patterns` at the repository root, one regular expression per line (`#` starts a comment);
they are checked the same way without being published themselves.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}", re.I)
# No-reply and example addresses, plus the maintainer's public contact address (SECURITY.md)
ALLOWED_EMAIL = re.compile(
    r"(@users\.noreply\.github\.com|^noreply@(github|anthropic)\.com|@example\.(com|org)|^mail@coolcow\.org)$", re.I)
# 172.30.32.0/23 is the Supervisor's internal network, the same on every installation
GENERIC = {
    "private IPv4 address": re.compile(
        r"\b(?!172\.30\.3[23]\.)(?:192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"),
    "local host name": re.compile(r"\b[\w-]+\.(?:lan|home|internal|fritz\.box)\b", re.I),
    "home directory": re.compile(r"(?:/home|/Users)/(?!runner\b)[a-z][\w.-]*", re.I),
}


def git(*args, data=None):
    return subprocess.run(["git", *args], cwd=ROOT, input=data, capture_output=True, check=True).stdout


def local_patterns():
    path = ROOT / ".private-patterns"
    if not path.exists():
        return {}
    lines = (line.split("#", 1)[0].strip() for line in path.read_text().splitlines())
    return {f".private-patterns: {p}": re.compile(p, re.I) for p in lines if p}


def findings(text):
    for name, pattern in {**GENERIC, **local_patterns()}.items():
        for m in pattern.finditer(text):
            yield f"{name}: {m.group(0)}"
    for m in EMAIL.finditer(text):
        if not ALLOWED_EMAIL.search(m.group(0)):
            yield f"e-mail address: {m.group(0)}"


def tracked_texts():
    for f in git("ls-files", "-z").decode().split("\0"):
        if f and (ROOT / f).is_file():
            yield f, (ROOT / f).read_text(errors="ignore")


def history_blobs():
    """Every blob reachable from any ref (all commits, not only HEAD), once each."""
    objects = [line.split(" ", 1) for line in git("rev-list", "--objects", "--all").decode().splitlines()]
    named = {o[0]: o[1] for o in objects if len(o) == 2}
    out = git("cat-file", "--batch", data="\n".join(named).encode() + b"\n")
    pos = 0
    while pos < len(out):
        header_end = out.index(b"\n", pos)
        sha, kind, size = out[pos:header_end].decode().split()
        body = out[header_end + 1:header_end + 1 + int(size)]
        pos = header_end + 2 + int(size)
        if kind == "blob" and b"\0" not in body[:8000]:
            yield f"{named[sha]} ({sha[:10]})", body.decode(errors="ignore")


def test_working_tree_has_no_private_information():
    hits = sorted({f"{f}: {h}" for f, text in tracked_texts() for h in findings(text)})
    assert not hits, hits


def test_history_has_no_private_information():
    hits = sorted({f"{f}: {h}" for f, text in history_blobs() for h in findings(text)})
    assert not hits, hits


def test_commit_metadata_has_no_private_information():
    """Branches and tags, not a detached HEAD: in pull request CI that is GitHub's throwaway test merge, which
    carries the account's primary address and never lands anywhere. The merge on main is checked by the push."""
    log = git("log", "--branches", "--remotes", "--tags", "--format=%an <%ae>%n%cn <%ce>%n%B%n").decode()
    hits = sorted(set(findings(log)))
    assert not hits, hits

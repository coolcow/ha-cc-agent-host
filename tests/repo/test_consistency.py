"""Repository consistency: versions, changelogs, Claude Code pin, translations, naming.

Plain pytest + PyYAML (no Home Assistant), part of `scripts/agent/check` (step `repo`).
"""

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "cc_agent_host"
INTEGRATION = ROOT / "custom_components" / "cc_agent_host"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def load_yaml(path):
    return yaml.safe_load(path.read_text())


def load_json(path):
    return json.loads(path.read_text())


def changelog_versions(path):
    return re.findall(r"^## (\S+)\s*$", path.read_text(), flags=re.M)


def key_paths(obj, prefix=()):
    """All key paths of nested dicts, e.g. ('entity', 'sensor', 'plan', 'name')."""
    if not isinstance(obj, dict):
        return {prefix}
    paths = set()
    for k, v in obj.items():
        paths |= key_paths(v, (*prefix, k))
    return paths


# ---- versions and changelogs ----------------------------------------------------------------------

@pytest.mark.parametrize(("version", "changelog"), [
    pytest.param(lambda: load_yaml(ADDON / "config.yaml")["version"], ADDON / "CHANGELOG.md", id="add-on"),
    pytest.param(lambda: load_json(INTEGRATION / "manifest.json")["version"], INTEGRATION / "CHANGELOG.md",
                 id="integration"),
])
def test_version_is_newest_changelog_entry(version, changelog):
    v = version()
    assert isinstance(v, str), f"version must be a quoted string, got {v!r}"
    assert SEMVER.match(v), f"version {v!r} is not X.Y.Z"
    entries = changelog_versions(changelog)
    assert entries, f"{changelog.relative_to(ROOT)} has no '## X.Y.Z' entries"
    assert entries[0] == v, (
        f"{changelog.relative_to(ROOT)}: newest entry is {entries[0]}, version is {v} "
        "(raise the version and add a CHANGELOG entry for every change)")
    assert len(entries) == len(set(entries)), "duplicate CHANGELOG entries"


def test_changelog_versions_descend():
    for changelog in (ADDON / "CHANGELOG.md", INTEGRATION / "CHANGELOG.md"):
        versions = [tuple(map(int, v.split("."))) for v in changelog_versions(changelog)]
        assert versions == sorted(versions, reverse=True), f"{changelog.relative_to(ROOT)} not newest first"


# ---- Claude Code pin --------------------------------------------------------------------------------

def dockerfile_args():
    return dict(re.findall(r"^ARG (\w+)=(.*)$", (ADDON / "Dockerfile").read_text(), flags=re.M))


def test_claude_code_pin_format():
    args = dockerfile_args()
    assert SEMVER.match(args["CLAUDE_CODE_VERSION"]), args["CLAUDE_CODE_VERSION"]
    for arch in ("SHA512_ARM64", "SHA512_X64"):
        assert re.fullmatch(r"[0-9a-f]{128}", args[arch]), f"{arch} is not a sha512 hex digest"
    assert args["SHA512_ARM64"] != args["SHA512_X64"], "both architectures share one checksum"


def test_claude_code_is_verified_and_unmodified():
    """Official npm package, checksum-checked before install, installed as is."""
    text = (ADDON / "Dockerfile").read_text()
    url = "https://registry.npmjs.org/@anthropic-ai/claude-code-${pkg}/-/claude-code-${pkg}-${CLAUDE_CODE_VERSION}.tgz"
    assert url in text
    assert 'sha512sum -c -' in text
    assert text.index("sha512sum -c -") < text.index("tar -xzf /tmp/cc.tgz")
    assert "install -D -m 0755 /tmp/package/claude /usr/lib/cc_agent_host/claude" in text
    assert "DISABLE_AUTOUPDATER=1" in text


def test_only_64_bit():
    assert sorted(load_yaml(ADDON / "config.yaml")["arch"]) == ["aarch64", "amd64"]


# ---- translations -----------------------------------------------------------------------------------

def test_integration_translations_complete():
    strings = load_json(INTEGRATION / "strings.json")
    en = load_json(INTEGRATION / "translations" / "en.json")
    assert en == strings, "translations/en.json must equal strings.json (custom integrations ship both)"
    expected = key_paths(strings)
    for path in sorted((INTEGRATION / "translations").glob("*.json")):
        got = key_paths(load_json(path))
        assert got == expected, (f"{path.name}: missing {sorted(expected - got)[:10]}, "
                                 f"extra {sorted(got - expected)[:10]}")


def test_integration_entities_and_services_translated():
    strings = load_json(INTEGRATION / "strings.json")
    for platform in ("sensor", "binary_sensor"):
        keys = set(re.findall(r'key="(\w+)"', (INTEGRATION / f"{platform}.py").read_text()))
        assert keys, platform
        missing = keys - set(strings["entity"][platform])
        assert not missing, f"{platform} entities without translation: {sorted(missing)}"
    services = load_yaml(INTEGRATION / "services.yaml")
    assert set(services) == set(strings["services"])
    for name, spec in services.items():
        assert set(spec.get("fields", {})) == set(strings["services"][name]["fields"]), name
    keys = set(re.findall(r'translation_key="(\w+)"', "".join(
        p.read_text() for p in INTEGRATION.glob("*.py"))))
    exceptions = set(strings.get("exceptions", {}))
    issues = set(strings.get("issues", {}))
    missing = keys - exceptions - issues - set(strings["entity"].get("sensor", {})) \
        - set(strings["entity"].get("binary_sensor", {}))
    assert not missing, f"translation_key without translation: {sorted(missing)}"


def test_addon_translations_cover_options():
    options = set(load_yaml(ADDON / "config.yaml")["schema"])
    for path in sorted((ADDON / "translations").glob("*.yaml")):
        configuration = load_yaml(path)["configuration"]
        assert set(configuration) == options, f"{path.name}: {sorted(set(configuration) ^ options)}"
        for key, entry in configuration.items():
            assert entry.get("name") and entry.get("description"), f"{path.name}: {key}"


# ---- HACS (file-level part of the HACS action, which cannot read a private repository) --------------

def test_hacs_json():
    hacs = load_json(ROOT / "hacs.json")
    allowed = {"content_in_root", "country", "filename", "hacs", "hide_default_branch", "homeassistant",
               "persistent_directory", "render_readme", "zip_release", "name"}
    assert set(hacs) <= allowed, f"unknown keys: {sorted(set(hacs) - allowed)}"
    assert isinstance(hacs["name"], str)


def test_manifest():
    manifest = load_json(INTEGRATION / "manifest.json")
    for key in ("domain", "name", "codeowners", "documentation", "issue_tracker", "version", "config_flow"):
        assert key in manifest, key
    assert manifest["domain"] == INTEGRATION.name
    repo_url = "https://github.com/coolcow/ha-cc-agent-host"
    assert manifest["documentation"].startswith(repo_url) and manifest["issue_tracker"].startswith(repo_url)


# ---- naming: "Claude" is a trademark ----------------------------------------------------------------

def tracked_files(*dirs):
    out = subprocess.run(["git", "ls-files", "--", *dirs], cwd=ROOT, capture_output=True, text=True,
                         check=True).stdout
    return out.split()


def test_no_claude_in_names_and_identifiers():
    """Display name 'CC Agent Host', identifier 'cc_agent_host'; 'Claude' only in descriptive text."""
    config = load_yaml(ADDON / "config.yaml")
    manifest = load_json(INTEGRATION / "manifest.json")
    strings = load_json(INTEGRATION / "strings.json")
    names = {
        "add-on name": config["name"], "add-on slug": config["slug"], "panel title": config["panel_title"],
        "discovery": " ".join(config.get("discovery", [])), "options": " ".join(config["schema"]),
        "integration domain": manifest["domain"], "integration name": manifest["name"],
        "hacs name": load_json(ROOT / "hacs.json")["name"],
        "repository name": load_yaml(ROOT / "repository.yaml")["name"],
        "translation keys": " ".join("/".join(p) for p in key_paths(strings)),
        "entity names": " ".join(v["name"] for p in strings["entity"].values() for v in p.values()),
        "service names": " ".join([*strings["services"], *(s["name"] for s in strings["services"].values())]),
        "profiles": " ".join(p.stem for p in (ADDON / "rootfs/usr/share/cc_agent_host/profiles").glob("*")),
        "shipped file paths": " ".join(tracked_files("cc_agent_host", "custom_components")),
    }
    offending = {k: v for k, v in names.items() if "claude" in v.lower()}
    assert not offending, f"'Claude' in names/identifiers: {offending}"
    assert config["name"] == manifest["name"] == "CC Agent Host"
    assert config["slug"] == manifest["domain"] == "cc_agent_host"


def test_cc_abbreviation_not_explained():
    pattern = re.compile(r"\bcc\b\s*(=|:|\(|stands for|steht für|is short for|means)\s*claude", re.I)
    hits = [f"{f}:{n}" for f in tracked_files() if f.endswith((".md", ".yaml", ".yml", ".json", ".py"))
            for n, line in enumerate((ROOT / f).read_text(errors="ignore").splitlines(), 1)
            if pattern.search(line)]
    assert not hits, hits


@pytest.mark.parametrize("english", [ROOT / "README.md", ADDON / "DOCS.md"], ids=["README", "DOCS"])
def test_german_translation_in_sync(english):
    """Public docs are English with a German translation `*.de.md`: same section structure, linked both ways."""
    german = english.with_suffix(".de.md")
    levels = [[line.split(" ", 1)[0] for line in p.read_text().splitlines() if re.match(r"#+ ", line)]
              for p in (english, german)]
    assert levels[0] == levels[1], f"{german.name}: headings differ from {english.name}"
    assert german.name in english.read_text() and english.name in german.read_text()


def test_addon_image_points_to_release_workflow():
    """`image:` (set at publication) must be the name release.yaml pushes, with the {arch} placeholder."""
    image = load_yaml(ADDON / "config.yaml").get("image")
    if image is not None:
        assert image == "ghcr.io/coolcow/{arch}-addon-cc_agent_host"
    release = (ROOT / ".github" / "workflows" / "release.yaml").read_text()
    assert "/${{ matrix.arch }}-addon-cc_agent_host" in release

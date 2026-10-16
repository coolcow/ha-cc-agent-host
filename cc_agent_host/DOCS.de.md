# CC Agent Host

Führt die offizielle, unveränderte Claude-Code-CLI in Home Assistant mit deinem eigenen Claude-Abo aus:
ein Web-Terminal, optional Remote Control und Aufträge aus Automationen.

Claude Code arbeitet direkt in deiner Home-Assistant-Konfiguration: Es sieht die echten Dateien und
Logs, du kopierst also kein YAML mehr in ein Chatfenster und synchronisierst deine Konfiguration nicht
auf einen anderen Rechner. Du siehst jede Änderung und gibst sie frei. *English: [DOCS.md](DOCS.md)*

Nicht mit Anthropic verbunden und nicht von Anthropic unterstützt. Claude und Claude Code sind Marken
von Anthropic, PBC.

## Voraussetzungen

- Home Assistant OS oder Supervised, 64 Bit (aarch64 oder amd64): z. B. Home Assistant Green/Yellow,
  Raspberry Pi 4/5 mit 64-Bit-HAOS, x86-64-Mini-PCs und VMs. Einen 32-Bit-Build von Claude Code gibt es
  nicht.
- 2 GB RAM oder mehr (ein laufender Claude-Code-Prozess braucht etwa 300–500 MB).
- Ein Claude-Abo (Pro oder Max).
- In Home Assistant selbst ist nichts zu ändern: keine Konfigurationsänderungen, keine zusätzlichen
  Integrationen nötig.

## Erster Start

1. **CC Agent Host** in der Seitenleiste öffnen.
2. In Claude Code `/login` eingeben und die Anmeldung im Browser abschließen.
3. Optional: **Remote Control** in der Konfiguration einschalten und das Add-on neu starten.

Die Sitzung im Web-Terminal läuft weiter, wenn du den Browser schließt. Beendest du Claude Code, landest
du in einer Shell; `exit` startet Claude Code wieder.

## Remote Control

Mit eingeschaltetem **Remote Control** startet das Add-on `claude remote-control` im Server-Modus in
`/homeassistant`. Es erscheint als Umgebung in claude.ai/code und in der Claude-App, aber es bleibt keine
Sitzung offen: Eine neue Sitzung startet erst, wenn du dort eine öffnest, direkt in der Konfiguration
(Spawn-Modus `same-dir`, keine Worktrees) und im Berechtigungsmodus `default` (Claude fragt vor jeder
Änderung). Sitzungen enden, wenn das Add-on stoppt. Der Dienst wartet auf deine Anmeldung und startet
von selbst. Die Sitzung im Web-Terminal selbst ist nicht aus der Ferne erreichbar.

Der Server läuft in einer eigenen tmux-Sitzung `rc`. Beim ersten Mal fragt Claude Code
`Enable Remote Control? (y/n)` (und, falls der Ordner noch nicht vertrauenswürdig ist, ob
`/homeassistant` vertraut werden soll); das Add-on-Log weist dann darauf hin. Nur du beantwortest diese
Fragen: Web-Terminal öffnen, unten rechts in der Statusleiste **Remote Control** antippen, antworten und
mit **Terminal** zurück (geht auch auf dem Handy; mit Tastatur wechselt auch `Ctrl-b s`).

## Begleit-Integration

Aufträge und Sensoren brauchen die Begleit-Integration (Installation über HACS als benutzerdefiniertes
Repository mit der URL dieses Add-on-Repositorys, Typ *Integration*, danach Home Assistant neu
starten). Das Add-on meldet sich selbst an, die Integration erscheint also unter Einstellungen → Geräte &
Dienste und muss nur bestätigt werden; Adresse oder Schlüssel musst du nicht eingeben. Sie bringt:

- die Aktion **`cc_agent_host.run`** (`profile`, `prompt`, optional `timeout` in Sekunden), die `ok`,
  `result` und `error` an deine Automation zurückgibt (`response_variable`);
- die Binärsensoren **Angemeldet**, **Job-Token** und **Auftrag läuft**;
- Sensoren für die Plan-Nutzung (5-Stunden- und Wochenfenster in %, Reset-Zeitpunkte, Guthaben mit der
  Usage-API-Option, Nutzungsquelle, Plan);
- die Update-Entität **CLI** für Claude-Code-Updates (siehe unten).

## Aufträge

Aufträge führen Claude Code unbeaufsichtigt aus (`claude -p`), mit einem **Profil**, und geben das
Ergebnis zurück. Sie nutzen ein eigenes, langlebiges Token und berühren deine interaktive Anmeldung nie:

1. Im Terminal Claude Code beenden (`/exit`), dann `claude setup-token` ausführen und die Anmeldung
   abschließen.
2. `cc-job-token` ausführen und das ausgegebene Token einfügen (die Eingabe ist verborgen).
3. Mit `exit` zurück zu Claude Code.

Profile sind YAML-Dateien im Add-on-Konfigurationsordner (`profiles/`). Fehlende Standardprofile werden
beim Start ergänzt; vorhandene Dateien werden nie überschrieben. Standardprofile:

| Profil | Werkzeuge | Kontextdateien |
|---|---|---|
| `read` | Read, Grep, Glob | keine |
| `read-config` | Read, Grep, Glob | gefilterte Kopie der HA-Konfiguration |
| `log-digest` | Read, Grep, Glob | Home-Assistant-Systemlog (Fehler, Warnungen) |

Profilschlüssel: `description`, `model` (Standard `sonnet`), `max_turns`, `timeout` (Sekunden, max.
1800), `max_budget_usd`, `tools` (eingebaute Claude-Code-Werkzeuge), `context` (`ha_system_log`,
`ha_states`, `ha_history`, `ha_config`; `ha_log` braucht die Supervisor-Rolle `homeassistant`),
`system_prompt`.

Der Kontext `ha_history` schreibt den Verlauf des Recorders als kompakte Zeitleisten, eine Datei pro
Bereich (`ha_history/<bereich>.txt`, Übersicht in `ha_history/INDEX.md`, Ortszeit). Optionen: `hours`
(Standard 24, max. 240), `bucket_minutes` (Zahlen als Min–Max pro Intervall, Standard 10),
`min_duration_s` (`unavailable`/`unknown` kürzer als dieser Wert wird verworfen), `domains`,
`sensor_device_classes`, `skip_binary_device_classes`, `include` / `exclude` (Globs für Entitäts-IDs),
`steps` (Rundung pro Einheit, z. B. `{"°C": 0.5}`; andere Einheiten: zwei signifikante Stellen).

### Wie Aufträge abgeschottet sind

- Aufträge laufen als Benutzer `cc_agent` ohne Sonderrechte in einem temporären Verzeichnis, das nur
  ihre Kontextdateien enthält.
- Die Home-Assistant-Konfiguration, die Add-on-Daten (Anmeldung, Tokens, Optionen) und das
  Supervisor-Token sind für diesen Benutzer überhaupt nicht erreichbar; die Kontextdateien bereitet das
  Add-on vor.
- Nur die im Profil genannten Werkzeuge sind verfügbar; alles andere wird ohne Rückfrage abgelehnt.
- Ein Auftrag gleichzeitig, Zeitlimit pro Profil, begrenzte Ausgabe, jeder Auftrag wird (ohne den
  Prompt-Text) in den Add-on-Daten protokolliert (`audit.log`).

### Schnittstelle

Nur aus dem internen Home-Assistant-Netz erreichbar, mit einem Bearer-Token, das das Add-on der
Begleit-Integration mitteilt. `GET /status`, `GET /profiles`, `GET /usage`,
`POST /run {"profile": "...", "prompt": "...", "timeout": 300}`, `POST /cli/update {"version": "..."}`.

`/usage` liefert die Plan-Nutzung, siehe nächster Abschnitt.

## Plan-Nutzung

Zwei Quellen, gewählt mit der Option **Vollständige Plan-Nutzung über die Usage-API**:

| | Statuszeile (Standard) | Usage-API (bewusst einschalten) |
|---|---|---|
| Daten | Nutzung 5 Stunden und Woche, Reset-Zeitpunkte | dasselbe, plus Guthaben und Aufteilung der Woche (Claude Code, Chat, …) |
| Aktualität | nur während die Sitzung im Web-Terminal genutzt wird | alle 5 Minuten, auch im Leerlauf |
| Zugangsdaten | werden nie angefasst | das Add-on liest das Zugangstoken deiner interaktiven Anmeldung |
| Stabilität | offizielle Funktion von Claude Code | undokumentierter Endpunkt, kann sich ändern oder verschwinden |

**Plan-Erkennung.** `/status` meldet den Plan deiner Anmeldung (`pro`, `max_5x`, `max_20x`, …) und seinen
Nutzungsfaktor relativ zu Pro (1, 5, 20). Die Abo-Art kommt aus `claude auth status`; nur mit der
Usage-API-Option lässt sich Max 5x von Max 20x unterscheiden (sonst wird der Plan als `max` gemeldet).

**Warum die Usage-API standardmäßig aus ist.** Um sie abzufragen, muss Add-on-Code das Zugangstoken
deiner Claude-Anmeldung lesen. Anthropics Bedingungen besagen, dass Software von Dritten
Claude.ai-Zugangsdaten nicht sammeln, speichern oder vermitteln darf, und der Endpunkt selbst ist keine
dokumentierte öffentliche API. Das Add-on hält das Risiko klein (das Token bleibt im Add-on, wird nur an
`api.anthropic.com` gesendet, und das Erneuern bleibt Claude Code selbst überlassen), aber ob das für dich
in Ordnung ist, entscheidest du, deshalb musst du es bewusst einschalten.

## Claude-Code-Updates

Das Add-on bringt eine festgelegte, per Prüfsumme verifizierte Claude-Code-Version mit. Neuere Versionen
brauchen keine neue Add-on-Version: Das Add-on prüft alle 6 Stunden bei npm die neueste
Claude-Code-Version, und die Begleit-Integration bietet sie als Update an (Entität **CLI** des Geräts
CC Agent Host, unter Einstellungen → Updates). Nichts wird automatisch installiert: **Installieren** lädt
das offizielle Paket für deine Architektur, prüft die sha512-Prüfsumme der Registry und die gemeldete
Version und legt es in den Add-on-Daten ab (`/data/cli`, die neue und die vorherige Version). Remote
Control startet mit der neuen Version neu (offene Cloud-Sitzungen werden getrennt); die Sitzung im
Web-Terminal nutzt sie nach ihrem nächsten Start (`/exit`, dann `exit`). Eine Add-on-Version mit
derselben oder einer neueren Claude-Code-Version ersetzt das installierte Update.

## Lange Links

Lange Links (zum Beispiel der Anmeldelink) werden über mehrere Zeilen umbrochen, und nur die erste Zeile
ist anklickbar. Halte **Shift** gedrückt und markiere den ganzen Link mit der Maus: Die Auswahl wird
automatisch kopiert. Füge ihn in einen neuen Browser-Tab ein; die Zeilenumbrüche fallen beim Einfügen
weg.

## Daten

- Anmeldung und Claude-Code-Einstellungen: Add-on-Daten, in Backups enthalten.
- Über die Update-Entität installiertes Claude Code: Add-on-Daten (`/data/cli`).
- Arbeitsverzeichnis des Terminals: deine Home-Assistant-Konfiguration (`/homeassistant`).

## Sicherheit

- Das Web-Terminal ist nur über Home-Assistant-Ingress erreichbar (nur Admins).
- Es sind keine Ports offen; die Auftrags-Schnittstelle ist nur im internen Add-on-Netz und mit Token
  erreichbar.
- Claude Code ist das offizielle, unveränderte Programm, geprüft über seine sha512-Prüfsumme; das Add-on
  liest, kopiert und versendet deine Anmeldung nie, außer mit der oben beschriebenen, bewusst
  einzuschaltenden Usage-API-Option.
- Aufträge können nichts ändern: siehe [Wie Aufträge abgeschottet sind](#wie-aufträge-abgeschottet-sind).
- Im Terminal und in Remote-Control-Sitzungen arbeitet Claude Code mit deinen Rechten auf deiner
  Konfiguration und fragt vor jeder Änderung. Mach Backups, am besten liegt deine Konfiguration in git.

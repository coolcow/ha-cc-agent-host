# CC Agent Host

**Claude Code direkt in Home Assistant, neben deiner Konfiguration.**
Eine Home-Assistant-App (Add-on) mit einer kleinen Begleit-Integration, mit der du die offizielle
Claude-Code-CLI mit deinem eigenen Claude-Abo nutzt: in der Seitenleiste von Home Assistant, aus der
Claude-App auf dem Handy und aus deinen Automationen.

**Schluss damit, Dashboards, Automationen und Skripte wie in der Steinzeit von Hand zu bauen.** Sag
Claude, was du haben willst, und nutze es einfach. Claude Code baut es direkt in deiner Konfiguration,
behält die Dinge mit geplanten Aufträgen im Blick und schlägt Verbesserungen vor; so wird deine
Installation mit jeder Runde Benutzen und Besprechen besser. Und anders als ein per MCP von außen
angebundener Assistent läuft alles in Home Assistant selbst: nichts weiter zu installieren, kein zweiter
Rechner.

*English: [README.md](README.md)*

> Nicht mit Anthropic verbunden und nicht von Anthropic unterstützt. Claude und Claude Code sind Marken
> von Anthropic, PBC. Du meldest dich mit deinem eigenen Konto in Claude Code an; dieses Projekt fasst
> deine Zugangsdaten nicht an.

## Was du bekommst

Claude Code läuft direkt auf dem Home-Assistant-Gerät, mit deiner Konfiguration als Arbeitsverzeichnis.
Es sieht die echten Dateien und Logs; kein YAML in einen Chat kopieren, nichts auf einen anderen Rechner
synchronisieren.

- **Web-Terminal in der Seitenleiste**, auf jedem Gerät, das Home Assistant öffnet. Die Sitzung läuft
  weiter, wenn du den Tab schließt.
- **Remote Control (optional):** Sitzungen aus claude.ai/code oder der Claude-App auf dem Handy öffnen.
- **Aufträge aus Automationen:** Die Aktion `cc_agent_host.run` schickt einen Prompt und gibt die Antwort
  an deine Automation zurück. Aufträge laufen nur lesend in einer abgeschotteten Umgebung.
- **Sensoren** für Anmeldung, laufende Aufträge und Plan-Nutzung, dazu **Claude-Code-Updates** unter
  Einstellungen → Updates (festgelegt und per Prüfsumme verifiziert, nie automatisch).

## Anwendungsbeispiele

**Im Terminal oder vom Handy aus** (Claude Code fragt vor jeder Änderung):

- „Warum ist das Flurlicht gestern Abend nicht angegangen?“ Es liest die Automation, ihren Trace und das Log.
- „Schreib eine Automation, die die Heizung ausschaltet, wenn ein Fenster fünf Minuten offen ist.“
- „Welche Automationen, Skripte und Dashboards verwenden noch Entitäten, die es nicht mehr gibt?“
- „Verschieb die Klima-Automationen in ein Package und mach aus den drei ähnlichen einen Blueprint.“
- „Lies die Breaking Changes der neuesten Version und prüf meine Konfiguration dagegen.“
- „Ergänze einen Temperatursensor an meinem ESPHome-Gerät `buero` und erklär die Verkabelung.“

**Als Aufträge aus Automationen** (nur lesend, Antwort zurück an die Automation):

- Morgens eine Zusammenfassung neuer Fehler, nur wenn es etwas Neues gibt (Beispiel unten).
- Wöchentlich nicht erreichbare Geräte und schwache Batterien, mit eigenem Profil (Beispiel unten).
- „Fasse Heizung und Energie der letzten Woche zusammen und nenn Auffälligkeiten“ (Kontext `ha_history`).
- „Verweist meine Konfiguration noch auf `light.alte_lampe`?“, bevor du ein Gerät entfernst (`read-config`).

Morgendliche Log-Zusammenfassung mit dem mitgelieferten Profil `log-digest`:

```yaml
automation:
  - alias: Morgendliche Log-Zusammenfassung
    triggers:
      - trigger: time
        at: "07:30:00"
    actions:
      - action: cc_agent_host.run
        data:
          profile: log-digest
          prompt: >-
            Liste neue Fehler und Warnungen der letzten 24 Stunden in höchstens fünf Stichpunkten auf.
            Antworte genau "nichts Neues", wenn es keine gibt.
        response_variable: digest
      - if: "{{ digest.ok and digest.result | trim != 'nichts Neues' }}"
        then:
          - action: notify.mobile_app_mein_handy
            data:
              title: Home-Assistant-Log
              message: "{{ digest.result }}"
```

Eigenes Profil, als `profiles/house-check.yaml` im Konfigurationsordner des Add-ons, dann genutzt mit
`profile: house-check` und einem Prompt wie „Welche Geräte sind seit mehr als einem Tag nicht
erreichbar, und welche Batterien liegen unter 20 %?“:

```yaml
description: Wöchentlicher Blick auf Geräte und Batterien
model: sonnet
max_turns: 10
timeout: 300
tools: [Read, Grep, Glob]
context:
  - ha_states:
      domains: [sensor, binary_sensor, light, switch, climate]
```

## Voraussetzungen

- **Home Assistant OS** auf 64-Bit-Hardware (aarch64 oder amd64): Home Assistant Green oder Yellow,
  Raspberry Pi 4/5, x86-64-Mini-PCs und VMs. Supervised-Installationen funktionieren auch, werden von
  Home Assistant aber nicht mehr unterstützt; Container- und Core-Installationen haben keine Apps. Ein
  32-Bit-Claude-Code gibt es nicht.
- 2 GB RAM oder mehr: ein laufender Claude-Code-Prozess braucht etwa 300–500 MB.
- Ein Claude-Pro- oder -Max-Abo, gedacht für eine Person, wie es die Bedingungen von Anthropic vorsehen.

## Sicherheit

Es gibt zwei Arbeitsweisen mit unterschiedlichen Rechten:

- **Terminal und Remote Control: du entscheidest.** Claude Code arbeitet in deiner Konfiguration und
  kann Automationen und andere Dateien anlegen oder ändern, fragt aber vor jeder Änderung und zeigt sie
  dir vorher. Mach Backups, besser noch: halte deine Konfiguration in git.
- **Aufträge aus Automationen: nur lesend.** Ein Auftrag läuft als Benutzer ohne Rechte und sieht nur
  die Daten, die sein Profil bereitstellt (zum Beispiel das Log oder eine gefilterte Kopie der
  Konfiguration), nie die echte Konfiguration, Geheimnisse, Anmeldung oder Home-Assistant-Tokens. Er
  kann nur die Werkzeuge nutzen, die das Profil erlaubt, und ändert nichts; jeder Auftrag wird
  protokolliert.

In beiden Fällen gilt:

- Claude Code ist das **offizielle, unveränderte** Programm von npm, festgelegt mit seiner
  sha512-Prüfsumme.
- **Anmeldung nur in Claude Code selbst** (`/login`); das Add-on liest, kopiert und versendet deine
  Zugangsdaten nie, außer mit der ausdrücklich einzuschaltenden Option *Vollständige Plan-Nutzung über
  die Usage-API* ([Details](cc_agent_host/DOCS.de.md#plan-nutzung)).
- **Keine offenen Ports:** Terminal nur über Home-Assistant-Ingress (Admins), Auftrags-Schnittstelle nur
  im internen Netz und mit Token.

## Installation

Das Repository ist noch nicht veröffentlicht; die Schritte beschreiben die Einrichtung danach.

1. **App:** Einstellungen → Apps → App-Store → ⋮ → Repositories, dort
   `https://github.com/coolcow/ha-cc-agent-host` hinzufügen, dann **CC Agent Host** installieren und
   starten. Das Image wird bei der Installation auf deinem Gerät gebaut; das dauert ein paar Minuten.
2. **Anmelden:** **CC Agent Host** in der Seitenleiste öffnen, `/login` eingeben und die Anmeldung im
   Browser abschließen.
3. **Integration (optional, für Aufträge und Sensoren):** in HACS → ⋮ → Benutzerdefinierte Repositories
   dieselbe URL mit Typ *Integration* hinzufügen, **CC Agent Host** installieren und Home Assistant neu
   starten. Das Add-on wird dann unter Einstellungen → Geräte & Dienste gefunden.
4. **Aufträge (optional):** einmalig ein Auftrags-Token anlegen, wie in der
   [Dokumentation](cc_agent_host/DOCS.de.md#aufträge) beschrieben.

## Dokumentation

- [Add-on-Dokumentation](cc_agent_host/DOCS.de.md): Terminal, Remote Control, Aufträge und Profile,
  Plan-Nutzung, Updates, Sicherheit ([English](cc_agent_host/DOCS.md))
- Englisch: [Design](docs/DESIGN.md) · [Entwicklung](docs/DEVELOPMENT.md) (Dev-Container, Tests, CI) ·
  [Sicherheitsrichtlinie](SECURITY.md) · Regeln für Coding-Agenten in [CLAUDE.md](CLAUDE.md)

## Lizenz

MIT, siehe [LICENSE](LICENSE).

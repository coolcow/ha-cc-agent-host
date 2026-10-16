# CC Agent Host

**Claude Code direkt in Home Assistant, neben deiner Konfiguration.**
Eine Home-Assistant-App (Add-on) mit einer kleinen Begleit-Integration, mit der du die offizielle
Claude-Code-CLI mit deinem eigenen Claude-Abo nutzt: in der Seitenleiste von Home Assistant, aus der
Claude-App auf dem Handy und aus deinen Automationen.

*English: [README.md](README.md)*

> Nicht mit Anthropic verbunden und nicht von Anthropic unterstützt. Claude und Claude Code sind Marken
> von Anthropic, PBC. Du meldest dich mit deinem eigenen Konto in Claude Code an; dieses Projekt fasst
> deine Zugangsdaten nicht an.

## Warum?

Claude Code ist sehr gut in genau der Arbeit, die eine Home-Assistant-Installation macht: YAML schreiben
und reparieren, Automationen und Vorlagen entwirren, Logs durchgehen, um herauszufinden, warum etwas
kaputt ist. Aber Claude Code arbeitet mit Dateien, und deine Konfiguration liegt auf dem
Home-Assistant-Gerät. Heute heißt das meistens eines davon:

- YAML und Log-Ausschnitte in ein Chatfenster kopieren und die Antworten zurück, ohne dass der Assistent
  den Rest deiner Installation je sieht;
- die Konfiguration per Samba oder SSH auf einem Rechner mit Claude Code einbinden und beides synchron
  halten;
- Werkzeuge von Hand auf dem Home-Assistant-Host installieren, was Home Assistant OS nicht vorsieht.

CC Agent Host schließt diese Lücke. Claude Code läuft als normales Add-on auf demselben Gerät, mit deiner
Home-Assistant-Konfiguration als Arbeitsverzeichnis. Es sieht die echten Dateien, kann die Logs lesen,
und du siehst jede Änderung und gibst sie frei. Nichts auf deinem Rechner zu installieren, nichts zu
synchronisieren.

## Was du bekommst

- **Web-Terminal in der Seitenleiste.** Claude Code im Browser, auf jedem Gerät, das Home Assistant
  öffnen kann. Die Sitzung läuft weiter, wenn du den Tab schließt.
- **Remote Control (optional).** Das Add-on erscheint als Umgebung in claude.ai/code und in der
  Claude-App. Öffne unterwegs eine Sitzung auf dem Handy und repariere die Automation vom Sofa oder aus
  dem Zug; Claude Code fragt weiterhin vor jeder Änderung.
- **Aufträge aus Automationen.** Die Aktion `cc_agent_host.run` schickt einen Prompt an Claude Code und
  gibt die Antwort an deine Automation zurück, zum Beispiel jeden Morgen „Fasse zusammen, was in den
  letzten 24 Stunden kaputtgegangen ist“, aufs Handy nur dann, wenn es etwas Neues gibt. Aufträge laufen
  nur lesend in einer abgeschotteten Umgebung (Details unten).
- **Sensoren.** Angemeldet, Auftrag läuft, Plan-Nutzung im 5-Stunden- und Wochenfenster mit
  Reset-Zeitpunkten und das erkannte Abo, bereit für Dashboards und Benachrichtigungen.
- **Claude-Code-Updates als Home-Assistant-Updates.** Das Add-on bringt eine festgelegte, per
  Prüfsumme verifizierte Version mit und bietet neuere offizielle Versionen unter Einstellungen →
  Updates an. Nichts aktualisiert sich von selbst.

## Ist es etwas für dich?

Passt gut, wenn du

- schon ein Claude-Pro- oder -Max-Abo hast und lieber das nutzt, als pro API-Token zu zahlen;
- deine Konfiguration als YAML bearbeitest (oder damit anfangen willst) und einen Assistenten möchtest,
  der das Ganze sieht;
- deinem Home Assistant regelmäßig Fragen stellen willst, ohne einer KI Schreibrechte zu geben.

Voraussetzungen und Grenzen:

- Home Assistant OS oder Supervised auf 64-Bit-Hardware (aarch64 oder amd64), zum Beispiel Home
  Assistant Green oder Yellow, Raspberry Pi 4/5 mit 64-Bit-System, x86-64-Mini-PCs und VMs. Container-
  und Core-Installationen haben keine Add-ons. Ein 32-Bit-Claude-Code gibt es nicht.
- 2 GB RAM oder mehr: ein laufender Claude-Code-Prozess braucht etwa 300–500 MB.
- Gedacht für eine Person mit eigenem Abo, wie es die Bedingungen von Anthropic vorsehen.
- Im Terminal und in Remote-Control-Sitzungen kann Claude Code deine Konfiguration ändern (nach
  Rückfrage). Mach Backups, besser noch: halte deine Konfiguration in git.

## Sicherheit auf einen Blick

- Claude Code ist das **offizielle, unveränderte** Programm von npm, festgelegt mit seiner
  sha512-Prüfsumme.
- **Anmeldung nur in Claude Code selbst** (`/login`). Das Add-on liest, kopiert und versendet deine
  Zugangsdaten nicht. Einzige Ausnahme ist die ausdrücklich einzuschaltende Option *Vollständige
  Plan-Nutzung über die Usage-API* (standardmäßig aus), erklärt in der
  [Dokumentation](cc_agent_host/DOCS.de.md#plan-nutzung).
- **Keine offenen Ports.** Das Terminal ist nur über Home-Assistant-Ingress erreichbar (nur Admins), die
  Auftrags-Schnittstelle nur im internen Add-on-Netz und mit Token.
- **Aufträge sind abgeschottet:** ein Benutzer ohne Rechte, ohne Zugriff auf deine Konfiguration,
  Geheimnisse, Anmeldung oder Home-Assistant-Tokens, nur die Werkzeuge, die das Profil erlaubt, ein
  Auftrag gleichzeitig, jeder Auftrag protokolliert.
- **In Home Assistant selbst wird nichts geändert**, weder vom Add-on noch von der Integration.

## Installation

Das Repository ist noch nicht veröffentlicht; die Schritte beschreiben die Einrichtung danach.

1. **Add-on:** Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories, dort
   `https://github.com/coolcow/ha-cc-agent-host` hinzufügen, dann **CC Agent Host** installieren und
   starten. Das Image wird bei der Installation auf deinem Gerät gebaut; das dauert ein paar Minuten.
2. **Anmelden:** **CC Agent Host** in der Seitenleiste öffnen, `/login` eingeben und die Anmeldung im
   Browser abschließen.
3. **Integration (optional, für Aufträge und Sensoren):** in HACS → ⋮ → Benutzerdefinierte Repositories
   dieselbe URL mit Typ *Integration* hinzufügen, **CC Agent Host** installieren und Home Assistant neu
   starten. Das Add-on wird dann unter Einstellungen → Geräte & Dienste gefunden.
4. **Aufträge (optional):** einmalig ein Auftrags-Token anlegen, wie in der
   [Dokumentation](cc_agent_host/DOCS.de.md#aufträge) beschrieben.

## Beispiel: morgendliche Log-Zusammenfassung

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

## Dokumentation

- [Add-on-Dokumentation](cc_agent_host/DOCS.de.md): Terminal, Remote Control, Aufträge und Profile,
  Plan-Nutzung, Updates, Sicherheit ([English](cc_agent_host/DOCS.md))
- [Design](docs/DESIGN.md) (englisch): Ziele, Aufbau und die Gründe für die wichtigsten Entscheidungen
- [Entwicklung](docs/DEVELOPMENT.md) (englisch): Tests, CI, Versionierung, lokale Installation

## Entwicklung

Dev-Container (`.devcontainer/`: Python 3.14, Docker-CLI → Docker des Hosts, gh, Claude Code):
`npx @devcontainers/cli up --workspace-folder .`, dann
`npx @devcontainers/cli exec --workspace-folder . claude` (oder in VS Code „Reopen in Container“).
Ohne: `scripts/setup`. Prüfungen: `scripts/agent/check`. Details in
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md), Regeln für Coding-Agenten in [`CLAUDE.md`](CLAUDE.md).

## Lizenz

MIT, siehe [LICENSE](LICENSE).

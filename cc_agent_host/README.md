# CC Agent Host

Runs the official, unmodified Claude Code CLI inside Home Assistant with your own
Claude subscription.

Not affiliated with or endorsed by Anthropic. Claude and Claude Code are trademarks
of Anthropic, PBC.

## First start

1. Open **CC Agent Host** in the sidebar.
2. Type `/login` in Claude Code and complete the sign-in in your browser.
3. Optional: enable **Remote Control** in the configuration and restart the add-on.

The session keeps running when you close the browser. Exiting Claude Code drops you
into a shell; `exit` starts Claude Code again.

## Long links

Long links (for example the sign-in link) wrap over several lines, and only the first line
is clickable. Hold **Shift** and select the whole link with the mouse: the selection is copied
automatically. Paste it into a new browser tab; the line breaks are removed on paste.

## Data

- Login and Claude Code settings: add-on data (`/data/claude`), included in backups.
- Working directory: your Home Assistant configuration (`/homeassistant`).

## Security

- The web terminal is reachable only through Home Assistant ingress (admins only).
- No ports are exposed.

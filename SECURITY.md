# Security policy

CC Agent Host runs an AI coding agent next to your Home Assistant configuration, so security reports are
very welcome. Areas of particular interest:

- a job (`cc_agent_host.run`) that can write, run commands, reach the network or read anything outside its
  context files (configuration, `secrets.yaml`, the Claude Code sign-in, Home Assistant or Supervisor tokens);
- the web terminal or the job API being reachable other than through ingress or the internal add-on network;
- add-on code reading, storing or sending Claude credentials beyond the documented opt-in `usage_api` option;
- the Claude Code binary or an update installed without a matching checksum.

## Reporting

Please do **not** open a public issue. Use GitHub's private vulnerability reporting instead:
**Security → Report a vulnerability** in this repository. Include the add-on and integration versions, what
you did and what you expected. You will get an answer within a week.

## Supported versions

Only the latest add-on and integration releases receive fixes.

## Out of scope

Vulnerabilities in Claude Code itself go to Anthropic (see the security policy of
[anthropics/claude-code](https://github.com/anthropics/claude-code/security)), vulnerabilities in Home Assistant to the Home Assistant project. Changes Claude Code makes in the
interactive terminal or Remote Control session after you approved them are not vulnerabilities.

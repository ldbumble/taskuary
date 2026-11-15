# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use
[GitHub's private vulnerability reporting](https://github.com/ldbumble/taskuary/security/advisories/new)
— it goes only to the maintainers.

Please include what you were running (version, OS, Python), what you did, and what
happened. You'll get a first response within a week, and credit in the release notes when
a fix ships unless you'd rather stay anonymous.

Supported: the latest release on `master`. There are no backported security fixes for
older versions while the project is pre-1.0.

## What Taskuary is, security-wise

Taskuary is a **local-first, single-user application**. It binds to `127.0.0.1` and
assumes the only person who can reach that port is the person sitting at the machine.
That assumption is the whole security model — the notes below are what follows from it.

- **Every request needs a token.** On first start Taskuary writes an owner token
  (`[server].token`) and a separate agent token to `~/.taskuary/config.toml`, and the API
  refuses a request without one (a provider's sign-in redirect and a vendor's signed push
  prove themselves another way). The browser gets the owner token from a one-time launch
  key when Taskuary opens it (`taskuary --link` prints a new one); a page opened without
  the key carries no token. Agent sessions carry the agent token, which the routes that
  send, approve or change settings refuse. `/api/health` stays open on purpose so a
  container HEALTHCHECK can pulse the process without the token.
- **Don't expose it to a network you don't trust.** If you must reach it from elsewhere,
  send the token as the `X-Taskuary-Token` header (`TASKUARY_TOKEN` sets it in Docker) and
  put it behind TLS you control. The token gate is a lock on a door, not a hardened
  perimeter.
- **Docker still assumes localhost.** `docker compose` publishes `127.0.0.1:7787`; the
  process inside listens on `0.0.0.0` only so Docker can reach it. Changing the publish
  bind to `0.0.0.0:7787` (LAN) is the same as a local install with `[server].host =
  "0.0.0.0"`.
- **The API executes things by design.** Reports run SQL and PowerShell, `/api/tools/run`
  runs a connector's query or script, agent dispatch runs your configured CLI, and the
  terminal opens a real shell — all with your credentials, on your machine. Anyone who
  can reach the API can do those things. `/api/tools/run` still refuses a catalog
  connection that is off or not marked *tool* (cards are seeded on first launch, so
  "never connected" is not the same as "no row").
- **Credentials are stored locally.** Connector secrets in `~/.taskuary/taskuary.db` are
  sealed with Windows DPAPI or the system keychain where one exists, and stay plain text
  where neither does; `config.toml` (the tokens among them) is plain text. They are
  write-only through the UI (never returned to the browser). Sealing stops a copy of the
  file carrying the keys, not a program running as you: the files are only as protected
  as your user account and disk encryption.
- **Agents act with your permissions.** A CLI agent configured with an auto-approve flag
  will edit files, run commands, and push to repos without asking. Scope its PAT and
  working directories to what you actually want it to touch.
- **The text Taskuary reads is written by other people, and some of it is written for the
  AI** (prompt injection). Triage runs with no tools, no agent works a stranger's task
  until you press Trust, and nothing is sent without your press. An agent that is running still acts as you. See
  [Security](https://taskuary.com/docs/security) for what is and is not covered.
- **AI triage sends message content to whichever AI you connect** (an API provider, or
  your local CLI agent). Nothing leaves the machine until you connect one.

## Good hygiene

- Give GitHub PATs the narrowest repository access and permission set that works.
- Keep `~/.taskuary/` out of backups that sync somewhere you don't control.
- Attachment URLs only serve files under `~/.taskuary/attachments/` — a `Path` that
  escaped that folder is a 404. SVG/HTML always download; they are not rendered as a
  document on the app origin.
- Read `~/.taskuary/taskuary.log` and the in-app audit log (Settings → Audit integrity —
  it's a hash chain) if you want to know what ran and when.

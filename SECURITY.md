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

Taskuary is a **local-first, single-user application**. It binds to `127.0.0.1` and has
no authentication by default, because it assumes the only person who can reach that port
is the person sitting at the machine. That assumption is the whole security model — the
notes below are what follows from it.

- **Don't expose it to a network you don't trust.** If you must reach it from elsewhere,
  set `[server].token` in `~/.taskuary/config.toml` and send it as the `X-Taskuary-Token`
  header (and put it behind TLS you control). The token gate is a lock on a door, not a
  hardened perimeter.
- **The API executes things by design.** Reports run SQL and PowerShell, `/api/tools/run`
  runs a connector's query or script, agent dispatch runs your configured CLI, and the
  terminal opens a real shell — all with your credentials, on your machine. Anyone who
  can reach the API can do those things.
- **Credentials are stored locally in plaintext** in `~/.taskuary/taskuary.db` and
  `config.toml`. They are write-only through the UI (never returned to the browser), but
  the files themselves are only as protected as your user account and disk encryption.
- **Agents act with your permissions.** A CLI agent configured with an auto-approve flag
  will edit files, run commands, and push to repos without asking. Scope its PAT and
  working directories to what you actually want it to touch.
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

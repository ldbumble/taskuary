# Taskuary

**Automate Your Work.** *(formerly TaskHub — everything streams into one estuary.)*

Task-driven agent work over your **existing systems** — fully local, nothing assumed,
bring your own AI CLI.

Everything inbound lands in one funnel. Real work becomes tasks on a kanban board.
Coding agents (Claude Code, Codex, or any CLI you configure) pick tasks up, work them in
your repos, show you the **diff**, and stay **resumable** — message an agent mid-task and
it continues the same session. You review; nothing sends or ships without you.

```
pip install git+https://github.com/ldbumble/taskuary
taskuary            # web app on http://127.0.0.1:7787, opens in your browser
```

## Getting started

**Prerequisites:** Python 3.10+ and `git`. That's it — the store is SQLite, no services
to stand up. Optional: a local [AI CLI](#bring-your-own-agent) like Claude Code for agent
runs; Microsoft's ODBC driver (preinstalled on most Windows machines) for SQL Server
reports.

### 1. Install & run (web app)

```bash
git clone https://github.com/ldbumble/taskuary
cd taskuary
pip install -e .[mssql]     # [mssql] adds pyodbc for SQL Server connections
taskuary                    # http://127.0.0.1:7787 opens in your browser
```

All data lives in `~/.taskuary/` (override with the `TASKUARY_HOME` env var): `taskuary.db`
is the SQLite store, `config.toml` holds server/agent config. An existing `~/.taskhub`
dir from the old name is migrated automatically. CLI flags: `--port`, `--no-browser`.

### 2. Or run it as a desktop app

```bash
pip install -e .[mssql,desktop]   # [desktop] adds pywebview (Edge WebView2 window)
taskuary-desktop                  # same UI, native window, random free port
```

Flags: `--port 7787` to pin the port, `--server-only` to run headless (service / CI
smoke tests). Without pywebview installed it falls back to opening your browser.

### 3. Or build the single-file executable

```bash
pip install -e .[mssql,desktop,build]   # [build] adds PyInstaller
pyinstaller taskuary.spec
dist/Taskuary.exe                       # server + UI + pyodbc in one file, no Python needed
```

Every push also builds this on CI — grab `Taskuary-windows-exe` from the Actions
artifacts if you don't want to build locally.

### 4. Configure — all in the UI

Open **Settings** (top-right):

- **Agents** — point Taskuary at your AI CLI (`claude`, `codex`, a wrapper script...):
  cmd, args, resume args, timeout, working dir, and the repo → local checkout map.
- **Report connections** — add a Microsoft SQL Server query (Windows auth works out of
  the box for a local instance — just server + database + query), an MCP server tool, or
  a SQLite/REST/RSS pull. Schedule with *every N minutes* or *daily at HH:MM*.
  **Test connection** and **Preview** run it live before you save; **Run now** files a
  row immediately.
- **App settings** — the engine knobs, saved on change: `default_action`,
  `auto_draft_enabled`, `attach_threshold`, `feed_days`, `intent_classify_enabled`,
  `coder_auto_enabled`.

No config files required; the UI persists everything (agents land in
`~/.taskuary/config.toml`, which you can still hand-edit).

### 5. Run the tests

```bash
pip install -e .[dev]
pytest -q                   # 37 tests, ~1s, no network or SQL Server needed
```

CI (`.github/workflows/ci.yml`) runs the suite on Windows + Linux, Python 3.10 and 3.12,
plus the exe build, on every push and PR.

## Why

Your work already lives in systems — email, chat, databases, GitHub, dashboards. You
don't need another place to *put* work; you need one place where work **arrives, gets
triaged, gets done by agents, and gets reviewed by you**. Taskuary is that funnel:

```
anything in  →  one funnel  →  triage (task / reply-only / FYI)  →  agents + you
```

- **Board** — Queued / Agent working / Waiting on you / Done. Click a card to see the
  thread, the diff, and message the agent.
- **Agents are teammates** — resumable CLI sessions: reply to an agent on its task and it
  picks up exactly where it left off. Every run records the exact prompt, a trace, and
  the git diff of what it changed.
- **Timeline feed** — every inbound item, one clean row, with its routing decision
  (`GET /api/feed`; a dedicated UI view is on the roadmap).
- **Operator documents** — `soul` (what is a task, how to respond) and `coder` (what an
  agent may do alone vs. must escalate): plain markdown injected into every run, editable
  via `GET/PUT /api/doc/{name}`. The agent's constitution is yours to edit.
- **Deterministic guardrails** — policy rules (ignore / escalate / auto-answer) that no
  model confidence can override, a learned-memory layer fed by your verdicts, and a
  hash-chained audit log (`GET /api/audit/verify` proves it's untampered).
- **Local first** — SQLite in `~/.taskuary`, server bound to 127.0.0.1. For LAN use, set
  `[server].token` in config and send it as the `X-Taskuary-Token` header. Your data and
  your agent sessions never leave the machine unless you point them somewhere.

## Bring your own agent

Any CLI that reads a prompt on stdin works — `claude`, `codex`, `gemini`, your own
wrapper. Add it in **Settings → Agents**, no config files:

| field | what it does |
|-------|--------------|
| cmd | the CLI to run, e.g. `claude` |
| args | flags for a headless run, e.g. `-p --output-format json` |
| resume args | e.g. `--resume` — enables message-the-agent session continuity |
| timeout | max seconds per run |
| repo → dir map | which local checkout the agent works in per repo |

Claude Code's JSON output (`result`, `session_id`) is parsed natively; plain-text CLIs
work too (you lose resumability, keep everything else).

## Integrations (report connections)

Scheduled pulls from the systems you already have; results land on the timeline feed as
informational rows (never tasks). All point-and-click in **Settings → Report
connections** — pick a type, fill the form, **Test connection**, **Preview**, save.
Every connection also takes `title` plus a schedule (`every_minutes` or `daily_at`).

| type            | status      | config keys                          |
|-----------------|-------------|--------------------------------------|
| `mssql`         | ✅ built-in | `server`, `database`, `auth` (windows/sql), `username`, `password`, `driver` (auto-picks newest installed), `query` — local SQL Server via Windows auth works out of the box; needs `pip install taskuary[mssql]` for pyodbc |
| `mcp`           | ✅ built-in | `cmd`, `args`, `tool`, `tool_args`, `env` — **any MCP server is a connector**: Taskuary speaks stdio JSON-RPC, lists the server's tools (Test connection), calls one on schedule |
| `sqlite`        | ✅ built-in | `db`, `query`                        |
| `rest`          | ✅ built-in | `url`, `headers`, `path`             |
| `rss`           | ✅ built-in | `url`                                |
| `postgres`      | 🗺 planned  |                                      |
| `mysql`         | 🗺 planned  |                                      |
| `snowflake`     | 🗺 planned  |                                      |
| `sharepoint_list` | 🗺 planned |                                     |
| `google_sheets` | 🗺 planned  |                                      |
| `s3_object`     | 🗺 planned  |                                      |
| `graphql`       | 🗺 planned  |                                      |
| `smb_file`      | 🗺 planned  |                                      |
| `prometheus`    | 🗺 planned  |                                      |
| `jira`          | 🗺 planned  |                                      |

Executors are ~15-line functions in `taskuary/reports.py` — `(config) -> (headline,
summary)`. PRs welcome; a planned type is one function away from ✅. (Planned types fail
loudly on the feed instead of silently doing nothing — a misconfig is always visible.)

Anything can also **push** items in: `POST /api/ingest/push` with
`{subject, body, from_email, channel}` — cron jobs, webhooks, other apps. The full HTTP
API is browsable at `/api/docs` (OpenAPI) while the server runs.

## GitHub loop (optional)

Set `[github].token` (a fine-grained PAT) and `default_repo` in config, and coding tasks
open an issue first (the issue body is the working prompt), the agent works it, and
closing the task closes the issue with the report. Diffs from the run are attached
either way.

## Status / roadmap

Early (v0.1.0). The engine (store, triage, policies, agents, sessions, diffs, reports,
audit) and the HTTP API are here, with a built-in web UI for the board and settings.

- [x] Settings UI (agents · report connections · app settings) — all point-and-click
- [x] Desktop app (`taskuary-desktop`, single-exe PyInstaller build)
- [x] Microsoft SQL Server + MCP report connectors
- [x] Test suite + CI (Windows/Linux, py3.10/3.12, exe build)
- [ ] Timeline + review + operator-docs views in the UI (feed/reviews/docs are API-only today)
- [ ] Full React UI port (drag-and-drop board)
- [ ] Git worktree isolation per task attempt (vibe-kanban-style)
- [ ] Tray + notifications for the desktop shell
- [ ] Email/chat ingest plugins (IMAP, Graph, Slack)
- [ ] More report executors (table above)

## Credits

Patterns borrowed with gratitude from **Buzz** (hash-chained audit), **Macro** (unified
memory / augment-don't-replace), and **vibe-kanban** (local-server app model, agents in
worktrees). MIT licensed.

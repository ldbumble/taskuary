# Taskuary

[![CI](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml/badge.svg)](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://github.com/ldbumble/taskuary)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**Automate your job.** Taskuary is a local-first, open-source AI task hub: email, Teams,
Slack, and scheduled reports stream into one timeline, AI triage decides what matters,
and your own coding agents — Claude Code, Codex, Gemini, Cursor, Copilot — do the work
while you approve the results.

![The Taskuary timeline: every inbound item on a day rail, with the AI-drafted reply ready to approve](docs/screenshot-timeline.png)

- **Everything in, one timeline.** Mail, Teams, Slack, and scheduled reports land on one
  day-rail feed. AI triage decides what is a real task, what just needs a reply, and
  what is noise. No AI connected yet? Nothing is lost — items file quietly until you add one.
- **Agents do the work.** Point Taskuary at the coding CLI you already use — Claude
  Code, Codex, Gemini, Cursor, Copilot — and tasks flow to it: it works in your repos,
  reports back with the diff, and you can message it mid-task (it resumes its session).
- **You stay in charge.** AI-drafted replies wait for your approve / edit / reject. A
  kanban board shows every agent's live status. Deterministic policy rules the AI can
  never override, and a tamper-evident audit log of everything.

## Get started

```bash
pip install git+https://github.com/ldbumble/taskuary
taskuary        # opens http://127.0.0.1:7787
```

Python 3.10+ is the only requirement. Then open **Connectors** and click through the
wizards — each one takes a minute or two:

1. **AI** — paste an Anthropic / OpenAI / Azure OpenAI key. This turns on triage.
2. **A channel** — Outlook, Teams, or Slack, so inbound lands on your Timeline.
3. **A coding agent** — pick a preset (Claude Code, Codex, Gemini, Cursor, Copilot),
   Save, Test. Add GitHub (paste a PAT — repos auto-discovered) for the full
   issue → work → report → close loop.
4. Then build **Reports**: connect SQL Server once (or use MCP / SQLite / REST / RSS)
   and schedule queries with an AI prompt that summarizes the results onto your Timeline.

Prefer a desktop app? `pip install "taskuary[desktop] @ git+https://github.com/ldbumble/taskuary"`
then `taskuary-desktop` — the same UI in a native window. A prebuilt single-file
`Taskuary.exe` is attached to every CI run.

## The workspace

- **Timeline** — every inbound item on a day-grouped rail: who/where, what Taskuary did
  with it, current state. Filter by state (everything / needs me) and channel
  independently. Click a row for the full review canvas — message, agent report, code
  diff, history — and decide inline. Chains holding several emails get a pill strip to
  flip between them (your own replies marked "↩ you"). **Send to coding agent** on any row
  hands that item — a failed report, an email, a chat — to a CLI agent with your own
  prompt; it becomes a task carrying the full message as context.
- **Board** — the agent kanban: Queued / Agent working / Waiting on you / Done. Cards
  working right now show a **live peephole** — the last lines of the agent's console —
  and open into the full trace. Drag between columns; "New task for the agent" sends work
  straight to the CLI you pick.
- **Tasks** — the dense two-pane view: messages with routing decisions, agent runs with
  prompts, traces and diffs, dispatch any agent, message the working agent, "Not a task"
  (which teaches the funnel).
- **Review** — the decision queue: approve / approve-my-edit / no-reply / reject, plus
  Draft-with-AI. Nothing sends without you.
- **Reports** — the pipeline builder: source → query → optional AI summary → Timeline,
  on a schedule, with a full-pipeline Preview before you save.
- **Terminal** — your coding CLI, for real, inside the app: a pseudo-terminal (ConPTY on
  Windows) streamed to xterm.js over a websocket. The agent's own TUI, its approval
  prompts, your keystrokes — the session, not a transcript of one. Open one on a task
  ("start it on this task" types the context in for you) or a bare shell in any repo.
- **Connectors** — a searchable catalog of connections with a setup wizard per card: AI
  models and CLI agents, messaging channels, GitHub, SQL Server. Every connection has a
  **role** you choose: *inbound trigger* (its items land on the Timeline and go through
  triage), *report source* (query it on a schedule), *agent tool* (the agents may read
  from it and create things in it). Mail and chat trigger by default; GitHub starts as a
  tool — flip its trigger on and new issues become timeline items and tasks like anything
  else. Nothing polls a connection you didn't make a trigger.
- **Docs** — the operator documents (SOUL.md / CODER.md / DIGEST.md): plain-markdown
  rules injected into every agent run. They ship as templates and maintain themselves —
  connectors and discovered repos write themselves in.
- **Settings** — triage knobs with plain-English help, deterministic routing policies
  (including **skip** rules for flood senders — one click on the Timeline mutes a sender
  forever), the agent's learned memory, and one-click audit-chain verification.

## One brain or two

Intent triage (task / reply-only / FYI) runs on whichever brain you pick in Settings →
Triage & routing: a cloud key (Anthropic, OpenAI, Azure OpenAI), or **your coding CLI
itself** — the same agent that works the tasks also classifies the inbox, so there is no
second API key and no second bill. Cloud keys answer in milliseconds; a CLI run takes
seconds and spends agent tokens. Obvious automated noise is filtered by heuristics before
either is called.

The other direction works too: a connection marked *agent tool* is named for the agents in
SOUL.md along with `POST /api/tools/run` — one call runs a query, script, or MCP tool
through the saved credentials and hands the raw output back, so an agent working a task
can look something up in SQL Server or act in another system without leaving the run.

## Bring your own agent

Any CLI that reads a prompt on stdin works. The presets ship the right headless flags —
the important one being the auto-approve flag (`--dangerously-skip-permissions`,
`--full-auto`, `--yolo`, …): without it a headless agent hangs waiting for an approval
click that never comes. The built-in **Test** runs one tiny prompt through your CLI to
prove the wiring before it goes live. Claude Code's JSON output is parsed natively,
which enables resumable message-the-agent sessions; plain-text CLIs work too.

## Integrations

| type | status | notes |
|------|--------|-------|
| `outlook` / `teams` / `slack` | ✅ | inbound channels → Timeline through AI triage |
| `github` | ✅ | PAT → auto repo discovery, issue loop, repo map in SOUL.md; optional inbound trigger (new issues → Timeline → triage) |
| `anthropic` / `openai` / `azure_openai` | ✅ | AI for triage + report summaries |
| `mssql` | ✅ | connect once; build AI-summarized reports on the Reports tab |
| `winrm` | ✅ | run PowerShell on any machine you can RDP into; output → Timeline |
| `mcp` | ✅ | any MCP server's tool as a scheduled report |
| `sqlite` / `rest` / `rss` | ✅ | scheduled reports, AI summaries optional |
| `postgres` `mysql` `snowflake` `sharepoint_list` `google_sheets` `s3_object` `graphql` `smb_file` `prometheus` `jira` | 🗺 planned | one ~15-line executor away — PRs welcome |

Anything can also **push** items in: `POST /api/ingest/push` with
`{subject, body, from_email, channel}` — cron jobs, webhooks, other apps. The full API is
browsable at `/api/docs` while the server runs.

## Development

```bash
git clone https://github.com/ldbumble/taskuary && cd taskuary
pip install -e .[dev,mssql,desktop]
taskuary --debug            # verbose console; every run also logs to ~/.taskuary/taskuary.log

pytest -q                   # 74 tests, ~2s, no network needed

cd website                  # the React UI (React 18 + MUI, Vite)
npm install
npm run dev                 # dev server, proxies /api to a running taskuary on :7787
npm run build               # emits taskuary/web/ (committed - pip installs need no node)

pip install -e .[build]
pyinstaller taskuary.spec   # dist/Taskuary.exe - single-file desktop build
```

Data lives in `~/.taskuary/` (override with `TASKUARY_HOME`): `taskuary.db` (SQLite),
`config.toml`, `taskuary.log`. For LAN use set `[server].token` in config and send it as
the `X-Taskuary-Token` header. CI runs the test matrix on Windows / Linux / macOS ×
py3.10 / 3.12 plus the web and exe builds on every push.

## Status / roadmap

Early (v0.2.0) and moving fast.

- [x] AI-gated triage, review queue, resumable agent sessions, hash-chained audit
- [x] Reports tab: source → query → AI summary → Timeline pipelines
- [x] Connectors catalog with setup wizards: channels, AI, GitHub, SQL Server
- [x] Agent presets (Claude Code, Codex, Gemini, Cursor, Copilot) with one-click Test
- [x] Desktop app + single-file Windows exe
- [x] Interactive agent terminal (pty + websocket + xterm.js) and hand-anything-to-an-agent
- [ ] Git worktree isolation per task attempt
- [ ] More ingest channels and report connectors (table above)
- [ ] Tray + notifications for the desktop shell

## Contributing

The single best first PR is a **report connector — ~15 lines** turns any system
(Postgres, Google Sheets, Jira, Prometheus…) into an AI-summarized Timeline report.
[CONTRIBUTING.md](CONTRIBUTING.md) has the recipe, the repo map, and the dev setup;
[good first issues](https://github.com/ldbumble/taskuary/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
are seeded and waiting. Tests run offline in ~2 seconds — no credentials needed to hack
on the funnel.

## Credits

Patterns borrowed with gratitude from **Buzz** (hash-chained audit), **Macro** (unified
memory), and **vibe-kanban** (local-server app model, agents in worktrees). MIT licensed.

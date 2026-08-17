# Taskuary

**Automate Your Work.**

Buzz/Macro-style, task-driven agent work over your **existing systems** — fully local,
nothing assumed, bring your own AI CLI.

Everything inbound becomes one timeline. Real work becomes tasks on a kanban board.
Coding agents (Claude Code, Codex, or any CLI you configure) pick tasks up, work them in
your repos, report **triage → determination → actions → reply**, show you the **diff**,
and stay **resumable** — message an agent mid-task and it continues the same session.
You review; nothing sends or ships without you.

```
pip install git+https://github.com/ldbumble/taskuary
taskuary          # starts locally on 127.0.0.1:7787 and opens the app
```

## Why

Your work already lives in systems — email, chat, databases, GitHub, dashboards. You don't
need another place to *put* work; you need one place where work **arrives, gets triaged,
gets done by agents, and gets reviewed by you**. Taskuary is that funnel:

```
anything in  →  one timeline  →  triage (task / reply-only / FYI)  →  agents + you
```

- **Timeline** — every inbound item as one clean line; hover for the full story.
- **Board** — Queued / Agent working / Waiting on you / Done. Drag, click, message.
- **Agents are teammates** — resumable CLI sessions: reply to an agent on its task and it
  picks up exactly where it left off. Every run records the exact prompt, a trace, and
  the git diff of what it changed.
- **Operator documents** — SOUL.md (what is a task, how to respond), CODER.md (what an
  agent may do alone vs. must escalate), DIGEST.md (rolling memory). Plain markdown, in
  the UI, injected into every run. The agent's constitution is yours to edit.
- **Deterministic guardrails** — policy rules (ignore / escalate / auto-answer) that no
  model confidence can override, a learned-memory layer fed by your verdicts, and a
  hash-chained audit log of everything.
- **Local first** — SQLite in `~/.taskuary`, server bound to 127.0.0.1. Your data and your
  agent sessions never leave the machine unless you point them somewhere.

## Bring your own agent

Agents are rows in config — any CLI that reads a prompt on stdin works:

```toml
# ~/.taskuary/config.toml
[agents.coder]
cmd  = "claude"                 # or "codex", "gemini", your own wrapper...
args = ["-p", "--dangerously-skip-permissions", "--output-format", "json"]
resume_args = ["--resume"]      # enables message-the-agent session continuity
timeout = 1500

[agents.coder.cwd_map]          # repo -> local checkout the agent works in
"you/your-repo" = "C:/src/your-repo"
```

Claude Code's JSON output (`result`, `session_id`) is parsed natively; plain-text CLIs
work too (you lose resumability, keep everything else).

## Integrations (report connections)

Schedule pulls from the systems you already have; results land on the timeline as
informational rows (never tasks) — headline visible, hover for the summary.

| type            | status      | config keys                          |
|-----------------|-------------|--------------------------------------|
| `sqlite`        | ✅ built-in | `db`, `query`                        |
| `rest`          | ✅ built-in | `url`, `headers`, `path`             |
| `rss`           | ✅ built-in | `url`                                |
| `mssql`         | ✅ extra    | `pip install taskuary[mssql]` · `dsn`, `query` |
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
summary)`. PRs welcome; a planned type is one function away from ✅.

Anything can also **push** items in: `POST /api/ingest/push` with
`{subject, body, from_email, channel}` — cron jobs, webhooks, other apps.

## GitHub loop (optional)

Give it a fine-grained PAT and coding tasks open an issue first (the issue body is the
working prompt), the agent works it, and closing the task closes the issue with the
report. Diffs from the run are attached either way.

## Status / roadmap

Early. The engine (store, triage, policies, agents, sessions, diffs, reports, audit) and
the HTTP API are here with a minimal built-in web UI. Coming next:

- [ ] Full React UI port (timeline · board · review · docs · settings)
- [ ] Git worktree isolation per task attempt (vibe-kanban-style)
- [ ] Tauri desktop shell (tray, notifications)
- [ ] Email/chat ingest plugins (IMAP, Graph, Slack)
- [ ] More report executors (table above)

## Credits

Patterns borrowed with gratitude from **Buzz** (hash-chained audit), **Macro** (unified
memory / augment-don't-replace), and **vibe-kanban** (local-server app model, agents in
worktrees). MIT licensed.

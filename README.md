# Taskuary

[![CI](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml/badge.svg)](https://github.com/ldbumble/taskuary/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://github.com/ldbumble/taskuary)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**Your inbox and your coding agents in one place.** Email, Teams, Slack, GitHub issues and
scheduled reports land on one timeline; AI triage says what is real work; the coding CLI
you already use does it; you approve the result. Runs entirely on your machine.

![The Taskuary timeline: every inbound item on a day rail, with the AI-drafted reply ready to approve](docs/screenshot-timeline.png)

## Why

Work arrives as messages, but work *is* tasks — and you are the translation layer. You
read the mail, decide what it means, open the ticket, do the thing, and write back. The
first and last steps are where the day goes.

Taskuary automates the ends and leaves you the middle. Triage reads everything and files
the noise. Real work becomes a task and goes to your agent, which works in your repos and
reports back with the diff. Replies come back as drafts. Nothing sends, closes, or ships
without you — and nothing leaves your machine except the calls you configured.

## Get started

```bash
pip install git+https://github.com/ldbumble/taskuary
taskuary        # opens http://127.0.0.1:7787
```

Python 3.10+ is all you need. Then, in **Connectors** — a minute or two each:

1. **AI** — paste an Anthropic / OpenAI / Azure OpenAI key. Triage is now on. (A small,
   cheap model is the right pick here; the expensive one goes in step 3.)
2. **A channel** — Outlook, Teams, or Slack. Mail starts landing on the Timeline.
3. **Your coding CLI** — pick a preset (Claude Code, Codex, Gemini, Cursor, Copilot), Save,
   Test. Add a GitHub PAT and repos are discovered for you.
4. **Reports** (optional) — point at SQL Server / MCP / SQLite / REST / RSS and schedule a
   query with an AI prompt; the summary lands on your Timeline.

No cloud key at all? Set **Settings → Triage & routing → Triage brain** to your CLI agent
and skip step 1 — one brain does everything, slower and pricier per message. See
[One brain or two](#one-brain-or-two).

Prefer a desktop app? `pip install "taskuary[desktop] @ git+https://github.com/ldbumble/taskuary"`
then `taskuary-desktop` — the same UI in a native window. A prebuilt single-file
`Taskuary.exe` is attached to every CI run.

## The workspace

- **Timeline** — every inbound item on a day-grouped rail: who/where, what Taskuary did
  with it, current state. Filter by state (everything / needs me) and channel
  independently. Click a row for the full review canvas — message, agent report, code
  diff, history — and decide inline. Mail is stored whole (not Graph's 255-char preview)
  and shown the way you'd read it: an *inbound* / *↩ your reply* marker, the new text
  first, and the thread quoted underneath folded behind one click. Chains holding several
  emails get a pill strip to flip between them. **Send to coding agent** on any row
  hands that item — a failed report, an email, a chat — to a CLI agent with your own
  prompt; it becomes a task carrying the full message as context.
- **Board** — the agent kanban: Queued / Agent working / Waiting on you / Done. Cards
  working right now show a **live peephole** — the last lines of the agent's console —
  and open into the full trace. Drag between columns; "New task for the agent" takes a
  task name, the **prompt** that becomes the agent's instruction, and which **CLI and
  model** run it.
- **Tasks** — the dense two-pane view: messages with routing decisions, agent runs with
  prompts, traces and diffs, message the working agent, "Not a task" (which teaches the
  funnel). One **Run agent** control — agent, model, an optional prompt — starts work;
  behind it runs the whole lifecycle (issue → work → report → close or escalate).
- **Review** — the decision queue: approve / approve-my-edit / no-reply / reject, plus
  Draft-with-AI. Nothing sends without you.
- **Reports** — a funnel you lay out: **any number of sources at the top** (the same
  connection twice with different SQL is fine — drag to reorder, one click to duplicate)
  feeding **one prompt at the bottom**, then the schedule. Every source's rows reach the
  summary together, each under its own label, and a source that fails is reported in place
  instead of killing the report. Preview runs the whole pipeline before you save. **max
  rows** (default 200, per source) decides how much reaches the summary, and the headline
  says *capped* when rows were left behind — so the AI never calls a truncated slice "all
  of them".
- **Terminal** — your coding CLI, for real, inside the app: a pseudo-terminal (ConPTY on
  Windows) streamed to xterm.js over a websocket. The agent's own TUI, its approval
  prompts, your keystrokes — the session, not a transcript of one. It lives in a **dock at
  the bottom of every tab** (Ctrl+\` to toggle, drag its top edge to resize, tabs for
  parallel sessions) as well as its own full-screen tab; hiding it never kills a session,
  because the pty lives server-side. Sessions start clean — no inherited agent session
  state. Every **task page embeds its own session** — the agent's TUI right under the run
  history — or open a bare shell in any repo.
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
- **Settings** — triage knobs with plain-English help (including which brain does the
  triage), deterministic routing policies, the agent's learned memory, and one-click
  audit-chain verification. **Skip** rules mute flood senders in both directions: one
  click on the Timeline hides that sender's future mail *and* their back catalogue, and
  switching the rule off puts the history back.

## One brain or two

**Two is the recommended setup**, and they do different jobs:

| | Triage brain | Working brain |
|---|---|---|
| what it does | classifies every inbound message: task / reply-only / FYI | writes the code, drafts the replies, works the task |
| what it is | a small cloud model (Anthropic / OpenAI / Azure OpenAI key) | your CLI agent (Claude Code, Codex, Gemini…) |
| per message | well under a second, a fraction of a cent | seconds to minutes, real agent tokens |

**One brain works too.** Set Settings → Triage & routing → **Triage brain** to a CLI agent
and the same brain that writes your code also triages your inbox — no second API key, no
second bill. The cost is speed and tokens: every message that reaches the AI spawns a CLI
run, which adds up fast on a busy mailbox. Obvious automated noise is filtered by
heuristics before either brain is called.

The other direction works too: a connection marked *agent tool* is named for the agents in
SOUL.md along with `POST /api/tools/run` — one call runs a query, script, or MCP tool
through the saved credentials and hands the raw output back, so an agent working a task
can look something up in SQL Server or act in another system without leaving the run.

## Bring your own agent — and pick its model

Every run surface (Board dialog, task page, "send to coding agent") asks two questions:
**which CLI** works it, and **which model** that CLI runs. The model list comes from the
CLI — `opus` / `sonnet` / `haiku` and the full `claude-*` ids for Claude Code, the
`gpt-5-codex` family for Codex, and so on — and "the agent's default model" leaves it to
the profile. Under the hood it is one flag appended to the command (`--model` by default,
`model_arg` if your CLI spells it differently), so a per-run choice never edits your saved
profile.

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

pytest -q                   # 97 tests, ~20s, no network or credentials needed

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
- [x] Per-connection roles (trigger / report / tool), GitHub issues as an inbound trigger
- [x] Configurable triage brain — a cloud key or your CLI agent — and `/api/tools/run`
- [ ] Git worktree isolation per task attempt
- [ ] More ingest channels and report connectors (table above)
- [ ] Tray + notifications for the desktop shell

## Contributing

The single best first PR is a **report connector — ~15 lines** turns any system
(Postgres, Google Sheets, Jira, Prometheus…) into an AI-summarized Timeline report.
[CONTRIBUTING.md](CONTRIBUTING.md) has the recipe, the repo map, and the dev setup;
[good first issues](https://github.com/ldbumble/taskuary/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
are seeded and waiting. Tests run offline in ~2 seconds — no credentials needed to hack
on the funnel. Please read the [Code of Conduct](CODE_OF_CONDUCT.md); security issues go
through [SECURITY.md](SECURITY.md), not a public issue.

## Looking for collaborators

Taskuary is early and I'd rather build it with people than alone. I'm looking for a few
regulars, not one-off drive-bys — though a single good PR is very welcome too.

**Where help goes furthest right now:**

- **Connectors** — every row marked 🗺 in the table above, plus whatever system runs *your*
  day. One executor function and you own that integration.
- **Non-Windows polish** — the terminal, desktop shell, and agent presets get the most
  testing on Windows. macOS and Linux users who hit rough edges (and fix them) are gold.
- **Agent CLIs beyond the presets** — if your CLI needs different flags to run headless,
  that's a preset PR and a paragraph in the README.
- **Design and UX** — this was built by one person with strong opinions and no designer.
  Argue with them.
- **Real-world war stories** — run it on your own inbox for a week and open an issue about
  what broke, what felt wrong, or what you kept doing by hand anyway. That feedback shapes
  the roadmap more than feature requests do.

Want a bigger piece? Say so in an issue — worktree isolation, a notifications/tray shell,
and a plugin API for connectors are all on the roadmap and all up for grabs. Interested in
maintaining an area long-term? Open an issue titled `maintainer: <area>` and let's talk.

## Credits

Patterns borrowed with gratitude from **Buzz** (hash-chained audit), **Macro** (unified
memory), and **vibe-kanban** (local-server app model, agents in worktrees). MIT licensed.

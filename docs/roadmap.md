# Status and roadmap

Taskuary is early—currently v0.3.9.51—and moving fast. The core funnel, review queue, agent
sessions, and reports pipeline are real and in daily use. Breaking changes remain possible
before 1.0.

## Available today

- AI-gated triage with a review queue and hash-chained audit history
- Resumable, live-streamed coding-agent sessions in the user's own repositories
- General-work assistant sessions with interchangeable assistant-ui and terminal views,
  persistent task conversation, queue, image attachments, and the shared browser pane
- Claude Code, Codex, Gemini, Cursor, Copilot, and Muse Code presets with connection tests
- Timeline, task Board, Studio floor, and multi-terminal Wall
- Assistant posts with evidence, actions, reviewed material, and cross-check notes
- Scheduled report pipelines from source to query, AI summary, spreadsheet, chart, and Timeline
- Plain-English report building against real connected schemas, with preview before save
- Inbound mail, chat, code-host, work-tracker, incident, and monitoring connectors
- Data sources spanning databases, AWS, Azure, Prometheus, Datadog, Sage Intacct, REST, RSS, and MCP
- Per-connection trigger, feed, report, and tool roles
- Configurable cloud, CLI, or local-model triage brains
- Self-learning triage through evidence-backed verdicts in `LEARNED.md`
- Goals as tasks: a task whose checklist boxes are tasks, a person as an assignee, a promise in
  sent mail as a task on the owner with its day, one row per goal on the rail
- An outcome ledger of what came after each action, resolved daily from the store's own facts
  and read by reflection as evidence for habits
- History-generated `TRIAGE.md` and `STYLE.md` guidance from the user's own mailbox
- Calendar-aware reply drafting
- Proof of work on reviews: changed files, tests, CI, attempts, and missing evidence
- Approval-gated high-impact actions such as sending, pushing, commenting, or closing
- Desktop app, single-file Windows executable, Python package, and Docker image

## Next

- Follow-up tracking as a first-class state for replies and handoffs that are owed an answer
- The Advisor on the event: one small prompt when an item changes, a pill in the prompt box
  ("Merge it · 8 of 8 times"), and a receipt of what it looked at and dropped
- Per-person pages derived from the ledger, with a per-person chase ladder
- Earned, revocable autonomy for patterns with enough unchanged approvals
- Teams as a phone-approval channel alongside Telegram and WhatsApp
- Additional finance, HR, healthcare, and report connectors listed in
  [Integrations](integrations.md)
- Desktop tray controls and native notifications
- A connector plugin API

## Under discussion

Bigger steps, each with a GitHub Discussion where the shape is being worked out:

- Record a job on screen once and turn the recording into a playbook
  ([#179](https://github.com/ldbumble/taskuary/discussions/179)) — the nearest of the three
- Computer use inside a sandboxed desktop, for the systems that have no API
  ([#178](https://github.com/ldbumble/taskuary/discussions/178))
- Outbound phone calls as approval-gated work: the agent proposes the brief, places the call,
  files the receipt ([#180](https://github.com/ldbumble/taskuary/discussions/180))

The active release history is on
[GitHub Releases](https://github.com/ldbumble/taskuary/releases), and current work is tracked
in [GitHub Issues](https://github.com/ldbumble/taskuary/issues).

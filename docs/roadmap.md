# Status and roadmap

Taskuary is early—currently v0.3.1—and moving fast. The core funnel, review queue, agent
sessions, and reports pipeline are real and in daily use. Breaking changes remain possible
before 1.0.

## Available today

- AI-gated triage with a review queue and hash-chained audit history
- Resumable, live-streamed coding-agent sessions in the user's own repositories
- Claude Code, Codex, Gemini, Cursor, and Copilot presets with connection tests
- Timeline, task Board, Studio floor, and multi-terminal Wall
- Assistant posts with evidence, actions, reviewed material, and cross-check notes
- Scheduled report pipelines from source to query, AI summary, spreadsheet, chart, and Timeline
- Plain-English report building against real connected schemas, with preview before save
- Inbound mail, chat, code-host, work-tracker, incident, and monitoring connectors
- Data sources spanning databases, AWS, Azure, Prometheus, Datadog, Sage Intacct, REST, RSS, and MCP
- Per-connection trigger, feed, report, tool, and notification roles
- Configurable cloud, CLI, or local-model triage brains
- Self-learning triage through evidence-backed verdicts in `LEARNED.md`
- History-generated `TRIAGE.md` and `STYLE.md` guidance from the user's own mailbox
- Calendar-aware reply drafting
- Proof of work on reviews: changed files, tests, CI, attempts, and missing evidence
- Approval-gated high-impact actions such as sending, pushing, commenting, or closing
- Desktop app, single-file Windows executable, Python package, and Docker image

## Next

- Follow-up tracking as a first-class state for replies and handoffs that are owed an answer
- Earned, revocable autonomy for patterns with enough unchanged approvals
- Teams as a phone-approval channel alongside Telegram and WhatsApp
- Additional finance, HR, healthcare, and report connectors listed in
  [Integrations](integrations.md)
- Desktop tray controls and native notifications
- A connector plugin API

The active release history is on
[GitHub Releases](https://github.com/ldbumble/taskuary/releases), and current work is tracked
in [GitHub Issues](https://github.com/ldbumble/taskuary/issues).

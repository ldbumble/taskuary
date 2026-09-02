# Integrations

Connector roles determine what Taskuary may do with a system:

Each connector card is one named connection. Rename it for the account or environment it
represents, and use **Add another** on the card to connect the same kind again—for example,
two IMAP mailboxes, two GitHub organizations, or separate production and staging databases.

- **trigger** sends inbound items through triage
- **feed** displays inbound items without triage
- **report** makes the source available to scheduled reports
- **tool** allows agents to query it
- **notify** lets Taskuary send notifications to it

Nothing is polled without an enabled role.

## Channels and work systems

| Integration | Status | Notes |
|---|---|---|
| Outlook | Available | Mail and calendar through Microsoft sign-in or a tenant app |
| Teams and Slack | Available | Messages enter the Timeline through AI triage |
| Gmail and IMAP | Available | Any IMAP mailbox; approved replies return through the provider's SMTP, in-thread |
| Telegram | Available | Bot-based inbound messages, approved in-chat replies, and optional phone notifications; each chat is opt-in |
| WhatsApp | Available | Local Baileys bridge for inbound messages, approved replies, and notifications; unofficial protocol, so use a number you can risk |
| Apple Messages | Available on macOS | Reads the Mac's local Messages history and replies through Messages.app; requires Full Disk Access and Automation permissions |
| Discord | Available | Watches selected bot channels and posts approved replies into the originating channel |
| GitHub | Available | Repository discovery, issues and pull requests as inbound triggers, and task-specific standing prompts |
| GitLab | Available | Assigned issues and merge requests from GitLab.com or a self-hosted instance |
| Jira, Asana, Monday.com, ClickUp, Todoist | Available | Assigned work items enter the Timeline through triage |
| Azure DevOps | Available | Work items assigned to the connected user through WIQL `@Me` |
| Linear and Trello | Available | Assigned issues and cards enter the Timeline through triage |
| Notion | Available | Pages shared with the integration appear as a feed when they change |
| Sentry and PagerDuty | Available | New unresolved errors and open incidents join the same funnel |

## AI providers and coding agents

| Integration | Status | Notes |
|---|---|---|
| Anthropic, OpenAI, Azure OpenAI | Available | Triage, drafts, report summaries, and Assistant runs |
| OpenRouter | Available | Hosted open and closed models through one API |
| Ollama | Available | Local models with no API key; the compatible base URL also supports LM Studio, llama.cpp, and vLLM |
| Claude Code, Codex, Gemini, Cursor, Copilot | Available | Presets for live coding sessions; custom stdin-based CLIs are supported too |
| Knowledge base | Available | Documents from SharePoint library folders and local folders (docx, pptx, xlsx, html, text; pdf with `pypdf`) indexed into Taskuary's own SQLite (FTS5) — a `kb_search` report and agent tool, a scheduled `kb_reindex`, and passages fed to the reply drafter, the assistant and coding sessions automatically |
| agent-browser (Vercel) | Optional | A local headless Chromium the coding agent drives from its terminal (`npm install -g agent-browser && agent-browser install`, Apache-2.0). When it is installed, the page the agent is on appears live beside the session (task page and Wall), with Take over for a password or 2FA code the agent must not type, and Snapshot to keep the frame on the task |

## Data and report sources

| Integration | Status | Notes |
|---|---|---|
| SQL Server | Available | Saved connection, report queries, and agent tools |
| Database connection string | Available | PostgreSQL, MySQL, Snowflake, Oracle, and other SQLAlchemy URLs; raw ODBC strings through pyodbc |
| AWS | Available | Discovers S3 buckets and CloudWatch log groups; each can be assigned report, feed, task, or off behavior; arbitrary service calls can be reports or tools |
| Azure | Available | Discovers blob containers and Log Analytics workspaces; supports arbitrary ARM paths and can reuse the Outlook app registration |
| Microsoft Entra ID | Available | People, transitive group membership, sign-in activity, and license usage when the connected app has permission |
| Prometheus and Datadog | Available | PromQL instant queries and Datadog monitor states |
| Sage Intacct | Available | Read-only XML gateway access for GL detail, AP bills, vendors, budgets, statistical accounts, and schema discovery. A source card can list the fields an object carries in your company, and the composer reads that list before writing a query |
| QuickBooks Online | Available | OAuth sign-in from the card. Bills, purchases, vendors and the chart of accounts as reports and agent tools (QBO's own query language), and the first system here an agent can post to: an AP bill or a paid expense. The card ships read-only, so a write is a proposal the owner approves in Review; raising the card to `write` lets a routing policy pass small, known bills through |
| WinRM | Available | Runs PowerShell on a remote Windows machine and returns output to the Timeline |
| MCP | Available | Uses an MCP server tool as a scheduled report source |
| SQLite, REST, RSS | Available | Scheduled reports with optional AI summaries |
| NetSuite, QuickBooks, SAP, Workday, ADP | Planned | Systems-of-record connectors |
| Epic, Cerner, PointClickCare | Planned | Healthcare systems-of-record connectors |
| SharePoint Lists, Google Sheets, GraphQL, SMB files | Planned | Additional report sources |

Connection secrets are write-only in the UI. A database string may contain `{password}` so
the saved password remains separate from the readable connection configuration.

## Push API

Any service can create an inbound item directly:

```http
POST /api/ingest/push
Content-Type: application/json

{
  "subject": "Nightly export failed",
  "body": "The export returned exit code 1.",
  "from_email": "scheduler@example.com",
  "channel": "automation"
}
```

The full interactive API reference is available at `/api/docs` while Taskuary is running.

## Related documentation

- [Getting started](getting-started.md)
- [Product guide](product-guide.md)
- [Reports and the Assistant](reports-and-assistant.md)
- [Status and roadmap](roadmap.md)

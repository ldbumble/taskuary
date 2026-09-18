A connection is one account Taskuary may read — a mailbox, a chat, a repository, a tracker, a
database, a bank feed. Each card on the **Connections** page is one named connection, and its
*roles* decide what Taskuary is allowed to do with what it finds there.

Nothing is polled without an enabled role. A card with no role is a saved credential and nothing
more.

## What a connection is

One card is one account, not one kind of system. Rename it for the account or environment it
represents — **Ops mailbox** rather than **IMAP** — and use **Add another** on the card to
connect the same kind again. Two mailboxes, two GitHub organisations, or separate production and
staging databases are all normal, and each keeps its own roles, its own schedule and its own name
in every prompt.

Secrets are write-only in the interface: you can replace a password, never read one back. A
database connection string may contain `{password}` so the saved password stays separate from the
readable part of the configuration.

## The five roles

A role is a permission, not a ranking.

| Role | What Taskuary may do |
|---|---|
| **trigger** | Send inbound items through triage — they can become tasks, drafts or FYIs |
| **feed** | Show inbound items on the Timeline, unread by any AI |
| **report** | Make the source available to scheduled reports |
| **tool** | Let agents query it while working a task |
| **notify** | Send notifications out through it |

:::rule Feed is not a quieter trigger
`feed` means no model ever reads those items — cheaper, quieter, and no verdict to argue with.
`ignore` is a judgement *about* a message and happens further down, in your routing policies. If
a source is noisy but you still want to see it, make it a feed.
:::

A card can hold more than one role. A mailbox is usually `trigger` and `notify`; a database is
usually `report` and `tool`.

## Mail

| System | Notes |
|---|---|
| **Outlook** | Mail and calendar, through Microsoft sign-in or a tenant app registration |
| **Gmail and IMAP** | Any IMAP mailbox. Approved replies go back through the provider's SMTP, in-thread |

Taskuary reads your **Sent** folder as well as your inbox. That is what makes "has this been
answered?" a real question rather than a guess, and it is what `STYLE.md`'s **Generate from
history** learns your writing voice from.

:::note A shared mailbox needs saying so
If the mailbox is shared, mail addressed to the team reads as mail addressed to you unless
Taskuary knows otherwise. Name your own addresses in `SOUL.md` so triage can tell "someone asked
me" from "someone asked the team".
:::

## Chat

| System | Notes |
|---|---|
| **Teams**, **Slack** | Messages enter the Timeline through triage |
| **Telegram** | Bot-based inbound, approved in-chat replies, optional phone notifications; each chat is opt-in |
| **WhatsApp** | A local bridge for inbound messages, approved replies and notifications. Unofficial protocol — use a number you can afford to lose |
| **Discord** | Watches selected bot channels and posts approved replies back into the originating channel |
| **Apple Messages** | macOS only. Reads the Mac's local Messages history and replies through Messages.app; needs Full Disk Access and Automation permissions |

Chat is different from mail in one way that matters: a chat message often has no clock on it.
"Can you look at this when you get a chance" is a real ask with no deadline, and Taskuary keeps
those as their own kind of item rather than inventing urgency for them. A greeting on its own is
held until the ask it opens arrives.

## Repositories and trackers

| System | Notes |
|---|---|
| **GitHub** | Repository discovery, issues and pull requests as triggers, task-specific standing prompts |
| **GitLab** | Assigned issues and merge requests, GitLab.com or self-hosted |
| **Azure DevOps** | Work items assigned to the connected user, through WIQL `@Me` |
| **Jira, Asana, Monday.com, ClickUp, Todoist** | Assigned work items enter the Timeline through triage |
| **Linear, Trello** | Assigned issues and cards |
| **Notion** | Pages shared with the integration appear as a feed when they change |
| **Sentry, PagerDuty** | New unresolved errors and open incidents join the same funnel |

A tracker is the clearest case for `trigger`: an issue assigned to you is, by definition, work
addressed to you, and triage settles most of them without an AI call at all.

## Data and report sources

The full list is long and grows; these are the ones worth knowing about by shape.

**Databases and files** — SQL Server, any SQLAlchemy URL (PostgreSQL, MySQL, Snowflake, Oracle),
raw ODBC through pyodbc, SQLite, SharePoint Lists, Google Sheets, a Windows/SMB share, SFTP, REST
and RSS, and any MCP server tool.

**Cloud and monitoring** — AWS (S3 buckets, CloudWatch log groups, arbitrary service calls),
Azure (blob containers, Log Analytics, arbitrary ARM paths, and it can reuse the Outlook app
registration), Microsoft Entra ID, Prometheus, Datadog, WinRM for PowerShell on a remote Windows
machine.

**Finance** — Sage Intacct, QuickBooks Online, Zoho Invoice, and bank and card feeds through
SimpleFIN or Teller. These are the cards where the read/write distinction bites: each ships at
`read`, so an agent proposes a bill or an invoice and you approve it in Review. Raising a card to
`write` is what lets a routing policy pass small, known items through without you.

**Markets** — Yahoo Finance, CoinGecko, Alchemy, ECB reference rates, SEC EDGAR filings, and a
strategy screen that filters another card's rows.

**Your own documents** — the **Knowledge base** card indexes SharePoint library folders and
folders on this machine (docx, pptx, xlsx, html, text, and pdf with `pypdf`) into Taskuary's own
SQLite. Once anything is indexed, a `kb_search` report answers questions from it on a schedule,
agents call the same search as a tool, and the reply drafter, the assistant and coding sessions
are handed the passages that bear on a thread. Passages are treated as facts to cite, never as
instructions.

:::warn Planned is not available
The Connections page lists cards that are on the roadmap as well as ones that work — NetSuite,
SAP, Workday, ADP, Epic, Cerner, PointClickCare, and a long tail of market-data providers. A
planned card tells you so on its face. If the assistant suggests connecting one, saying yes is a
vote for building it, not a connection.
:::

## Coding CLIs and AI providers

**AI providers** — Anthropic, OpenAI, Azure OpenAI, OpenRouter, Ollama (and any OpenAI-compatible
local server: LM Studio, llama.cpp, vLLM), and the Meta Model API.

**Coding CLIs** — Claude Code, Codex, Qwen Code, OpenCode, Kimi Code, Gemini, Cursor, Copilot,
Muse Code and Devin, plus any CLI that accepts a prompt on stdin. The connector defines its
command, arguments, model argument and working-directory behaviour.

Two practical notes. A headless agent needs its noninteractive or auto-approval flag, or it will
hang waiting for a click that cannot happen — the presets set this for you. And the card's
**Test** action runs a small prompt through the CLI before it ever receives real work, which is
the fastest way to find out that a sign-in expired.

Every CLI card has a **light model** as well as a main one. Naming the same CLI as both your
coder and your triage brain is normal and cheap, and it is the light gear that keeps it cheap.

## Adding another of the same kind

**Add another** on any card creates a second connection of that type with its own name,
credentials, roles and schedule. Use it for:

- a second mailbox, where one is yours and one is a shared team address;
- production and staging databases, so a report says which it read;
- two GitHub organisations, so repository discovery does not mix them.

Every prompt, report source and agent tool names the connection it used, so two cards of the same
type never become ambiguous downstream.

## Pushing something in yourself

Anything that can make an HTTP request can put an item on the Timeline:

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

It goes through triage exactly like anything else. The full interactive API reference is at
`/api/docs` while Taskuary is running.

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
| WhatsApp | Available | Local Baileys bridge for inbound messages, approved replies, notifications, and a private remote chat with the Taskuary guide; unofficial protocol, so use a number you can risk |
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
| Sage Intacct | Available | XML gateway access for GL detail, AP bills, vendors, budgets, statistical accounts, and schema discovery. Writing is the same gateway, generically by object: intacct_create makes a record (an AP bill, a vendor, a journal batch) and intacct_update changes one that names itself. The card ships at scope read, so an agent cannot post - it proposes the write and you approve it in Review, exactly as with a QuickBooks bill. A source card can list the fields an object carries in your company, and the composer reads that list before writing a query |
| QuickBooks Online | Available | OAuth sign-in from the card. Bills, purchases, vendors and the chart of accounts as reports and agent tools (QBO's own query language), and the first system here an agent can post to: an AP bill or a paid expense. The card ships read-only, so a write is a proposal the owner approves in Review; raising the card to `write` lets a routing policy pass small, known bills through |
| Zoho Invoice | Available | OAuth sign-in from the card. The Monthly Zoho invoices workflow copies prior invoices into editable monthly batches, creates drafts only after amounts are confirmed, and sends one customer at a time only after Review approval. A stable customer/month reference prevents duplicate creation on retries |
| Bank & card feed (SimpleFIN) | Available | The bank and card feed anyone can sign up for, and the one to reach for first: the owner links their banks at their own SimpleFIN Bridge account ($1.50/month or $15/year, billed to them), presses “Get a setup token” and pastes it into the card, which spends it once for a write-only access URL. No application to register, no approval, no client certificate. One token can carry several banks. simplefin_accounts, simplefin_transactions (newest first, with spend/inflow direction and pending flagged), simplefin_balances (each with the date it is as of) and simplefin_spend (per account and total over a window, headline leading with the total so a 'more than' alert compares dollars). Read-only because the protocol has no write verbs. Two limits shape how you schedule it: the bridge refreshes about once a day and allows 24 reads a day, so one cached response serves all four reports and the card refuses past 20 rather than letting the token be disabled |
| Bank & card feed (Teller) | Available | One card per bank login, enrolled in the browser with Teller Connect; accounts, transactions (newest first, with spend/inflow direction) and balances as reports and tools. Spend is a report of its own (teller_spend): per-card and total over a window, with a headline that leads with the total so a 'more than' alert compares dollars. Read-only by construction. Schedule the transactions with 'can become work' and each new one is a message triage judges — the front door of the card-to-books playbook. Development tier is free to 100 logins; development and production present Teller's client certificate. **Teller stopped taking new signups** (checked 2026-09-10: the login page still works, /signup is a 404 and dashboard.teller.io no longer resolves), so this card is for owners who already hold credentials — everyone else wants the SimpleFIN card above |
| Yahoo Finance (best-effort) | Available | Quotes and historical bars through an undocumented endpoint (v8/finance/chart) — Yahoo retired its official market-data API in 2017; this can change or break without notice. No key |
| CoinGecko | Available | Spot price and 24-hour change for any coin, by CoinGecko id; no key needed, an optional demo key raises the free rate limit |
| FX rates (Frankfurter) | Available | European Central Bank reference exchange rates; no key |
| SEC filings (EDGAR) | Available | A company's filings and its reported XBRL facts (e.g. Revenues) by CIK, straight from SEC EDGAR; no key. Schedule filings with 'can become work' and a new 8-K is a message triage judges |
| Strategy screen | Available | Filters another market card's rows to the ones matching a condition (e.g. change_pct <= -5); borrows that card's connection rather than holding its own — works over a Yahoo watchlist or CoinGecko prices today |
| WinRM | Available | Runs PowerShell on a remote Windows machine and returns output to the Timeline |
| MCP | Available | Uses an MCP server tool as a scheduled report source |
| SQLite, REST, RSS | Available | Scheduled reports with optional AI summaries |
| NetSuite, QuickBooks, SAP, Workday, ADP | Planned | Systems-of-record connectors |
| Epic, Cerner, PointClickCare | Planned | Healthcare systems-of-record connectors |
| Network file share (SMB) | Available | Documents on a Windows/SMB share, under one configured root: `smb_read` (a file, a folder listing newest-first, or a glob) plus `smb_write` and `smb_move` — the first connector that can FILE a document, including a mail's attachment by id. Ships at authority `read`, so a save is a proposal the owner approves until they raise the card |
| SFTP | Available | A vendor's or bank's server: `sftp_list`, `sftp_get` (stages the file and answers with its local path, which the share card accepts as a source), `sftp_put`, `sftp_move`. Needs `paramiko` (bundled in the desktop build); the host key must match the card's fingerprint and is never auto-accepted |
| SharePoint Lists, Google Sheets | Available | A list's items or a csv/xlsx in a document library as rows; a Google Sheet's cells as rows |
| GraphQL | Planned | Additional report source |
| Stooq | Planned | Its CSV endpoint now serves a JavaScript proof-of-work challenge a REST client cannot pass (checked 2026-09-08), so it stays planned rather than quietly broken |
| Finnhub, Alpha Vantage, Twelve Data, Tiingo, FMP, Polygon, FRED, Alpaca, Plaid, Interactive Brokers, Schwab, Tradier, Robinhood, EODHD, Marketstack, Intrinio, Benzinga | Planned | Market-data and brokerage providers awaiting an API key nobody has supplied yet |

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

// Connectors, Stripe-style like Settings: a searchable landing of grouped category cards
// (AI · Messaging · Developer · Local & data), each drilling into a detail page with a
// setup WIZARD (stepper) plus Sources/management. All connectors live here - channel
// connectors (Outlook, Teams, Slack, GitHub), cloud AI APIs (Anthropic, OpenAI, Azure
// OpenAI - wired into intent triage), AI CLI agents, and scheduled report connections.
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, Button, CircularProgress, InputAdornment, MenuItem, Radio, Select, Step, StepButton,
  StepContent, Stepper, Switch, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import BoltIcon from "@mui/icons-material/Bolt";
import SearchIcon from "@mui/icons-material/Search";
import SyncIcon from "@mui/icons-material/Sync";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import TerminalIcon from "@mui/icons-material/Terminal";
import api from "./api";
import { PANEL2, BORDER, DIM, FAINT, INK, mono } from "./theme.jsx";
import { ChannelIcon, StatusDot, timeAgo, Crumb, UnderTabs, LandingCard, Empty, FilterPills, ConfirmDelete } from "./ui.jsx";
import { CAN_NOTIFY } from "./notify.js";
import { hasLogo } from "./logos.jsx";
import { AgentsPage } from "./AgentsPanel.jsx";

/* ── connector metadata: channel + AI connectors (rows in the connector table) ── */
const META = {
  outlook: { group: "Messaging", channel: "email", srcLabel: "Mailboxes", srcPh: "someone@yourdomain.com",
    fields: [["tenant_id", "tenant_id"], ["client_id", "client_id"],
],
    secretLabel: "client secret",
    desc: "Ingest mailboxes through a Microsoft Graph app - mail lands on the Timeline through triage.",
    howto: ["Register (or reuse) an Azure app: Azure Portal → App registrations → New registration.",
      "API permissions → add the APPLICATION permission Mail.Read (Microsoft Graph) → Grant admin consent. Mail.ReadWrite instead if you want Outlook drafts on approve, or 'Mark items read at the source' (Settings → Sync & startup) — both write back to the mailbox.",
      "Enter tenant_id + client_id and paste the app's client secret (write-only). Blank = the server's AZURE_* env vars.",
      "Add each mailbox to read as a UPN under Sources and flip it on.",
      "Test acquires a real Graph token and reports exactly what failed if anything. Enable, and mail flows through the same triage funnel as everything else."] },
  teams: { group: "Messaging", channel: "teams", srcLabel: "Users / chat ids", srcPh: "user UPN, e.g. jsmith@yourcompany.com",
    fields: [["tenant_id", "tenant_id"], ["client_id", "client_id"],
      ["Notify chat id", "notify_chat", "19:…@thread.v2", "Only for the Notifications role — the chat id from a Teams URL"]],
    secretLabel: "client secret",
    desc: "Ingest Teams chats via Graph. Leave credentials blank to reuse the Outlook connector's app.",
    howto: ["Credentials: leave everything blank and Teams automatically reuses the Outlook connector's saved Graph app (or the server's AZURE_* env vars). Only fill these to use a different app registration.",
      "App-only chat reading is a Microsoft PROTECTED API: the tenant needs Microsoft-approved Chat.Read.All - until that approval is granted, Test shows the 403 telling you so.",
      "Add the user whose chats to ingest as a UPN under Sources. Your UPN (User Principal Name) is your Microsoft 365 sign-in address - usually just your work email. Find it in Teams: click your profile picture, it's the address under your name. Or run `whoami /upn` in a terminal on a work Windows machine, or check Azure Portal → Users → your account → User principal name.",
      "A specific chat id works too (Teams web: open the chat, the 19:...@thread.v2 part of the URL).",
      "Test probes an actual chat read for the first Teams source, not just the token."] },
  slack: { group: "Messaging", channel: "slack", srcLabel: "Channel IDs", srcPh: "C0123456789",
    fields: [], secretLabel: "bot token (xoxb-…)",
    desc: "Ingest Slack channels with a bot token - messages land on the Timeline through triage.",
    howto: ["Create a Slack app (api.slack.com/apps) → OAuth & Permissions → bot token scopes: channels:history, channels:read.",
      "Install the app to your workspace and invite the bot to the channels to ingest (/invite @yourbot).",
      "Paste the xoxb- bot token under Credentials (write-only).",
      "Add each channel ID under Sources (channel → View details → ID at the bottom).",
      "Test authenticates and probes a real channel read."] },
  telegram: { group: "Messaging", channel: "telegram", srcLabel: "Chat IDs — only chats flipped ON become work", srcPh: "-1001234567890",
    fields: [["Notify chat id", "notify_chat", "", "Only for the Notifications role — same id the chat's Source card shows"]],
    secretLabel: "bot token (from @BotFather)",
    desc: "A Telegram bot as an inbound channel - approved chats flow through triage; approved replies go back into the same chat. Unknown chats never become work: a bot is public.",
    howto: ["Message @BotFather in Telegram → /newbot → copy the token.",
      "Paste the token under Credentials (write-only) and Test.",
      "Finding a chat id is automatic: message your bot (or add it to a group) and Sync — the chat appears under Sources with its chat id, switched OFF. Flip on the ones that are yours; messages flow from then on.",
      "Everything else stays out by design — anyone can find and message a public bot, and an unapproved stranger must never be able to put tasks on your board.",
      "For a group: add the bot to it and disable its privacy mode (@BotFather → /setprivacy) so it sees messages."] },
  whatsapp: { group: "Messaging", channel: "whatsapp", srcLabel: "Chat JIDs (optional — blank takes every chat)", srcPh: "15551234567@s.whatsapp.net",
    fields: [["bridge URL (blank = http://127.0.0.1:8977)", "bridge_url"],
      ["Notify chat JID", "notify_chat", "15551234567@s.whatsapp.net",
       "Only for the Notifications role — the WhatsApp JID of the chat to ping"]],
    secretLabel: null,
    desc: "Your own WhatsApp, via a small bridge that runs beside Taskuary (Baileys, installed separately) - chats flow through triage, approved replies go back into the chat.",
    howto: ["The heavy dependency is deliberately NOT bundled: in the Taskuary folder run `cd taskuary/whatsapp && npm install && node bridge.mjs` (Node 18+).",
      "Pair once: scan the QR the bridge prints (WhatsApp → Linked devices), or run it with --phone 1555… and enter the code it gives you.",
      "Leave the bridge running; Test here confirms the pairing and adds a catch-all source.",
      "Add specific chat JIDs under Sources only if you want to LIMIT which chats come in.",
      "Unofficial protocol (WhatsApp Web) - use a number you would risk; business-critical numbers belong on the official API."] },
  gmail: { group: "Messaging", channel: "email", srcLabel: "Mailbox", srcPh: "you@gmail.com",
    fields: [["mailbox address", "address"]], secretLabel: "App Password (16 characters)",
    desc: "A Gmail or Google Workspace mailbox - IMAP in through triage, replies back over Gmail's own SMTP, in-thread.",
    howto: ["Turn on 2-Step Verification for the Google account (App Passwords require it).",
      "Create an App Password: myaccount.google.com -> Security -> App passwords -> app: Mail.",
      "Enter the mailbox address under Credentials and paste the 16-character App Password (write-only).",
      "Test logs in and adds the mailbox as a source; new mail flows in on the next sync.",
      "Replies you approve are sent from this same address over SMTP, threaded into the conversation."] },
  imap: { group: "Messaging", channel: "email", srcLabel: "Mailbox", srcPh: "you@yourdomain.com",
    fields: [["mailbox address", "address"], ["IMAP host (e.g. imap.yourdomain.com)", "imap_host"],
             ["SMTP host (blank = imap host with imap->smtp)", "smtp_host"]],
    secretLabel: "mailbox password",
    desc: "Any mailbox that speaks IMAP - a domain.com address, Yahoo, an ISP, your webhost. In through triage, replies out over its SMTP.",
    howto: ["Find your provider's IMAP and SMTP hostnames (usually imap./smtp. + your domain; ports 993/587).",
      "Enter the address and IMAP host under Credentials; SMTP host only if it does not follow the imap->smtp pattern.",
      "Paste the mailbox password (write-only). Providers with app passwords (Yahoo, iCloud) want those.",
      "Test logs in and adds the mailbox as a source; new mail flows in on the next sync."] },
  github: { group: "Developer", channel: "github", srcLabel: "Repositories", srcPh: "org/repo",
    fields: [], secretLabel: "fine-grained PAT",
    desc: "Paste a PAT - repos are auto-discovered, feed the Board's repo picker and the coder's issue loop. Per repo, choose what issues and PRs do: tasks, feed, or off.",
    howto: ["Create a fine-grained PAT: GitHub → Settings → Developer settings → Fine-grained tokens.",
      "Repository access: the repos the agent may touch. Permissions: Issues Read+Write, Pull requests Read+Write, Metadata Read.",
      "Paste the token under Credentials - that's ALL the config: on save Taskuary discovers every repo the token reaches, adds them under Sources, and writes the repository map into SOUL.md.",
      "Everything inbound lives on ONE step — Inbound, what becomes work: the trigger/feed switch, a per-repo picker for what issues and PRs do (tasks = through triage, feed = timeline only, off = ignored), and the agent prompts. Triage sees each item's author and GitHub association, so a stranger's PR on a public repo files as FYI instead of becoming work — and github items never auto-start a coding agent; you promote the ones that deserve one.",
      "When you DO send a PR or issue to the agent, its prompt carries the standing rules you set on that same Inbound step — the PR default says judge it (useful? safe? minimal?), run the tests, report a verdict, and never merge.",
      "Test re-runs discovery and reports who it's authenticated as.",
      "Coding tasks then open an issue first, the agent works it, and closing the task closes the issue."] },
  jira: { group: "Project management", channel: "jira", srcLabel: "Site", srcPh: "yourteam.atlassian.net",
    fields: [["site URL (https://yourteam.atlassian.net)", "base_url"], ["account email (the one the token belongs to)", "email"]],
    secretLabel: "API token",
    desc: "Jira issues ASSIGNED TO YOU land on the Timeline through triage — 'assigned in Jira' and 'asked by email' end up in the one funnel.",
    howto: ["Create an API token: id.atlassian.com → Security → Create API token.",
      "Enter the site URL and the account email under Credentials, paste the token (write-only).",
      "Test authenticates as you and adds the site under Sources.",
      "From then on every sync brings in issues assigned to you (updated since the last poll) — each shows its status, priority and reporter, and links back to Jira.",
      "Nothing is written back to Jira; Taskuary only reads."] },
  asana: { group: "Project management", channel: "asana", srcLabel: "Workspace", srcPh: "added by Test",
    fields: [],
    secretLabel: "Personal Access Token",
    desc: "Asana tasks ASSIGNED TO YOU land on the Timeline through triage, linking back to Asana.",
    howto: ["Create a Personal Access Token: app.asana.com/0/my-apps → Create new token.",
      "Paste it under Credentials (write-only) — that is all the config.",
      "Test authenticates, finds your workspace and adds it under Sources.",
      "Every sync brings in open tasks assigned to you that changed since the last poll.",
      "Nothing is written back to Asana; Taskuary only reads."] },
  monday: { group: "Project management", channel: "monday", srcLabel: "Account", srcPh: "added by Test",
    fields: [["board ids to watch, comma-separated (blank = your 25 most recently used boards)", "board_ids"]],
    secretLabel: "API token",
    desc: "Monday.com items ASSIGNED TO YOU (any People column naming you) land on the Timeline through triage.",
    howto: ["Get an API token: your avatar → Developers → My access tokens (admin tokens work too).",
      "Paste it under Credentials (write-only). Test authenticates and remembers who 'you' are.",
      "Monday has no assigned-to-me API, so the poll walks boards and keeps items whose People column names you — blank config walks your 25 most recently used boards; list board ids to pin it down (the number in the board's URL).",
      "Every sync brings in your items that changed since the last poll, linking back to the board.",
      "Nothing is written back to Monday; Taskuary only reads."] },
  clickup: { group: "Project management", channel: "clickup", srcLabel: "Workspace", srcPh: "added by Test",
    fields: [],
    secretLabel: "API token (starts pk_)",
    desc: "ClickUp tasks ASSIGNED TO YOU land on the Timeline through triage, with their list, status and priority.",
    howto: ["Get a personal API token: Settings → Apps → API Token → Generate. It starts pk_ and does not expire.",
      "Paste it under Credentials (write-only). ClickUp wants the token raw, so don't add 'Bearer' — Taskuary handles the header.",
      "Test authenticates, remembers who 'you' are and which Workspace to walk, and adds it under Sources.",
      "Every sync brings in tasks assigned to you that changed since the last poll, linking back to ClickUp.",
      "Nothing is written back to ClickUp; Taskuary only reads."] },
  todoist: { group: "Project management", channel: "todoist", srcLabel: "Account", srcPh: "added by Test",
    fields: [["filter query (blank = (today | overdue))", "filter"]],
    secretLabel: "API token",
    desc: "The Todoist tasks a filter says are live — due today and overdue by default — land on the Timeline through triage.",
    howto: ["Get your API token: avatar → Settings → Integrations → Developer → copy the API token.",
      "Paste it under Credentials (write-only).",
      "Todoist is a personal list, so most tasks have no assignee and 'assigned to me' would match only shared projects. The poll asks a FILTER QUERY instead — what Todoist itself says is live.",
      "Blank means (today | overdue). Write any Todoist filter to change it: 'assigned to: me' for shared projects, '@work & 7 days', 'p1', and so on.",
      "Each task files once — Todoist has no updated-since filter, so re-runs dedupe by task id rather than re-filing edits.",
      "Nothing is written back to Todoist; Taskuary only reads."] },
  gitlab: { group: "Developer", channel: "gitlab", srcLabel: "Instance", srcPh: "added by Test",
    fields: [["instance URL (blank = https://gitlab.com)", "base_url"]],
    secretLabel: "Personal Access Token (scope: read_api)",
    desc: "GitLab issues and merge requests ASSIGNED TO YOU land on the Timeline through triage — gitlab.com or your own instance.",
    howto: ["Create a Personal Access Token: avatar → Preferences → Access tokens, scope read_api.",
      "Self-hosted? Enter the instance URL; blank means gitlab.com.",
      "Paste the token (write-only). Test authenticates as you and adds the instance under Sources.",
      "Every sync brings in issues and MRs assigned to you that changed since the last poll, linking back to GitLab.",
      "Nothing is written back to GitLab; Taskuary only reads."] },
  azdo: { group: "Developer", channel: "azdo", srcLabel: "Organization", srcPh: "added by Test",
    fields: [["organization URL (https://dev.azure.com/yourorg)", "org_url"]],
    secretLabel: "Personal Access Token (Work Items: Read)",
    desc: "Azure DevOps work items ASSIGNED TO YOU land on the Timeline through triage.",
    howto: ["Create a PAT: User settings (top right) → Personal access tokens → New, scope Work Items: Read.",
      "Enter the organization URL (https://dev.azure.com/yourorg) and paste the PAT (write-only).",
      "Test authenticates and reports how many projects the token can see.",
      "Every sync runs a WIQL 'assigned to @Me' query and brings in work items that changed since the last poll.",
      "Nothing is written back to Azure DevOps; Taskuary only reads."] },
  sentry: { group: "Developer", channel: "sentry", srcLabel: "Organization", srcPh: "added by Test",
    fields: [["organization slug (first path segment of your Sentry URLs)", "org"],
      ["base URL (blank = https://sentry.io; set for self-hosted)", "base_url"]],
    secretLabel: "auth token (org:read + event:read)",
    desc: "New unresolved Sentry errors land on the Timeline through triage — production breakage joins the same funnel as the mail about it.",
    howto: ["Create an auth token: Sentry → Settings → Auth Tokens (scopes org:read, event:read).",
      "Enter the organization slug — the first path segment in your Sentry URLs.",
      "Paste the token (write-only). Test authenticates and adds the org under Sources.",
      "Every sync brings in unresolved issues whose last-seen changed since the last poll, with count and level, linking back to Sentry."] },
  pagerduty: { group: "Developer", channel: "pagerduty", srcLabel: "Account", srcPh: "added by Test",
    fields: [],
    secretLabel: "API token",
    desc: "Open PagerDuty incidents (triggered / acknowledged) land on the Timeline through triage.",
    howto: ["Get an API token: PagerDuty → Integrations → API Access Keys (a read-only key is enough).",
      "Paste it under Credentials (write-only) — that is all the config.",
      "Test probes the incidents API and adds the account under Sources.",
      "Every sync brings in incidents opened since the last poll with status, urgency and service, linking back to PagerDuty."] },
  linear: { group: "Project management", channel: "linear", srcLabel: "Workspace", srcPh: "added by Test",
    fields: [],
    secretLabel: "API key",
    desc: "Linear issues ASSIGNED TO YOU land on the Timeline through triage.",
    howto: ["Create a personal API key: Linear → Settings → Security & access → Personal API keys.",
      "Paste it under Credentials (write-only) — that is all the config.",
      "Test authenticates as you and adds the workspace under Sources.",
      "Every sync brings in issues assigned to you that changed since the last poll, linking back to Linear.",
      "Nothing is written back to Linear; Taskuary only reads."] },
  trello: { group: "Project management", channel: "trello", srcLabel: "Account", srcPh: "added by Test",
    fields: [["API key (trello.com/power-ups/admin → your Power-Up → API key)", "api_key"]],
    secretLabel: "token (generate it from the API key page)",
    desc: "Open Trello cards ASSIGNED TO YOU land on the Timeline through triage.",
    howto: ["Get an API key: trello.com/power-ups/admin → create a Power-Up if you have none → API key.",
      "On that same page use the Token link to authorize and copy the token.",
      "Enter the API key under Credentials and paste the token (write-only).",
      "Test authenticates as you; every sync brings in your open cards whose activity changed since the last poll."] },
  notion: { group: "Project management", channel: "notion", srcLabel: "Workspace", srcPh: "added by Test",
    fields: [],
    secretLabel: "internal integration secret",
    desc: "Notion pages shared with your integration show on the Timeline as they change — a FEED by default: edits are information, not assignments.",
    howto: ["Create an internal integration at notion.so/my-integrations and copy its secret.",
      "SHARE the pages or databases you care about with the integration (page → ⋯ → Connections) — it sees nothing else.",
      "Paste the secret under Credentials (write-only). Test authenticates the integration.",
      "Every sync surfaces pages edited since the last poll. It ships as a feed; flip the trigger role on if edits should become work."] },
  discord: { group: "Messaging", channel: "discord", srcLabel: "Channel IDs", srcPh: "1234567890123456789",
    fields: [],
    secretLabel: "bot token",
    desc: "Watch Discord channels with a bot — messages land on the Timeline through triage, and approved replies post back to the channel.",
    howto: ["Create an app at discord.com/developers → Bot → Reset Token, and turn ON the Message Content intent.",
      "Invite the bot to your server with permission to read (and send, for replies in) the channels you'll watch.",
      "Paste the bot token under Credentials (write-only).",
      "Add each channel ID under Sources (Discord → Settings → Advanced → Developer Mode, then right-click a channel → Copy Channel ID).",
      "Approving a drafted reply posts it into the same channel as the bot."] },
  anthropic: { group: "AI — agents & models", channel: "ai", srcLabel: null,
    fields: [["model (default claude-opus-5)", "model"]], secretLabel: "API key",
    desc: "Claude via the Anthropic API - powers intent triage (task / reply-only / FYI) once enabled.",
    howto: ["Create an API key at console.anthropic.com → API keys.",
      "Paste it under Credentials (write-only). Optionally set a model - default is claude-opus-5.",
      "Test runs a real round trip through the model.",
      "Enable it and every new inbound message is classified by the model, guided by SOUL.md - the first active AI connector wins."] },
  openai: { group: "AI — agents & models", channel: "ai", srcLabel: null,
    fields: [["model (default gpt-4o-mini)", "model"]], secretLabel: "API key",
    desc: "OpenAI models for intent triage - alternative to the Anthropic connector.",
    howto: ["Create an API key at platform.openai.com.",
      "Paste it under Credentials; optionally set a model.",
      "Test runs a real round trip. Enable to wire it into triage - the first active AI connector wins."] },
  azure_openai: { group: "AI — agents & models", channel: "ai", srcLabel: null,
    fields: [["endpoint", "endpoint"], ["deployment", "deployment"], ["api_version", "api_version"]], secretLabel: "API key",
    desc: "Your Azure OpenAI deployment for intent triage - endpoint + deployment + key.",
    howto: ["Azure Portal → your Azure OpenAI resource → Keys and Endpoint.",
      "Enter the endpoint (https://YOUR-RESOURCE.openai.azure.com), the deployment name, and optionally an api_version.",
      "Paste a key under Credentials. Test runs a real round trip through the deployment."] },
  openrouter: { group: "AI — agents & models", channel: "ai", srcLabel: null,
    fields: [["model (default openrouter/auto)", "model"]], secretLabel: "API key",
    desc: "One key, the whole catalog — open-weights Llama / Qwen / Mistral and every closed model, through OpenRouter's OpenAI-compatible API.",
    howto: ["Create a key at openrouter.ai → Keys.",
      "Paste it under Credentials; optionally set a model from openrouter.ai/models (e.g. meta-llama/llama-3.3-70b-instruct). Empty = openrouter/auto picks per request.",
      "Test runs a real round trip. Enable to wire it into triage, drafts, the digest and LEARNED.md — or pick it explicitly under Settings → Triage & routing."] },
  ollama: { group: "AI — agents & models", channel: "ai", srcLabel: null,
    fields: [["base_url (default http://127.0.0.1:11434)", "base_url"], ["model — required, e.g. llama3.2 / qwen2.5", "model"]],
    secretLabel: "API key (optional — a local server rarely needs one)",
    desc: "Open-source models on YOUR machine — Ollama out of the box, or any OpenAI-compatible server (LM Studio, llama.cpp, vLLM). Your mail never leaves the box.",
    howto: ["Install Ollama (ollama.com) and pull a model: ollama pull llama3.2 — or point base_url at LM Studio (http://127.0.0.1:1234), llama.cpp or vLLM.",
      "Enter the model name (ollama list shows what's installed). No key needed for a local server.",
      "Test runs a real round trip through the local model, then Enable makes it the triage brain — or pick it under Settings → Triage & routing.",
      "For the CODING side, local models ride the CLI road instead: add any CLI that reads a prompt on stdin under AI CLI agents."] },
};

const PLANNED_AI = [
  { name: "AWS Bedrock", desc: "planned - Claude & friends through your AWS account" },
  { name: "Google Vertex AI", desc: "planned - Gemini / Claude through your GCP project" },
];

const MSSQL_HOWTO = [
  "This card is the CONNECTION only - set it up once, Test it, and every SQL report inherits it.",
  "Local SQL Server: keep auth on Windows (trusted) - server + database is all the config. Named instance? Use HOST\INSTANCE, e.g. localhost\SQLEXPRESS.",
  "Driver auto-picks the newest installed 'ODBC Driver NN for SQL Server'; SQL logins go under auth.",
  "Build the actual reports (query + AI summary + schedule) on the REPORTS tab.",
];

/* ── data-connection cards that share one field-driven detail page (mssql keeps its
   bespoke driver picker). Each is the CONNECTION only - reports live on the Reports tab. */
const DATA_META = {
  database: { title: "Any database (connection string)", types: ["database"],
    fields: [["connection string", "conn_str",
      "postgresql://user:{password}@host:5432/db   ·   mysql+pymysql://…   ·   DRIVER={…};SERVER=…"]],
    secretLabel: "password for {password} (optional — write-only)",
    desc: "Postgres, MySQL, Snowflake, Oracle, anything with a connection string — URLs run through SQLAlchemy, raw ODBC strings through pyodbc.",
    howto: ["Paste the connection string: a URL (postgresql://…, mysql+pymysql://…, snowflake://…) or a raw ODBC string (DRIVER={…};SERVER=…;).",
      "Keep the password OUT of the string: write {password} where it goes and paste the real one below (stored write-only, never shown again).",
      "URL engines need their Python driver on the server: pip install taskuary[db] plus e.g. psycopg2-binary (postgres) or pymysql (mysql).",
      "Test connects for real and runs a probe (SELECT 1 — engines that need FROM DUAL can set test_query in the config).",
      "Build the actual reports (query + AI summary + schedule) on the REPORTS tab; agents with the tool role can query it too."] },
  aws: { title: "Amazon Web Services", types: ["aws", "s3_object", "cloudwatch_logs"], discovers: true,
    fields: [["access key id", "access_key_id"], ["region(s), comma-separated (e.g. us-east-2, us-east-1)", "region"]],
    secretLabel: "secret access key (write-only; blank = server env / ~/.aws / instance role)",
    desc: "S3 objects, CloudWatch logs — or ANY service call — as scheduled reports, Timeline feeds and agent tools, with your IAM keys.",
    howto: ["Create an IAM user (or use an existing one) with read access to what you'll pull: AmazonS3ReadOnlyAccess, CloudWatchLogsReadOnlyAccess, etc.",
      "Enter the access key id + region and paste the secret access key (write-only). Leave everything blank to use the server's own AWS credentials (env vars, ~/.aws, an instance role).",
      "Several regions? List them comma-separated. CloudWatch log groups exist PER REGION - the same account shows a completely different set in us-east-1 and us-east-2 - so discovery sweeps each one and every object remembers where it was found. S3 is one global namespace, listed once, and each bucket is asked for its own region so reads go to the right endpoint.",
      "The server needs boto3: pip install taskuary[aws].",
      "Test & discover calls STS (reporting which account/ARN you are) and then asks the keys what they can SEE: every S3 bucket and CloudWatch log group is listed under 'What you have access to'.",
      "Each discovered object gets its own picker: report only (the default — selectable on the Reports tab, nothing polled), feed (new objects / matching log lines appear on the Timeline), tasks (they go through triage), or off.",
      "Reports tab then offers the same objects as pipelines: S3 object (read a file or list a prefix), CloudWatch logs (grep a group), and a generic AWS call (any service + operation, e.g. athena or ec2)."] },
  prometheus: { title: "Prometheus", types: ["prometheus"],
    fields: [["base URL", "base_url", "http://prometheus.yourcompany.local:9090"]],
    secretLabel: "bearer token (optional — most Prometheus servers need none)",
    desc: "PromQL instant queries as scheduled reports and agent tools — each series comes back as a row of its labels + value.",
    howto: ["Enter the server's base URL (the address the Prometheus UI runs on, usually port 9090).",
      "Behind an auth proxy? Paste the bearer token (write-only); plain servers need nothing.",
      "Test runs a trivial query for real.",
      "Build the reports (PromQL + AI summary + schedule) on the REPORTS tab — 'up == 0' every morning is the classic."] },
  datadog: { title: "Datadog", types: ["datadog"],
    fields: [["site (blank = datadoghq.com; EU = datadoghq.eu)", "site"],
      ["application key (Organization Settings → Application Keys)", "app_key"]],
    secretLabel: "API key (write-only)",
    desc: "Your Datadog monitors and their states as scheduled reports and agent tools — trouble sorts first.",
    howto: ["Get an API key (Organization Settings → API Keys) and an application key (→ Application Keys).",
      "Enter the site if not US1 (datadoghq.eu, us3.datadoghq.com, …), the application key, and paste the API key (write-only).",
      "Test validates the key pair for real.",
      "Build the reports on the REPORTS tab: all monitors, or filtered by name — Alert and Warn states sort to the top."] },
  /* Research: the web as a report source. All four are one REST call with a key - what is NOT
     here is anything that DRIVES a browser (log in, click, fill), because that runs over CDP
     through Playwright or Stagehand and cannot be reached from an API at all. */
  exa: { title: "Exa", types: ["exa"], fields: [],
    secretLabel: "API key (write-only)",
    desc: "Neural web search with the page text already extracted — a research source for reports, and a tool an agent can call.",
    howto: ["Get a key at exa.ai → Dashboard → API Keys.",
      "Paste it here (write-only) and Test runs a real search.",
      "Build the research on the REPORTS tab: a query, how many results, optionally only certain domains or published since a date.",
      "It returns the page TEXT, not just links — so the AI summary has something to read."] },
  tavily: { title: "Tavily", types: ["tavily"], fields: [],
    secretLabel: "API key (write-only, starts tvly-)",
    desc: "Search built for agents: it can hand back a written answer with its sources beside it, not only a list of results.",
    howto: ["Get a key at tavily.com → API Keys (there is a free tier).",
      "Paste it here (write-only) and Test runs a real search.",
      "On the REPORTS tab, pick a depth: basic for a fact, advanced for a question worth two credits.",
      "The answer leads and the sources sit under it, so a claim can be checked rather than taken on faith."] },
  firecrawl: { title: "Firecrawl", types: ["firecrawl"], fields: [],
    secretLabel: "API key (write-only, starts fc-)",
    desc: "Read one page as clean markdown — the nav, the cookie banner and the footer stripped out.",
    howto: ["Get a key at firecrawl.dev → Dashboard.",
      "Paste it here (write-only) and Test reads a page for real.",
      "On the REPORTS tab, give it a URL. Good for a pricing page or a changelog you want watched.",
      "For a page behind a login it will not help — that needs a real browser session, which is not an API away."] },
  reader: { title: "Jina Reader", types: ["reader"], fields: [],
    secretLabel: "API key (optional — it works without one, a key just raises the rate limit)",
    desc: "Read any public page as markdown, with no account at all. The one research source a fresh install can try immediately.",
    howto: ["Nothing to set up: leave the key blank and it works.",
      "Test reads a page for real, key or no key.",
      "Paste a key from jina.ai only if you hit the anonymous rate limit.",
      "On the REPORTS tab, give it a URL — same shape as Firecrawl, no account required."] },
  azure: { title: "Microsoft Azure", types: ["azure", "azure_blob", "azure_logs"], discovers: true,
    fields: [["tenant_id", "tenant_id"], ["client_id", "client_id"]],
    secretLabel: "client secret (write-only; blank = reuse the Outlook connector's app)",
    desc: "Blob storage, Log Analytics (KQL) — or ANY resource via ARM — as scheduled reports, Timeline feeds and agent tools, through an app registration.",
    howto: ["Reuse the app you registered for Outlook (leave everything blank) or register a new one: Azure Portal → App registrations.",
      "Grant the app RBAC roles on what you'll pull: Reader on a subscription/resource group (ARM reads), Storage Blob Data Reader (blobs), Log Analytics Reader (logs). These are IAM role assignments, not Graph API permissions.",
      "No extra installs — tokens ride the same client-credentials road the Outlook connector uses.",
      "Test & discover authenticates (naming the subscriptions the app can see — a token with no roles is called out) and then enumerates what those roles reach: every blob container and Log Analytics workspace is listed under 'What you have access to'.",
      "Each discovered object gets its own picker: report only (the default — selectable on the Reports tab, nothing polled), feed (new blobs / new query rows appear on the Timeline), tasks (they go through triage), or off.",
      "Reports tab then offers the same objects as pipelines: Azure blob (read a file or list a container), Log Analytics (any KQL), and a generic ARM read (any resource path)."] },
};

const WINRM_HOWTO = [
  "This card is the CONNECTION only - the machine name. Build the actual reports (script + AI summary + schedule) on the REPORTS tab.",
  "A box you can RDP into (like AZWEB01) is usually domain-joined and already reachable over WinRM with your Windows login - just enter the machine name and Test.",
  "If Test fails with 'WinRM unreachable', enable PS remoting on the remote box once: open an elevated PowerShell THERE and run Enable-PSRemoting -Force.",
  "Reports then run any PowerShell you write ON that machine (read a log, query a service, export a CSV) and the output - optionally AI-summarized - lands on the Timeline.",
];

const parse = (s) => { try { return JSON.parse(s || "{}"); } catch { return {}; } };
const NL = String.fromCharCode(10);

export default function ConnectorsView() {
  const [connectors, setConnectors] = useState(null);
  const [sources, setSources] = useState([]);
  const [types, setTypes] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(null);   // {kind:'channel',id} | {kind:'rtype',rtype,SourceId?} | {kind:'agents'}
  const [syncing, setSyncing] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const [c, s, t] = await Promise.all([api.get("/api/connectors"), api.get("/api/sources"), api.get("/api/report-types")]);
      setConnectors(c.data.data || []); setSources(s.data.data || []); setTypes(t.data.data || []);
    } catch (e) { setErr(e?.response?.data?.detail || "Failed to load connectors"); }
  }, []);
  useEffect(() => { load(); api.get("/api/mssql/drivers").then(({ data }) => setDrivers(data.data || [])).catch(() => {}); }, [load]);

  const reports = sources.filter((x) => x.Channel === "report");
  const syncNow = async () => {
    setSyncing(true);
    try { await api.post("/api/ingest/poll"); setTimeout(() => { setSyncing(false); load(); }, 3000); }
    catch { setSyncing(false); }
  };

  const byType = Object.fromEntries((connectors || []).map((c) => [c.Type, c]));

  if (!connectors) return <CircularProgress size={22} sx={{ m: 4 }} />;

  if (open?.kind === "agents") return <AgentsPage section="Connectors" title="AI CLI agents" onBack={() => setOpen(null)} />;
  if (open?.kind === "channel") {
    const conn = connectors.find((c) => c.ConnectorId === open.id);
    return <ChannelDetail conn={conn} sources={sources} reload={load} onBack={() => setOpen(null)} />;
  }
  if (open?.kind === "mssql") {
    return <MssqlDetail conn={byType.mssql} drivers={drivers} reload={load} onBack={() => setOpen(null)} />;
  }
  if (open?.kind === "winrm") {
    return <WinrmDetail conn={byType.winrm} reload={load} onBack={() => setOpen(null)} />;
  }
  if (open?.kind === "data") {
    return <DataDetail conn={byType[open.type]} meta={DATA_META[open.type]} sources={sources}
      reload={load} onBack={() => setOpen(null)} />;
  }

  /* ── landing: searchable grouped catalog ── */
  const chanCard = (c) => {
    const m = META[c.Type] || {};
    const srcs = m.channel && m.channel !== "ai"
      ? sources.filter((s) => s.ConnectorId === c.ConnectorId) : null;   // owned, never channel-shared
    const roles = String(c.Roles || "").split(",").filter(Boolean);
    const status = `${c.Active ? "on" : "off"}`
      + (roles.length ? ` · ${roles.map((r) => r === "notify" ? "notifications" : r).join(" + ")}` : "")
      + (srcs ? ` · ${srcs.filter((s) => s.Active).length}/${srcs.length} ${(m.srcLabel || "sources").toLowerCase()}`
        : c.HasSecret ? " · key saved" : c.Type === "ollama" ? " · local — no key needed" : " · no key yet")
      + (c.LastError ? " · last test failed" : c.LastSyncAt ? ` · ok ${timeAgo(c.LastSyncAt)}` : "");
    // the product's own logo wins over the channel glyph: five AI cards sharing one sparkle,
    // or Jira and Linear both wearing 'boards', tells you nothing about which is which
    return { key: `c${c.ConnectorId}`, title: c.Name, desc: status,
      channel: hasLogo(c.Type) ? c.Type : (m.channel || c.Type),
      haystack: `${c.Name} ${c.Type} ${m.desc || ""} ${(m.howto || []).join(" ")}`,
      go: () => setOpen({ kind: "channel", id: c.ConnectorId }) };
  };
  const groups = [
    { title: "AI — agents & models", cards: [
      { key: "agents", title: "AI CLI agents", desc: "claude / codex / gemini — bring your own coding CLI, resumable sessions",
        channel: "cli", haystack: "ai cli agents claude codex gemini command args resume", go: () => setOpen({ kind: "agents" }) },
      ...["anthropic", "openai", "azure_openai", "openrouter", "ollama"].filter((t) => byType[t]).map((t) => chanCard(byType[t])),
      ...PLANNED_AI.map((p) => ({ key: p.name, title: p.name, desc: p.desc, channel: "ai", haystack: `${p.name} ${p.desc}`, planned: true })),
    ]},
    { title: "Messaging", cards: ["outlook", "gmail", "imap", "teams", "slack", "telegram", "whatsapp", "discord"].filter((t) => byType[t]).map((t) => chanCard(byType[t])) },
    { title: "Developer", cards: ["github", "gitlab", "azdo", "sentry", "pagerduty"].filter((t) => byType[t]).map((t) => chanCard(byType[t])) },
    { title: "Project management", cards: ["jira", "asana", "monday", "clickup", "todoist", "linear", "trello", "notion"].filter((t) => byType[t]).map((t) => chanCard(byType[t])) },
    { title: "Data connections", cards: [
      {
        key: "mssql", title: "Microsoft SQL Server", channel: "mssql",
        desc: (byType.mssql?.LastError ? "connection failing" : byType.mssql?.LastSyncAt ? "connection ✓" : "not set up")
          + ` · ${reports.filter((s2) => (parse(s2.ConfigJson).type || "rest") === "mssql").length} reports (built on the Reports tab)`,
        haystack: "microsoft sql server mssql connection windows auth " + MSSQL_HOWTO.join(" "),
        go: () => setOpen({ kind: "mssql" }),
      },
      ...(byType.winrm ? [{
        key: "winrm", title: "Remote Windows (WinRM)", channel: "winrm",
        desc: (byType.winrm.LastError ? "connection failing" : byType.winrm.LastSyncAt ? "connection ✓" : "not set up")
          + ` · ${reports.filter((s2) => (parse(s2.ConfigJson).type || "rest") === "winrm").length} reports (built on the Reports tab)`,
        haystack: "remote windows winrm rdp powershell remoting azweb01 " + WINRM_HOWTO.join(" "),
        go: () => setOpen({ kind: "winrm" }),
      }] : []),
      ...Object.entries(DATA_META).filter(([t]) => byType[t]).map(([t, dm]) => ({
        key: t, title: dm.title, channel: t,
        desc: (byType[t].LastError ? "connection failing" : byType[t].LastSyncAt ? "connection ✓" : "not set up")
          + ` · ${reports.filter((s2) => dm.types.includes(parse(s2.ConfigJson).type)).length} reports (built on the Reports tab)`,
        haystack: `${dm.title} ${t} ${dm.desc} ${dm.types.join(" ")} ` + dm.howto.join(" "),
        go: () => setOpen({ kind: "data", type: t }),
      })),
      ...types.filter((t) => t.status === "planned").map((t) => ({
        key: `p${t.type}`, title: t.type, desc: "planned", channel: t.type, haystack: `${t.type} planned`, planned: true })),
    ]},
  ];
  const hits = q ? groups.flatMap((g) => g.cards.filter((c) => !c.planned && c.haystack.toLowerCase().includes(q.toLowerCase()))
    .map((c) => ({ ...c, crumb: g.title }))) : [];

  return (
    <Box sx={{ maxWidth: 1160, mx: "auto" }}>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 3 }}>
        <TextField fullWidth placeholder="Search connectors — Slack, SQL Server, Anthropic… matches setup guides too" value={q}
          onChange={(e) => setQ(e.target.value)} sx={{ bgcolor: "#fff", borderRadius: 2, maxWidth: 520, mx: "auto", display: "block" }}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon sx={{ fontSize: 18, color: FAINT }} /></InputAdornment> }} />
        <Box sx={{ flex: 1 }} />
        <Button size="small" variant="contained" disableElevation onClick={syncNow} disabled={syncing}
          startIcon={syncing ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : <SyncIcon sx={{ fontSize: 15 }} />}>
          {syncing ? "Syncing…" : "Sync now"}
        </Button>
      </Box>

      {q ? (
        <Box>
          {!hits.length && <Empty>Nothing matches.</Empty>}
          {hits.map((r) => (
            <Box key={r.key} onClick={r.go} sx={{ py: 1.25, borderBottom: `1px solid ${BORDER}`, cursor: "pointer",
              "&:hover": { bgcolor: "#fafbfd" } }}>
              <Typography sx={{ color: "#4f46e5", fontWeight: 600, fontSize: 13.5 }}>{r.title}</Typography>
              <Typography variant="caption" sx={{ color: FAINT }}>{r.crumb} · {r.desc}</Typography>
            </Box>
          ))}
        </Box>
      ) : groups.map((g) => (
        <Box key={g.title} sx={{ mb: 4 }}>
          <Typography sx={{ color: INK, fontWeight: 800, fontSize: 15, mb: 2 }}>{g.title}</Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" }, gap: 3 }}>
            {g.cards.map((c) => (
              <Box key={c.key} sx={{ opacity: c.planned ? 0.45 : 1 }}>
                <LandingCard title={c.title} desc={c.desc} onOpen={c.planned ? () => {} : c.go}
                  icon={c.channel === "cli" ? <TerminalIcon sx={{ fontSize: 19, color: "#4f46e5" }} />
                    : <ChannelIcon channel={c.channel} sx={{ fontSize: 19 }} />} />
              </Box>
            ))}
          </Box>
        </Box>
      ))}
    </Box>
  );
}

/* ── "Remove connection" on every detail page: wipes creds/config, turns sources off ── */
function RemoveConnection({ conn, reload, onBack }) {
  const [confirm, setConfirm] = useState(false);
  const remove = async () => {
    await api.post(`/api/connectors/${conn.ConnectorId}/reset`);
    reload(); onBack();
  };
  // this one already asked, as a row that swapped itself for a "Sure?" - which is a different
  // shape of question from every other delete in the app. Same dialog as the rest now.
  return (
    <Box sx={{ mt: 3, pt: 1.5, borderTop: `1px solid ${BORDER}`, display: "flex", gap: 1, alignItems: "center", maxWidth: 720 }}>
      <Button size="small" startIcon={<DeleteOutlineIcon sx={{ fontSize: 15 }} />} sx={{ color: "#8a94a6" }}
        onClick={() => setConfirm(true)}>Remove connection</Button>
      <ConfirmDelete open={confirm} what={`the ${conn.Name || conn.Type} connection`} confirmLabel="Remove"
        consequence="Its saved credentials and settings are wiped and its sources are switched off. The card stays in the catalog, so you can set it up again from scratch."
        onClose={() => setConfirm(false)} onConfirm={remove} />
    </Box>
  );
}

/* ── channel / AI connector detail: setup wizard + sources ─────────────── */
function ChannelDetail({ conn, sources, reload, onBack }) {
  const m = META[conn.Type] || { fields: [], howto: [] };
  const isAI = m.channel === "ai";
  const [tab, setTab] = useState("Setup");
  const [step, setStep] = useState(conn.HasSecret ? (conn.LastSyncAt ? 2 : 1) : 0);
  const [cfg, setCfg] = useState(parse(conn.ConfigJson));
  const [secret, setSecret] = useState("");
  const [newSrc, setNewSrc] = useState("");
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");

  const mine = sources.filter((s) => s.ConnectorId === conn.ConnectorId);   // owned, never channel-shared

  const saveCreds = async () => {
    setBusy("save"); setMsg("");
    try {
      const body = { ConnectorId: conn.ConnectorId, ConfigJson: JSON.stringify(cfg) };
      if (secret) body.Secret = secret;
      const { data } = await api.post("/api/connectors", body);
      setMsg("saved ✓");
      if (data.discovery) {
        const d = data.discovery;
        setTest(d.error ? { ok: false, detail: d.error }
          : { ok: true, detail: `authenticated as ${d.login} · ${d.repos} repos discovered · ${d.added} sources added · repo map written to SOUL.md` });
      }
      setSecret(""); setStep(1); reload();
    } catch (e) { setMsg(""); setTest({ ok: false, detail: e?.response?.data?.detail || "save failed" }); }
    setBusy("");
  };
  const runTest = async () => {
    setBusy("test");
    try {
      const { data } = await api.post(`/api/connectors/${conn.ConnectorId}/test`);
      setTest(data);
      if (data.ok) setStep(m.srcLabel ? 2 : 3);
    } catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "test call failed" }); }
    setBusy(""); reload();
  };
  const addSource = async () => {
    if (!newSrc.trim()) return;
    await api.post("/api/sources", { Channel: m.channel, Address: newSrc.trim(), ConnectorId: conn.ConnectorId, Active: true });
    setNewSrc(""); reload();
  };
  // the telegram flow says "hit Sync now" - so the button has to BE here, not on another tab
  const [srcSync, setSrcSync] = useState(false);
  const syncHere = async () => {
    setSrcSync(true);
    try { await api.post("/api/ingest/poll"); setTimeout(() => { setSrcSync(false); reload(); }, 3000); }
    catch { setSrcSync(false); }
  };
  const toggleSource = async (s) => { await api.post("/api/sources", { SourceId: s.SourceId, Active: !s.Active }); reload(); };
  const setActive = async (on) => { await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, Active: on }); reload(); };

  const steps = [
    { label: "Credentials", done: !!conn.HasSecret || !m.secretLabel, body: (
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, maxWidth: 460, mt: 1 }}>
        {m.fields.map(([label, key, ph, helper]) => (
          <TextField key={key} label={label} placeholder={ph || ""} value={cfg[key] || ""} sx={{ bgcolor: "#fff" }}
            helperText={helper} onChange={(e) => setCfg({ ...cfg, [key]: e.target.value })} />
        ))}
        {/* WhatsApp has no secret at all - the bridge holds the pairing, not us */}
        {m.secretLabel && (
          <TextField label={conn.HasSecret ? `${m.secretLabel} (saved — type to replace)` : m.secretLabel} type="password"
            value={secret} onChange={(e) => setSecret(e.target.value)} sx={{ bgcolor: "#fff" }}
            helperText="Write-only: stored server-side, never returned to the browser." />
        )}
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          <Button variant="contained" disableElevation disabled={busy === "save"} onClick={saveCreds}>
            {busy === "save" ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : "Save & continue"}</Button>
          {msg && <Typography variant="body2" sx={{ color: "#15803d", fontWeight: 600 }}>{msg}</Typography>}
        </Box>
      </Box>
    )},
    { label: "Test", done: !!conn.LastSyncAt && !conn.LastError, body: (
      <Box sx={{ mt: 1 }}>
        <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>Live probe — token / model / channel read, for real.</Typography>
        <Button variant="contained" disableElevation disabled={busy === "test"} onClick={runTest}
          startIcon={busy === "test" ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : <BoltIcon sx={{ fontSize: 15 }} />}>Test</Button>
        {test && <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: test.ok ? "#15803d" : "#b91c1c" }}>
          {test.ok ? "✓" : "✗"} {test.detail}{test.ms != null ? ` · ${test.ms}ms` : ""}</Typography>}
        {!test && conn.LastError && <Typography variant="body2" sx={{ mt: 1, color: "#b91c1c" }}>✗ {conn.LastError}</Typography>}
      </Box>
    )},
    ...(m.srcLabel ? [{ label: m.srcLabel, done: mine.some((s) => s.Active), body: (
      <Box sx={{ mt: 1 }}>
        {conn.Type === "github" && (
          <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.5 }}>
            The repos this connection reaches — discovery fills the list from the PAT. What each
            repo's issues and PRs <b>do</b> (become tasks, show as feed, stay ignored) is decided in
            one place: the <b>Inbound — what becomes work</b> step below.
          </Typography>
        )}
        {conn.Type === "telegram" && (
          <>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1, maxWidth: 560 }}>
              No chat id to type: <b>message your bot</b> (or add it to a group), hit <b>Sync now</b>, and the
              chat appears below with its id — switched off. Flip on the chats that are yours; every other
              chat stays out, because a public bot can be messaged by anyone. The field at the bottom is only
              for an id you already know.
            </Typography>
            <Button size="small" variant="outlined" onClick={syncHere} disabled={srcSync} sx={{ mb: 1 }}
              startIcon={srcSync ? <CircularProgress size={11} /> : <SyncIcon sx={{ fontSize: 14 }} />}>
              {srcSync ? "Syncing…" : "Sync now — pull in chats that messaged the bot"}
            </Button>
          </>
        )}
        {mine.filter((s) => !(conn.Type === "telegram" && s.Address === "*")).map((s) => (
          <Box key={s.SourceId} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1, borderBottom: `1px solid ${BORDER}` }}>
            <StatusDot ok={!!s.Active} />
            <Typography sx={{ ...mono, color: INK, fontSize: 13 }} noWrap>{s.Address}</Typography>
            {String(s.Owner || "").startsWith("discovered:") && (
              <Typography variant="caption" sx={{ color: FAINT }} noWrap>
                {s.Owner.replace("discovered:", "").trim()}
              </Typography>
            )}
            <Box sx={{ flex: 1 }} />
            {s.LastPolledAt && <Typography variant="caption" sx={{ color: FAINT }}>polled {timeAgo(s.LastPolledAt)}</Typography>}
            <Switch checked={!!s.Active} onChange={() => toggleSource(s)} />
          </Box>
        ))}
        <Box sx={{ display: "flex", gap: 1, mt: 1.5, maxWidth: 460 }}>
          <TextField fullWidth placeholder={m.srcPh} value={newSrc} sx={{ bgcolor: "#fff" }}
            onChange={(e) => setNewSrc(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addSource()} />
          <Button variant="contained" disableElevation onClick={addSource}>Add</Button>
        </Box>
      </Box>
    )}] : []),
    ...(isAI ? [] : [
      { label: "Inbound — what becomes work", done: inboundDone(conn, mine),
        body: <InboundStep conn={conn} m={m} mine={mine} reload={reload} /> },
      { label: CAN_NOTIFY.has(conn.Type) ? "More roles — reports, agents, notifications" : "More roles — reports, agents", done: true,
        body: <RoleStep conn={conn} reload={reload}
          only={CAN_NOTIFY.has(conn.Type) ? ["report", "tool", "notify"] : ["report", "tool"]} /> },
    ]),
    ...(conn.Type === "github" ? [{ label: "Agent permissions", done: true, body: <GithubPerms conn={conn} reload={reload} /> }] : []),
    { label: "Enable", done: !!conn.Active, body: (
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mt: 1 }}>
        <Switch checked={!!conn.Active} onChange={(e) => setActive(e.target.checked)} />
        <Typography variant="body2" sx={{ color: DIM }}>
          {conn.Active
            ? (isAI ? "On — wired into intent triage (the first active AI connector wins)." : "On — polling on schedule and via Sync now.")
            : "Off — flip on once Test passes."}
        </Typography>
      </Box>
    )},
  ];

  return (
    <Box sx={{ maxWidth: 980, mx: "auto" }}>
      <Crumb section="Connectors" onBack={onBack} title={conn.Name} />
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>{m.desc}</Typography>
      <UnderTabs tabs={["Setup", "Guide"]} value={tab} onChange={setTab} />
      {tab === "Setup" && (
        <Stepper nonLinear activeStep={step} orientation="vertical" sx={{ "& .MuiStepLabel-label": { fontSize: 13.5, fontWeight: 600 } }}>
          {steps.map((s, i) => (
            <Step key={s.label} completed={s.done}>
              <StepButton onClick={() => setStep(i)}>{s.label}{s.done ? " ✓" : ""}</StepButton>
              <StepContent>{s.body}</StepContent>
            </Step>
          ))}
        </Stepper>
      )}
      {tab === "Guide" && <Steps steps={m.howto || []} />}
      <RemoveConnection conn={conn} reload={reload} onBack={onBack} />
    </Box>
  );
}

/* ── SQL Server detail: connection wizard + guide (reports live on the Reports tab) ── */
function MssqlDetail({ conn, drivers, reload, onBack }) {
  const [tab, setTab] = useState("Connection");
  if (!conn) return null;
  return (
    <Box sx={{ maxWidth: 980, mx: "auto" }}>
      <Crumb section="Connectors" onBack={onBack} title="Microsoft SQL Server" />
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>
        The connection only — build the scheduled reports (query + AI summary) on the Reports tab.
      </Typography>
      <UnderTabs tabs={["Connection", "Guide"]} value={tab} onChange={setTab} />
      {tab === "Connection" && <MssqlConnection conn={conn} drivers={drivers} reload={reload} />}
      {tab === "Guide" && <Steps steps={MSSQL_HOWTO} />}
      <RemoveConnection conn={conn} reload={reload} onBack={onBack} />
    </Box>
  );
}

/* ── the SQL Server CONNECTION (set up once; reports inherit it) ────────── */
function MssqlConnection({ conn, drivers, reload }) {
  const [cfg, setCfg] = useState(parse(conn.ConfigJson));
  const [secret, setSecret] = useState("");
  const [step, setStep] = useState(conn.LastSyncAt && !conn.LastError ? 1 : 0);
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const sqlAuth = (cfg.auth || "windows") === "sql";

  const save = async () => {
    setBusy("save"); setMsg("");
    try {
      const body = { ConnectorId: conn.ConnectorId, ConfigJson: JSON.stringify(cfg), Active: true };
      if (secret) body.Secret = secret;
      await api.post("/api/connectors", body);
      setMsg("saved ✓"); setSecret(""); setStep(1); reload();
    } catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "save failed" }); }
    setBusy("");
  };
  const runTest = async () => {
    setBusy("test");
    try { setTest((await api.post(`/api/connectors/${conn.ConnectorId}/test`)).data); }
    catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "test call failed" }); }
    setBusy(""); reload();
  };

  return (
    <Stepper nonLinear activeStep={step} orientation="vertical" sx={{ "& .MuiStepLabel-label": { fontSize: 13.5, fontWeight: 600 } }}>
      <Step completed={!!(cfg.server || conn.LastSyncAt)}>
        <StepButton onClick={() => setStep(0)}>Connection</StepButton>
        <StepContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, maxWidth: 460, mt: 1 }}>
            <TextField label="server" placeholder="localhost  ·  localhost\SQLEXPRESS  ·  HOST\INSTANCE" value={cfg.server || ""}
              sx={{ bgcolor: "#fff" }} onChange={(e) => setCfg({ ...cfg, server: e.target.value })} />
            <TextField label="database" placeholder="master" value={cfg.database || ""}
              sx={{ bgcolor: "#fff" }} onChange={(e) => setCfg({ ...cfg, database: e.target.value })} />
            <Select value={cfg.auth || "windows"} sx={{ bgcolor: "#fff" }} onChange={(e) => setCfg({ ...cfg, auth: e.target.value })}>
              <MenuItem value="windows" sx={{ fontSize: 12.5 }}>Windows auth (local, trusted)</MenuItem>
              <MenuItem value="sql" sx={{ fontSize: 12.5 }}>SQL login</MenuItem>
            </Select>
            {sqlAuth && <TextField label="username" value={cfg.username || ""} sx={{ bgcolor: "#fff" }}
              onChange={(e) => setCfg({ ...cfg, username: e.target.value })} />}
            {sqlAuth && <TextField label={conn.HasSecret ? "password (saved — type to replace)" : "password"} type="password"
              value={secret} onChange={(e) => setSecret(e.target.value)} sx={{ bgcolor: "#fff" }} />}
            <Select value={cfg.driver || ""} displayEmpty sx={{ bgcolor: "#fff" }} onChange={(e) => setCfg({ ...cfg, driver: e.target.value })}>
              <MenuItem value="" sx={{ fontSize: 12.5 }}>(auto — newest installed driver)</MenuItem>
              {drivers.map((d) => <MenuItem key={d} value={d} sx={{ fontSize: 12.5 }}>{d}</MenuItem>)}
            </Select>
            <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
              <Button variant="contained" disableElevation disabled={busy === "save"} onClick={save}>
                {busy === "save" ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : "Save & continue"}</Button>
              {msg && <Typography variant="body2" sx={{ color: "#15803d", fontWeight: 600 }}>{msg}</Typography>}
            </Box>
          </Box>
        </StepContent>
      </Step>
      <Step completed={!!(conn.LastSyncAt && !conn.LastError)}>
        <StepButton onClick={() => setStep(1)}>Test connection</StepButton>
        <StepContent>
          <Typography variant="body2" sx={{ color: DIM, mb: 1, mt: 0.5 }}>Connects for real and reports the server version — every scheduled report inherits this connection.</Typography>
          <Button variant="contained" disableElevation disabled={busy === "test"} onClick={runTest}
            startIcon={busy === "test" ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : <BoltIcon sx={{ fontSize: 15 }} />}>Test</Button>
          {test && <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: test.ok ? "#15803d" : "#b91c1c" }}>
            {test.ok ? "✓" : "✗"} {test.detail}{test.ms != null ? ` · ${test.ms}ms` : ""}</Typography>}
          {!test && conn.LastError && <Typography variant="body2" sx={{ mt: 1, color: "#b91c1c" }}>✗ {conn.LastError}</Typography>}
        </StepContent>
      </Step>
    </Stepper>
  );
}

/* ── Remote Windows (WinRM) detail: machine name + live probe; reports live on Reports ── */
function WinrmDetail({ conn, reload, onBack }) {
  const [tab, setTab] = useState("Connection");
  const [cfg, setCfg] = useState(parse(conn?.ConfigJson));
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  if (!conn) return null;

  const save = async () => {
    setBusy("save"); setMsg("");
    try {
      await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, ConfigJson: JSON.stringify(cfg), Active: true });
      setMsg("saved ✓"); reload();
    } catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "save failed" }); }
    setBusy("");
  };
  const runTest = async () => {
    setBusy("test");
    try { setTest((await api.post(`/api/connectors/${conn.ConnectorId}/test`)).data); }
    catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "test call failed" }); }
    setBusy(""); reload();
  };

  return (
    <Box sx={{ maxWidth: 980, mx: "auto" }}>
      <Crumb section="Connectors" onBack={onBack} title="Remote Windows (WinRM)" />
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>
        Run PowerShell ON a machine you can RDP into (your Windows credentials) — the connection only;
        build the scheduled reports on the Reports tab.
      </Typography>
      <UnderTabs tabs={["Connection", "Guide"]} value={tab} onChange={setTab} />
      {tab === "Guide" && <Steps steps={WINRM_HOWTO} />}
      {tab === "Connection" && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, maxWidth: 460, mt: 1 }}>
          <TextField label="machine name" placeholder="AZWEB01" value={cfg.host || ""} sx={{ bgcolor: "#fff" }}
            onChange={(e) => setCfg({ ...cfg, host: e.target.value })} />
          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
            <Button variant="contained" disableElevation disabled={busy === "save"} onClick={save}>
              {busy === "save" ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : "Save"}</Button>
            <Button variant="outlined" disabled={busy === "test" || !cfg.host} onClick={runTest}
              startIcon={busy === "test" ? <CircularProgress size={12} /> : <BoltIcon sx={{ fontSize: 15 }} />}>Test</Button>
            {msg && <Typography variant="body2" sx={{ color: "#15803d", fontWeight: 600 }}>{msg}</Typography>}
          </Box>
          {test && <Typography variant="body2" sx={{ fontWeight: 600, color: test.ok ? "#15803d" : "#b91c1c" }}>
            {test.ok ? "✓" : "✗"} {test.detail}{test.ms != null ? ` · ${test.ms}ms` : ""}</Typography>}
          {!test && conn.LastError && <Typography variant="body2" sx={{ color: "#b91c1c" }}>✗ {conn.LastError}</Typography>}
        </Box>
      )}
      <RemoveConnection conn={conn} reload={reload} onBack={onBack} />
    </Box>
  );
}

/* ── What each DISCOVERED cloud object does. Same shape as the GitHub card's per-repo
   pickers, and the same reason: one bucket is a report source, the next should put every
   new file on the Timeline - that is a per-OBJECT decision, not a per-connection one.
   'report' is the default and polls nothing: the object is simply available on the
   Reports tab. Picking saves instantly. ── */
const CLOUD_MODES = [
  ["report", "report only — selectable on the Reports tab, never polled"],
  ["feed", "feed — new items appear on the Timeline, never become work"],
  ["tasks", "tasks — new items go through triage and can become work"],
  ["off", "off — ignored entirely"],
];
// prefix -> (short type label, filter pill label). The prefix IS the type, so one place
// turns s3://… into "S3 bucket" for the row and "S3 buckets" for the pill.
const OBJ_TYPES = {
  "s3://": ["S3 bucket", "S3 buckets"],
  "logs://": ["CloudWatch log group", "log groups"],
  "blob://": ["blob container", "blob containers"],
  "law://": ["Log Analytics workspace", "workspaces"],
};
const objType = (addr) => Object.keys(OBJ_TYPES).find((p) => addr.startsWith(p)) || "";
const regionOf = (s) => { try { return JSON.parse(s.ConfigJson || "{}").region || ""; } catch { return ""; } };
const OBJ_KIND = (addr) => (OBJ_TYPES[objType(addr)] || ["object"])[0];
const objName = (addr) => addr.slice(objType(addr).length) || addr;
const PAGE_OBJ = 40;   // a 100-row wall is not a list; the rest is one click away

function CloudObjects({ conn, meta, objects, reload }) {
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");     // "" = every type
  const [mode, setMode] = useState("");     // "" = every mode
  const [limit, setLimit] = useState(PAGE_OBJ);
  const [bulk, setBulk] = useState("");
  const setOne = async (s, m) => {
    await api.post("/api/sources", { SourceId: s.SourceId, ConfigJson: JSON.stringify({ ...parse(s.ConfigJson), mode: m }) });
    reload();
  };
  const rediscover = async () => {
    setBusy(true);
    try { await api.post(`/api/connectors/${conn.ConnectorId}/test`); } catch { /* the card shows the error */ }
    setBusy(false); reload();
  };
  const modeOf = (s) => parse(s.ConfigJson).mode || "report";
  const needle = q.trim().toLowerCase();
  const shown = objects.filter((s) => (!kind || objType(s.Address) === kind)
    && (!mode || modeOf(s) === mode)
    && (!needle || s.Address.toLowerCase().includes(needle)));
  // the type pills only offer types this connection actually discovered
  const kinds = Object.keys(OBJ_TYPES).filter((p) => objects.some((s) => objType(s.Address) === p));
  // one decision for a whole filtered set: 46 buckets where 40 are amplify noise is a
  // search for "amplify" and one click, not 40 dropdowns
  const setAllShown = async (m) => {
    setBulk(m);
    for (const s of shown) {
      await api.post("/api/sources", { SourceId: s.SourceId, ConfigJson: JSON.stringify({ ...parse(s.ConfigJson), mode: m }) });
    }
    setBulk(""); reload();
  };
  return (
    <Box sx={{ mt: 3, maxWidth: 760 }}>
      <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13.5 }}>
        What you have access to — and what each one does
      </Typography>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5, mb: 1 }}>
        Discovery asks your {meta.title.includes("Azure") ? "app registration" : "keys"} what they can see and lists
        it here. Everything arrives as <b>report only</b>: available to the Reports tab, nothing polled. Switch one
        to <b>feed</b> or <b>tasks</b> and Taskuary starts watching it on every sync.
      </Typography>
      <Button size="small" variant="outlined" onClick={rediscover} disabled={busy} sx={{ mb: 1.5 }}
        startIcon={busy ? <CircularProgress size={11} /> : <SyncIcon sx={{ fontSize: 14 }} />}>
        {busy ? "Discovering…" : objects.length ? "Re-run discovery" : "Discover what I can access"}
      </Button>
      {!objects.length ? (
        <Empty>Nothing discovered yet — save the credentials above and press Discover.</Empty>
      ) : (
        <>
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap", mb: 1 }}>
            <TextField size="small" placeholder="search by name…" value={q}
              onChange={(e) => { setQ(e.target.value); setLimit(PAGE_OBJ); }}
              sx={{ bgcolor: "#fff", width: 230 }}
              InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon sx={{ fontSize: 16, color: FAINT }} /></InputAdornment> }} />
            {kinds.length > 1 && (
              <FilterPills value={kind} onChange={(v) => { setKind(v); setLimit(PAGE_OBJ); }}
                options={[{ key: "", label: "all", n: objects.length },
                  ...kinds.map((p) => ({ key: p, label: OBJ_TYPES[p][1],
                    n: objects.filter((s) => objType(s.Address) === p).length }))]} />
            )}
            <FilterPills value={mode} onChange={(v) => { setMode(v); setLimit(PAGE_OBJ); }}
              options={[{ key: "", label: "any mode" },
                ...CLOUD_MODES.map(([v]) => ({ key: v, label: v }))
                  .filter((o) => objects.some((s) => modeOf(s) === o.key))]} />
          </Box>
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap", mb: 0.5 }}>
            <Typography variant="caption" sx={{ color: FAINT }}>
              {shown.length === objects.length ? `${objects.length} objects`
                : `${shown.length} of ${objects.length} shown`}
            </Typography>
            {shown.length > 0 && shown.length < objects.length && (
              <>
                <Typography variant="caption" sx={{ color: FAINT }}>· set all {shown.length} shown to</Typography>
                {CLOUD_MODES.map(([v, label]) => (
                  <Box key={v} component="span" title={label}
                    onClick={() => !bulk && setAllShown(v)}
                    sx={{ fontSize: 11, fontWeight: 700, color: bulk ? FAINT : "#4f46e5", cursor: bulk ? "default" : "pointer",
                      "&:hover": { textDecoration: bulk ? "none" : "underline" } }}>
                    {bulk === v ? `${v}…` : v}
                  </Box>
                ))}
              </>
            )}
          </Box>
          {!shown.length && <Empty>Nothing matches that search.</Empty>}
          {shown.slice(0, limit).map((s) => (
            <Box key={s.SourceId} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1, borderBottom: `1px solid ${BORDER}` }}>
              <Box sx={{ minWidth: 0, flex: 1 }}>
                <Typography sx={{ ...mono, color: INK, fontSize: 12.5 }} noWrap title={s.Address}>{objName(s.Address)}</Typography>
                <Typography variant="caption" sx={{ color: FAINT }}>
                  {OBJ_KIND(s.Address)}
                  {/* two regions can hold log groups with the SAME name - without this they are
                      two identical rows and no way to tell which one you just switched on */}
                  {regionOf(s) ? ` · ${regionOf(s)}` : ""}
                  {s.LastPolledAt ? ` · polled ${timeAgo(s.LastPolledAt)}` : ""}
                </Typography>
              </Box>
              <Select size="small" value={modeOf(s)} onChange={(e) => setOne(s, e.target.value)}
                sx={{ fontSize: 11.5, height: 26, minWidth: 108, ".MuiSelect-select": { py: 0.4 } }}>
                {CLOUD_MODES.map(([v, label]) => (
                  <MenuItem key={v} value={v} sx={{ fontSize: 12 }} title={label}>{v}</MenuItem>
                ))}
              </Select>
            </Box>
          ))}
          {shown.length > limit && (
            <Button size="small" onClick={() => setLimit(limit + PAGE_OBJ * 2)} sx={{ mt: 1 }}>
              show {Math.min(PAGE_OBJ * 2, shown.length - limit)} more of {shown.length - limit}
            </Button>
          )}
        </>
      )}
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1 }}>
        <b>feed</b> and <b>tasks</b> watch for what is NEW since the last sync: a bucket reports each new object, a
        log group batches the matching lines into one item, a workspace runs its saved query. An object nothing
        discovered can still be typed in by hand as a report source on the Reports tab.
      </Typography>
    </Box>
  );
}

/* ── shared detail for the DATA_META cards (database / aws / azure): fields + write-only
   secret + live Test; the connection only - reports are built on the Reports tab. ── */
function DataDetail({ conn, meta, sources, reload, onBack }) {
  const [tab, setTab] = useState("Connection");
  const [cfg, setCfg] = useState(parse(conn?.ConfigJson));
  const [secret, setSecret] = useState("");
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  if (!conn) return null;
  const objects = (sources || []).filter((s) => s.Channel === conn.Type);

  const save = async () => {
    setBusy("save"); setMsg("");
    try {
      const body = { ConnectorId: conn.ConnectorId, ConfigJson: JSON.stringify(cfg), Active: true };
      if (secret) body.Secret = secret;
      await api.post("/api/connectors", body);
      setMsg("saved ✓"); setSecret(""); reload();
    } catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "save failed" }); }
    setBusy("");
  };
  const runTest = async () => {
    setBusy("test");
    try { setTest((await api.post(`/api/connectors/${conn.ConnectorId}/test`)).data); }
    catch (e) { setTest({ ok: false, detail: e?.response?.data?.detail || "test call failed" }); }
    setBusy(""); reload();
  };

  return (
    <Box sx={{ maxWidth: 980, mx: "auto" }}>
      <Crumb section="Connectors" onBack={onBack} title={meta.title} />
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>
        {meta.desc} The connection only — build the scheduled reports on the Reports tab.
      </Typography>
      <UnderTabs tabs={["Connection", "Guide"]} value={tab} onChange={setTab} />
      {tab === "Guide" && <Steps steps={meta.howto} />}
      {tab === "Connection" && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, maxWidth: 560, mt: 1 }}>
          {meta.fields.map(([label, key, ph]) => (
            <TextField key={key} label={label} placeholder={ph} value={cfg[key] || ""} sx={{ bgcolor: "#fff" }}
              multiline={key === "conn_str"} minRows={key === "conn_str" ? 2 : undefined}
              onChange={(e) => setCfg({ ...cfg, [key]: e.target.value })} />
          ))}
          <TextField label={conn.HasSecret ? `${meta.secretLabel} — saved, type to replace` : meta.secretLabel}
            type="password" value={secret} onChange={(e) => setSecret(e.target.value)} sx={{ bgcolor: "#fff" }}
            helperText="Write-only: stored server-side, never returned to the browser." />
          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
            <Button variant="contained" disableElevation disabled={busy === "save"} onClick={save}>
              {busy === "save" ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : "Save"}</Button>
            <Button variant="outlined" disabled={busy === "test"} onClick={runTest}
              startIcon={busy === "test" ? <CircularProgress size={12} /> : <BoltIcon sx={{ fontSize: 15 }} />}>
              {meta.discovers ? "Test & discover" : "Test"}</Button>
            {msg && <Typography variant="body2" sx={{ color: "#15803d", fontWeight: 600 }}>{msg}</Typography>}
          </Box>
          {test && <Typography variant="body2" sx={{ fontWeight: 600, color: test.ok ? "#15803d" : "#b91c1c" }}>
            {test.ok ? "✓" : "✗"} {test.detail}{test.ms != null ? ` · ${test.ms}ms` : ""}</Typography>}
          {!test && conn.LastError && <Typography variant="body2" sx={{ color: "#b91c1c" }}>✗ {conn.LastError}</Typography>}
        </Box>
      )}
      {tab === "Connection" && meta.discovers && (
        <CloudObjects conn={conn} meta={meta} objects={objects} reload={reload} />
      )}
      <RemoveConnection conn={conn} reload={reload} onBack={onBack} />
    </Box>
  );
}

/* What a connection IS to the hub. Three independent jobs - a system can do all three,
   or just be something the agents are allowed to touch. */
const ROLE_META = {
  trigger: ["Inbound trigger — creates work", "Poll it for new items, run them through triage, open tasks and draft replies. This is what turns a connection into work (mail, chats, GitHub issues…)."],
  feed: ["Timeline feed — shows, never assigns", "Poll it and show every new item on the Timeline, but stop there: no triage, no AI call, no task. Good for GitHub issues or a chatty channel you want to SEE without being handed."],
  report: ["Report source", "Selectable on the Reports tab: query it on a schedule and put the (optionally AI-summarized) result on the Timeline."],
  tool: ["Agent tool", "Named for the agents in SOUL.md as a system they may use — pull data from it, create and update things in it while working a task."],
  notify: ["Notifications", "The outbound direction: Taskuary pushes a ping into this chat when something needs you. Name the chat in Credentials; what qualifies is Settings → Notifications."],
};

// The GitHub DECISIONS live on the GitHub card: is GitHub the issue tracker for tasks (agents
// open/update issues as the team expects) and may agents push/deploy on their own. These were
// buried in Settings as global switches, which read as Taskuary behavior instead of what they
// are - how this team uses this connector. Either can be on without the other.
const GITHUB_PERMS = [
  ["use_as_tracker", "GitHub is the issue tracker",
   "On: your team runs on GitHub issues, so agents open and update them for the work they do. Off (default): Taskuary is the tracker - the task is the record - and agents never create issues or tracker items unless a task's ask explicitly says to."],
  ["agents_push", "Agents may push / deploy",
   "On: agents push and deploy as the work needs. Off (default): commits stay local for your review - you push - and only a task whose ask explicitly says to push may. Force-pushes and archived repositories stay forbidden either way."],
  ["reply_comments", "Reply to issue/PR authors",
   "On: questions from GitHub get a drafted reply, finished work drafts a close-out note, and approving one posts it as a PUBLIC comment on the issue/PR. Off (default): GitHub items never get reply drafts - questions file with their triage reason, finished work just closes with its report, and nothing is ever posted to a public thread on your behalf."],
];

const GithubPerms = ({ conn, reload }) => {
  const cfg = JSON.parse(conn.ConfigJson || "{}");
  const toggle = async (key) => {
    await api.post("/api/connectors", { ConnectorId: conn.ConnectorId,
      ConfigJson: JSON.stringify({ ...cfg, [key]: !cfg[key] }) });
    reload();
  };
  return (
    <Box sx={{ mt: 1, maxWidth: 620 }}>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.5 }}>
        OUTBOUND — what the coding agent may do <b>on GitHub</b> while it works your tasks. Unrelated
        to the <b>Inbound</b> step above, which only controls what comes <b>in</b> to your timeline.
      </Typography>
      {GITHUB_PERMS.map(([key, label, desc]) => (
        <Box key={key} sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, py: 1.25, borderBottom: `1px solid ${BORDER}` }}>
          <Switch checked={!!cfg[key]} onChange={() => toggle(key)} sx={{ mt: -0.5 }} />
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13 }}>{label}</Typography>
            <Typography variant="body2" sx={{ color: DIM }}>{desc}</Typography>
          </Box>
        </Box>
      ))}
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1 }}>
        Both land in the instruction every agent session is seeded with, and in the SOUL.md line
        describing this connection. A task whose ask explicitly says "open an issue" or "push"
        may always do so, whatever these say.
      </Typography>
    </Box>
  );
};

const useRoles = (conn, reload) => {
  const roles = new Set(String(conn.Roles || "").split(",").filter(Boolean));
  const toggle = async (r) => {
    const next = new Set(roles);
    if (next.has(r)) next.delete(r); else next.add(r);
    // a trigger already puts its items on the timeline; holding both would just be a
    // contradiction the poller has to resolve
    if (r === "trigger" && next.has("trigger")) next.delete("feed");
    if (r === "feed" && next.has("feed")) next.delete("trigger");
    await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, Roles: [...next].join(",") });
    reload();
  };
  return [roles, toggle];
};

const RoleRow = ({ on, onToggle, label, desc }) => (
  <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, py: 1.25, borderBottom: `1px solid ${BORDER}` }}>
    <Switch checked={on} onChange={onToggle} sx={{ mt: -0.5 }} />
    <Box sx={{ minWidth: 0 }}>
      <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13 }}>{label}</Typography>
      <Typography variant="body2" sx={{ color: DIM }}>{desc}</Typography>
    </Box>
  </Box>
);

/* Authority: the ceiling on what an agent may do THROUGH this connection, once it is a tool.
   The role says the agents may use Jira; this says whether they may close a ticket in it.
   Read is the safe floor and the default for every tracker - a connection only gains a verb
   when the owner hands it over. */
const SCOPE_META = {
  read: ["Read only", "Look, never touch: list, fetch, search, query. Nothing upstream changes. The safe default."],
  write: ["Read and write", "The everyday work as well: create, update, comment, assign, complete, send. No deleting, no closing, no running code."],
  admin: ["Full authority", "Everything, including the destructive and the structural: delete, close, archive, manage access, run scripts on a box. Hand this over deliberately."],
};
const SCOPE_KEYS = ["read", "write", "admin"];

const AuthorityRow = ({ conn, reload }) => {
  const fallback = String(conn.ScopeDefault || "read").toLowerCase();
  const current = String(conn.Scope || "").toLowerCase();
  const [busy, setBusy] = useState(false);
  const set = async (s) => {
    setBusy(true);
    try { await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, Scope: s }); reload(); }
    finally { setBusy(false); }
  };
  return (
    <Box sx={{ pt: 1.5 }}>
      <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13 }}>Authority — how far the agents may reach</Typography>
      <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>
        Only bites when this is an agent tool. An action nobody has classified counts as write,
        so a read-only connection stays read-only even for a verb we have never seen.
      </Typography>
      {SCOPE_KEYS.map((s) => (
        <Box key={s} sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, py: 1, borderBottom: `1px solid ${BORDER}` }}>
          <Radio checked={(current || fallback) === s} disabled={busy} onChange={() => set(s)} sx={{ mt: -0.75 }} />
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13 }}>
              {SCOPE_META[s][0]}{!current && fallback === s ? " — default" : ""}
            </Typography>
            <Typography variant="body2" sx={{ color: DIM }}>{SCOPE_META[s][1]}</Typography>
          </Box>
        </Box>
      ))}
    </Box>
  );
};

const RoleStep = ({ conn, reload, only }) => {
  const [roles, toggle] = useRoles(conn, reload);
  const keys = only || Object.keys(ROLE_META);
  const chat = String(parse(conn.ConfigJson).notify_chat || "").trim();
  return (
    <Box sx={{ mt: 1, maxWidth: 620 }}>
      {keys.map((key) => (
        <RoleRow key={key} on={roles.has(key)} onToggle={() => toggle(key)}
          label={ROLE_META[key][0]} desc={ROLE_META[key][1]} />
      ))}
      {keys.includes("notify") && roles.has("notify") && (
        <Typography variant="caption" sx={{ color: chat ? "#15803d" : "#b45309", display: "block", mt: 1, lineHeight: 1.45 }}>
          {chat
            ? `Pinging chat ${chat} · what goes out is Settings → Notifications`
            : "Name the chat in Credentials, or pings have nowhere to go."}
        </Typography>
      )}
      {keys.includes("tool") && <AuthorityRow conn={conn} reload={reload} />}
    </Box>
  );
};

/* ── the ONE inbound page: the switch, what each source's items do, and the agent prompt.
   These three used to live on three different steps (Role, Repositories, Credentials) and
   read as three unrelated settings - they are one decision: what from here becomes work,
   and what the agent is told about it. ── */
const GH_PROMPTS = [
  ["prompt_pr", "When the task came from a PULL REQUEST",
   "blank = the built-in: judge it — useful? safe? minimal? — check out the branch, run the tests, report a verdict; never merge"],
  ["prompt_issue", "When the task came from an ISSUE",
   "blank = the built-in: reproduce it, fix it when the fix is contained, otherwise report what it would take"],
];
const TASK_PROMPT = [["task_prompt", "For every task from this connection",
  "optional — rides into the agent's instructions alongside the message itself; blank = nothing extra"]];
const PROMPTABLE = new Set(["outlook", "teams", "slack", "telegram", "whatsapp", "gmail", "imap",
  "jira", "asana", "monday"]);
const promptsFor = (t) => (t === "github" ? GH_PROMPTS : PROMPTABLE.has(t) ? TASK_PROMPT : []);

const ghInboundExplicit = (mine) => mine.some((s) => {
  const c = parse(s.ConfigJson);
  return ["tasks", "feed"].includes(c.issues) || ["tasks", "feed"].includes(c.prs);
});
const inboundDone = (conn, mine) => {
  const roles = new Set(String(conn.Roles || "").split(",").filter(Boolean));
  return roles.has("trigger") || roles.has("feed") || (conn.Type === "github" && ghInboundExplicit(mine));
};

const InboundStep = ({ conn, m, mine, reload }) => {
  const [roles, toggle] = useRoles(conn, reload);
  const [cfg, setCfg] = useState(parse(conn.ConfigJson));
  const [saved, setSaved] = useState("");
  useEffect(() => { setCfg(parse(conn.ConfigJson)); }, [conn.ConfigJson]);
  const gh = conn.Type === "github";
  const on = roles.has("trigger") || roles.has("feed") || (gh && ghInboundExplicit(mine));
  const prompts = promptsFor(conn.Type);
  const savePrompts = async () => {
    await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, ConfigJson: JSON.stringify(cfg) });
    setSaved("saved ✓"); setTimeout(() => setSaved(""), 2500); reload();
  };
  return (
    <Box sx={{ mt: 1, maxWidth: 640 }}>
      {/* 1 — the switch: does this connection create work at all */}
      <Typography variant="caption" sx={{ ...mono, color: FAINT, letterSpacing: 1, fontSize: 10 }}>
        1 · DOES IT CREATE WORK
      </Typography>
      {["trigger", "feed"].map((key) => (
        <RoleRow key={key} on={roles.has(key)} onToggle={() => toggle(key)}
          label={ROLE_META[key][0]} desc={ROLE_META[key][1]} />
      ))}
      {/* 2 — github only: what each repo's items do, overriding the switch per repo */}
      {gh && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="caption" sx={{ ...mono, color: FAINT, letterSpacing: 1, fontSize: 10 }}>
            2 · PER REPO — WHAT ISSUES AND PRS DO
          </Typography>
          <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5, mb: 0.5 }}>
            <b>tasks</b> = through triage (never auto-dispatched — you promote what deserves work),
            <b> feed</b> = shown on the Timeline only, <b>off</b> = ignored. A picker set here pulls
            that repo whatever the switches above say; picking saves instantly.
          </Typography>
          {mine.filter((s) => s.Active).map((s) => {
            const gc = parse(s.ConfigJson);
            return (
              <Box key={s.SourceId} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1, borderBottom: `1px solid ${BORDER}` }}>
                <Typography sx={{ ...mono, color: INK, flex: 1, fontSize: 13 }} noWrap>{s.Address}</Typography>
                {["issues", "prs"].map((kind) => (
                  <Select key={kind} size="small" value={gc[kind] || (kind === "prs" ? "off" : "tasks")}
                    sx={{ fontSize: 11.5, height: 26, ".MuiSelect-select": { py: 0.4 } }}
                    onChange={async (e) => {
                      await api.post("/api/sources", { SourceId: s.SourceId,
                        ConfigJson: JSON.stringify({ ...gc, [kind]: e.target.value }) });
                      reload();
                    }}>
                    {["tasks", "feed", "off"].map((v) => (
                      <MenuItem key={v} value={v} sx={{ fontSize: 12 }}>{kind === "prs" ? "PRs" : "issues"}: {v}</MenuItem>
                    ))}
                  </Select>
                ))}
              </Box>
            );
          })}
        </Box>
      )}
      {/* 3 — the standing prompt, right where inbound is decided */}
      {prompts.length > 0 && (
        <Box sx={{ mt: 2, opacity: on ? 1 : 0.5 }}>
          <Typography variant="caption" sx={{ ...mono, color: FAINT, letterSpacing: 1, fontSize: 10 }}>
            {gh ? "3" : "2"} · WHAT THE AGENT IS TOLD ABOUT WORK FROM HERE
            {on ? "" : " — turn inbound on above first"}
          </Typography>
          {prompts.map(([key, label, hint]) => (
            <TextField key={key} fullWidth multiline minRows={2} label={label} helperText={hint}
              value={cfg[key] || ""} onChange={(e) => setCfg({ ...cfg, [key]: e.target.value })}
              sx={{ bgcolor: "#fff", mt: 1.5 }} />
          ))}
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", mt: 1.5 }}>
            <Button size="small" variant="contained" disableElevation onClick={savePrompts}>Save prompts</Button>
            {saved && <Typography variant="body2" sx={{ color: "#15803d", fontWeight: 600 }}>{saved}</Typography>}
          </Box>
        </Box>
      )}
    </Box>
  );
};

const Steps = ({ steps }) => (
  <Box sx={{ maxWidth: 720, mx: "auto" }}>
    {steps.map((step, i) => (
      <Box key={i} sx={{ display: "flex", gap: 1.5, py: 1.25, borderBottom: `1px solid ${BORDER}` }}>
        <Box sx={{ ...mono, width: 24, height: 24, borderRadius: "50%", bgcolor: "#eef0ff", color: "#4f46e5",
          fontSize: 12, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{i + 1}</Box>
        <Typography variant="body2" sx={{ color: INK, lineHeight: 1.55 }}>{step}</Typography>
      </Box>
    ))}
  </Box>
);

A connection is one account Taskuary may read — a mailbox, a chat, a repository, a tracker, a
database, a bank feed. Each card on the **Connections** page is one named connection, and its
*roles* decide what Taskuary is allowed to do with what it finds there.

Nothing is polled without an enabled role. A card with no role is a saved credential and nothing
more.

Every field on a card saves itself - its name, credentials, roles, what each repository or source does,
processing, the agent's prompts. A switch or a pick saves at once; typing saves once it pauses or the
box is left; a password or key saves when its box is left, and is never shown again. A quiet **Saved**
appears by what was saved, or **Not saved** and why. There is no Save button: the last step is **Test**.

**Remove connection** asks once, saying what stays (what it brought in), what goes (its sign-in and
settings) and what stops working with it; on yes the card is gone and the page is back on the list,
where **Undo** brings it back for ten minutes.

## What a connection is

One card is one account, not one kind of system. Rename it for the account or environment it
represents — **Ops mailbox** rather than **IMAP** — and use **Add another** on the card to
connect the same kind again. Two mailboxes, two GitHub organisations, or separate production and
staging databases are all normal, and each keeps its own roles, its own schedule and its own name
in every prompt.

Secrets are write-only in the interface: you can replace a password, never read one back. A
database connection string may contain `{password}` so the saved password stays separate from the
readable part of the configuration.

A key or a password goes on its card, never into the Assistant's chat. Ask the Assistant on a card and it
fills the other boxes and presses **Test** for you; a secret box is yours to paste into.

## The five roles

A role is a permission, not a ranking.

| Role | What Taskuary may do |
|---|---|
| **trigger** | Send inbound items through triage — they can become tasks, drafts or FYIs |
| **feed** | Show inbound items on the rail to read, unread by any AI |
| **report** | Make the source available to scheduled reports |
| **tool** | Let agents query it while working a task |

:::rule Feed is not a quieter trigger
`feed` means no model ever reads those items — cheaper, quieter, and no verdict to argue with.
`ignore` is a judgement *about* a message and happens further down, in your routing policies. If
a source is noisy but you still want to see it, make it a feed.
:::

A card can hold more than one role. A mailbox is usually `trigger` and `tool`; a database is
usually `report` and `tool`.

## Mail

| System | Notes |
|---|---|
| **Outlook** | Mail and calendar, through Microsoft sign-in or a tenant app registration - answering invites and booking meetings needs Calendars.ReadWrite, which a sign-in from before it asks for again |
| **Gmail and IMAP** | Any IMAP mailbox. Approved replies go back through the provider's SMTP, in-thread. A Gmail card can also sign in with Google, which adds the calendar and contacts |

### How Microsoft sign-in works

**Outlook and Teams sign in through your company's own Microsoft app.** Taskuary ships no
Microsoft app of its own, so nothing goes through anybody else's Azure: your IT registers one app
in your own Microsoft Entra ID, once, and every Outlook and Teams card in your company uses it. The
card shows these steps until its two IDs are filled in:

1. Microsoft Entra ID → **App registrations** → **New registration** → name it Taskuary, accounts
   in this organizational directory only (single tenant) → Register.
2. **Authentication** → **Add a platform** → **Mobile and desktop applications** → redirect URI
   `http://localhost/api/ms/callback`. Entra ignores the port of a `localhost` redirect for a
   public client, so this one entry covers whatever port Taskuary listens on; the card also shows
   this install's own, `http://localhost:<port>/api/ms/callback` (7787 unless changed), if
   Microsoft asks for it.
3. **Authentication** → **Allow public client flows: Yes** → Save.
4. **API permissions** → Add a permission → Microsoft Graph → **Delegated**, then **Grant admin
   consent**:
   - Outlook: `offline_access User.Read Mail.ReadWrite Mail.Send Calendars.ReadWrite People.Read Contacts.Read`
   - Teams: `offline_access User.Read User.ReadBasic.All Chat.ReadWrite ChatMessage.Send People.Read`
   - Plus `Files.ReadWrite` only on a card where the owner turns on *Allow saving files*.
   One app can serve both cards: list both sets.
5. From the app's **Overview**, copy the **Application (client) ID** and the **Directory (tenant)
   ID** into the card. Then sign in, in the browser or with a code.

No client secret: a sign-in app is public by design. Someone running their own Taskuary for
several people can name one app for the whole install with the `TASKUARY_MS_CLIENT_ID` environment
variable instead; a card's own IDs still win.

**Sign in with Microsoft** opens Microsoft's own sign-in page in your browser. You sign in there,
as you would anywhere else, and accept; the tab comes back to Taskuary on this computer and says
*Signed in - you can close this tab*, and the card shows who signed in. Taskuary never sees your
password.

Under the hood this is the OAuth 2.0 authorization-code flow with PKCE, for a public client (no
client secret): the sign-in carries a one-time `state` and an S256 code challenge, the code comes
back to `http://localhost:<port>/api/ms/callback` on the machine Taskuary runs on, and is redeemed
there with the matching verifier. The return is accepted once, only for the sign-in the card
started, only from this machine, and only for ten minutes. The tab never shows a token. The
refresh token is kept as the card's secret and renews itself from then on.

**Sign in with a code instead** - the small link beside the button - is the device-code flow, with
the same app. It is for a Taskuary your browser cannot reach on `localhost` (one running on another
computer, or a headless box) or a company that prefers it, and it needs *Allow public client flows:
Yes*. It shows a code to type at microsoft.com/devicelogin. Some organisations block it with a
Conditional Access policy.

**What Microsoft's errors mean:**

- **AADSTS50011** (the redirect URI does not match): the app does not list
  `http://localhost/api/ms/callback` under *Mobile and desktop applications* yet. Microsoft stops
  on its own page and never comes back; the card says so while it waits.
- **AADSTS700016** (no such app in the directory): the Application (client) ID or the Directory
  (tenant) ID on the card is wrong. Copy both again from the app's Overview page.
- **AADSTS50194**: the app is single-tenant and the card has no Directory (tenant) ID.
- **AADSTS7000218** (a client secret is required): the redirect is on the *Web* platform instead
  of *Mobile and desktop applications*, or public client flows are off.
- **"Need admin approval"**, **AADSTS65001**, **AADSTS90094**, **AADSTS900971** ("No reply address
  provided"), **AADSTS50105** (the app is limited to people IT assigned) or **AADSTS53003** (a
  Conditional Access policy): admin consent has not been granted yet. After a minute and a half
  the card says so and shows an approval link. Your IT admin opens it once, signs in and clicks
  Accept - the same as *Grant admin consent* on the app's API permissions page. After Accept their
  browser goes to `http://localhost/api/ms/callback`: if the page says it can't connect, that is
  expected - the approval is done. Then press Sign in with Microsoft again.

**A card that signed in before Taskuary stopped shipping a Microsoft app** keeps its sign-in on
record but reads nothing until its company's app is on it: the card says so, shows the steps, and
signing in again with the two IDs picks up where it left off. Nothing already in Taskuary is lost.

:::note For an IT admin
- **No device-code flow by default.** Sign-in is the authorization-code flow with PKCE in the
  system browser, so a Conditional Access policy that blocks device-code authentication does not
  block Taskuary. Only a user who chooses *Sign in with a code instead* uses the device-code flow.
- **The approval link** is Microsoft's standard sign-in page (`/oauth2/v2.0/authorize`) for your
  app with `prompt=admin_consent`, returning to `http://localhost/api/ms/callback`: on the computer
  Taskuary runs on it shows *Approved*; anywhere else the page does not load, and the approval
  stands all the same. Nothing is signed in by it - the code it brings back is never used.
:::

Taskuary reads your **Sent** folder as well as your inbox. That is what makes "has this been
answered?" a real question rather than a guess, and it is what `STYLE.md`'s **Generate from
history** learns your writing voice from.

:::note A shared mailbox needs saying so
If the mailbox is shared, mail addressed to the team reads as mail addressed to you unless
Taskuary knows otherwise. Name your own addresses in `SOUL.md` so triage can tell "someone asked
me" from "someone asked the team".
:::

### Finding people: the permissions it asks for

To, Cc and the other recipient boxes search everyone Taskuary knows by name, company or any part
of an address. Each sign-in also asks for read-only access to the people the account knows:

| Sign-in | Asks for | What the search gains |
|---|---|---|
| **Outlook** (Sign in with Microsoft) | `People.Read`, `Contacts.Read` | The people you write with, including outside contacts and their companies, and your Outlook contacts |
| **Teams** (Sign in with Microsoft) | `People.Read`, besides `User.ReadBasic.All` | Your organisation's people, not only the chats already seen here. Picking one sends into your one-to-one chat with them, and opens that chat if you don't have one yet |
| **Gmail** (Sign in with Google for the calendar) | `contacts.readonly`, `contacts.other.readonly`, `directory.readonly` | Your Google contacts, the addresses Gmail saved for you, and your Workspace directory |

Microsoft lets each person consent to these themselves, without an admin, unless your
organisation limits user consent. In that case **Get the admin link** on the card asks for them
as well. On Google's consent page each one is its own box, and only the calendar is required.

A sign-in made before Taskuary asked for these still works. The search skips what that sign-in
can't read, and the card says so. To add them on the Outlook or Teams card, sign out and sign in again. A Gmail card that
only has an App Password has no Google sign-in, so its contacts are not searched. The mail you
exchanged is still searched. Search answers are kept for ten minutes, and the people they found
are remembered so they can still be found offline.

### The signature under your emails

Every email Taskuary writes for you ends with one signature, taken from the first of these that has one:

1. the signature on the mailbox's own card (Connections, the card that sends as it)
2. **Settings → Replies → Email signature**
3. the mailbox's own signature, read from your sent mail: the closing lines it plainly
   shares — most of at least six recent mails, more than one line, with your name in it.
   A less certain one is only offered in Settings for you to confirm
4. the sign-off line in STYLE.md
5. your name

Gmail's own signature setting is not read yet, and Microsoft offers no way to read an Outlook
signature, so every mailbox uses its sent mail. It is read once a day and kept on the card.

## Chat

| System | Notes |
|---|---|
| **Teams**, **Slack** | Messages reach the rail through triage |
| **Telegram** | Bot-based inbound, approved in-chat replies, the Assistant walk on your phone; each chat is opt-in |
| **WhatsApp** | A local bridge for inbound messages, approved replies and the Assistant walk on your phone. Unofficial protocol — use a number you can afford to lose |
| **Discord** | Watches selected bot channels and posts approved replies back into the originating channel |
| **Apple Messages** | macOS only. Reads the Mac's local Messages history and replies through Messages.app; needs Full Disk Access and Automation permissions |
| **Mattermost**, **Rocket.Chat** | A server you host. Each watched channel is its own source, and approved replies post back into it. Rocket.Chat needs two values — the token and the user id issued beside it |
| **Matrix** | Any homeserver, matrix.org or your own. Replies go back as your account rather than a bot, so the account has to have joined the room |
| **Google Chat** | Spaces on the rail and replies back into them. Reuses the Gmail card's OAuth client, so there is one registration in Google Cloud rather than two |

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
| **Jira, Asana, Monday.com, ClickUp, Todoist** | Assigned work items reach the rail through triage |
| **Linear, Trello** | Assigned issues and cards |
| **Notion** | Pages shared with the integration appear as a feed when they change |
| **Sentry, PagerDuty** | New unresolved errors and open incidents join the same funnel |

A tracker is the clearest case for `trigger`: an issue assigned to you is, by definition, work
addressed to you, and triage settles most of them without an AI call at all.

### GitHub: what Close out does

The GitHub connection has a **Close out** step: what finishing a task does on GitHub when you press
**Close out**. These are your choices - what each repository *requires* (branch protection, required checks
and reviews) is read from GitHub for every pull request, and the card only offers what it allows.

| Setting | Choices (default first) | The token needs |
|---|---|---|
| Close out on a pull request | Merges it · Only closes the task | Contents: write |
| Merge method | Squash · Merge commit · Rebase - used when the repository allows it | (same) |
| Red checks the repository does not require | Merge anyway, with a note · Stop and ask me | - |
| Offer Update branch | on - when the pull request is behind and its author allows maintainer edits | Pull requests: write |
| Offer Re-run checks | on - re-runs the failed Actions jobs | Actions: write |
| Close out on an issue closes it | on | Issues: write |
| Post your reply as the close-out's comment | on - even with *Reply to issue/PR authors* off | Issues / Pull requests: write |
| Close out anyway, past the repository's own rules | **off** - admin tokens only, and only on your press | Administration |

A repository you follow can override the pull-request choice, the merge method and Close out anyway.
**Check the token** asks GitHub, per repository, whether the token may do what these settings turn on.

### Jira, Monday.com and Linear: what goes back

These three trackers can be written to as well as read. Every write waits for your press, because
each one reaches people: everyone on an item reads a comment, and the tracker tells the people
following an item when it moves or changes hands.

| Act | Jira (REST v3) | Monday.com | Linear |
|---|---|---|---|
| Comment | A comment on the issue | An update on the item | A comment on the issue |
| Move | A transition the workflow offers from where the issue stands | A label of the item's status column | A state of the team's workflow |
| Assign | One person Jira can assign it to | One person, set on the item's People column | One person in the workspace |
| Close | The transition to a status in Jira's *done* category | The label the status column marks as done | The team's first *completed* state |

**Close out on a tracker task.** When the agent on a task from one of these items finishes, Close
out proposes **comment and move to done**, with the comment drafted from the agent's result. You can
edit the comment, then press **Approve**. Taskuary reads the item again when the card is drawn. If
the tracker has no done state, or the workflow offers no move to it from the item's current status,
the card says so and Approve posts the comment alone. If the item is already done, it posts only the
comment.

**What an agent can do.** An agent proposes these acts with the types `jira_comment`, `jira_move`,
`jira_assign` and `jira_close`, and the same four for `monday_` and `linear_`. Without an item named,
the proposal is for the item its task came from. Each one waits on the task with an Approve button,
whatever permission the card has. A name that matches two people, or a status the workflow does not
offer, is refused and nothing is changed. A scheduled report never runs them.

Monday's board can have several status and People columns. The first of each is used unless the
card's settings name one (`status_column`, `people_column`).

## Data and report sources

The full list is long and grows; these are the ones worth knowing about by shape.

A data card feeds reports, dashboards and agent look-ups. It never puts work on your rail or your
task list: what it holds reaches you through a report you set up on it.

**Databases and files** — SQL Server, SQLite, SharePoint Lists, Google Sheets, a Windows/SMB
share, SFTP, REST and RSS, and any MCP server tool. **PostgreSQL**, **MySQL**, **ClickHouse**,
**Snowflake** and **BigQuery** each have their own card: the same executor with the dialect filled
in, the default port known and the missing driver named in the error you actually get. The older
**Any database (connection string)** card is still there for anything else with a SQLAlchemy URL,
including raw ODBC through pyodbc. All of them are reads — these cards ship no write verb at all,
and the engine's own user is the ceiling, so point them at a read-only account.

**Cloud and monitoring** — AWS (S3 buckets, CloudWatch log groups, arbitrary service calls),
Azure (blob containers, Log Analytics, arbitrary ARM paths, and it can reuse the Outlook app
registration), Microsoft Entra ID, Prometheus, Datadog, WinRM for PowerShell on a remote Windows
machine.

**Finance** — Sage Intacct, QuickBooks Online, Zoho Invoice, and bank and card feeds through
SimpleFIN or Teller. These are the cards where the read/write distinction bites: each ships at
`read`, so an agent proposes a bill or an invoice and you approve it on the task. Raising a card to
`write` is what lets a routing policy pass small, known items through without you.

**Selling on Amazon** — the **Amazon (Seller Central & Business)** card reads your seller reports:
sales & traffic (the Business Report), every order by order date, FBA inventory, settlements, or any
other report type Amazon offers by its name. It is a data card for reports, dashboards and agent
lookups, never a source of work, and it is read-only: the one thing it asks of Amazon is to build a
report it can download. To connect it, register a private developer profile and a self-authorized
app in Seller Central (Apps and Services → Develop Apps), copy the app's LWA client id and secret onto
the card, press **Authorize app** and paste the refresh token it shows, then pick the region (`na`,
`eu` or `fe`) and, optionally, the marketplace ids. Test lists the marketplaces the account sells in.
Vendor Central accounts do the same under Integration → API Integration. Amazon's quotas are small,
about one new report a minute, so a throttled call waits rather than fails, and a finished report is
kept for 15 minutes. See Amazon's [SP-API documentation](https://developer-docs.amazon.com/sp-api).

**Buying on Amazon Business** — the same card reads Amazon Business purchases for reconciliation:
every charge and refund in a window, one row per line (ASIN, quantity, price, tax, order and PO
number), each matched to its invoice number — a charge to its invoice, a refund to its credit memo.
It signs in the same way, with an app that holds the **Business Purchase Reconciliation** role. One
set of credentials can reach either API or both, so the card shows a dot for each: **Test** tries a
cheap read against both, fills in the ones that answered, and passes as long as one did. Build the
report as **Amazon — Business purchases**. Turn on **attach invoice PDFs** and each run also puts the
invoice (or credit memo) PDFs on the report — at most 25 new ones a run, since Amazon builds each PDF
on request at about one a minute; one already fetched is kept and not asked for again. An agent can
fetch a single one by number with the `amazon_invoice_pdf` lookup. See Amazon's
[Amazon Business API documentation](https://developer-docs.amazon.com/amazon-business/docs).

**Taking payments with Stripe** — the **Stripe** card reads your Stripe account: the balance,
balance transactions with fees and net, charges, payments (PaymentIntents), payouts, refunds,
disputes, customers, subscriptions with each one's monthly recurring revenue, and invoices. Like the
Amazon card it is a data card for reports, dashboards and agent lookups, never a source of work, and
it is read-only by construction: it only sends GET requests, so nothing on it can refund, pay out or
cancel. To connect it, open the Stripe Dashboard → Developers → API keys → **Create restricted key**,
give it Read on Balance, Balance transaction sources, Charges, Refunds, Customers, Disputes,
PaymentIntents, Payouts, Invoices and Subscriptions and None on everything else, then paste the key
(`rk_live_…` or `rk_test_…`) onto the card, where it is kept write-only. A full secret key (`sk_`)
works too, but it can move money; the restricted one is the one to give. **Test** reads the balance
and says whether the key is live or test. Amounts come back in money rather than cents — a
zero-decimal currency such as JPY stays as it is — lists are read a page at a time within the window
you ask for, and a rate-limited call waits and retries. See Stripe's
[restricted keys documentation](https://docs.stripe.com/keys#create-restricted-api-secret-key).

**Markets** — Yahoo Finance, CoinGecko, Alchemy, ECB reference rates, SEC EDGAR filings, and a
strategy screen that filters another card's rows. With a key: **Twelve Data** (quotes and computed
indicators across stocks, FX and crypto), **Alpha Vantage** (slow limits, no card, no expiry),
**Finnhub** (quotes plus company news, earnings dates and insider transactions), **Polygon.io**
(bars and full-market snapshots), **Tiingo** (properly adjusted end-of-day history), **Financial
Modeling Prep** (fundamentals and ratios rather than prices) and **Alpaca** (a broker's own feed —
read only; this card has no order executor at all). **FRED** needs no key or account whatsoever and
is the one a fresh install can use immediately.

Which to pick is a question of what you are watching, not of which is best: Finnhub if you follow
companies, Tiingo or Polygon if you follow prices, FMP if you follow balance sheets, FRED if you
follow the economy.

**The web** — search it or read one page of it, each a single REST call with a key. **Exa** and
**Tavily** read the web for an agent (Tavily can hand back a written answer with its sources beside
it); **Brave Search** answers from its own index; **SerpApi** and **Serper** give back a search
engine's page as it was ranked, which matters when the ORDER is the finding. To read one page:
**Jina Reader** (no account at all), **Firecrawl** (clean markdown), **ScrapingBee** (for a page
that fights back) and **Apify** (when the crawl is one somebody already wrote). They overlap on
purpose — the bill and the terms differ far more than the results do.

What is deliberately NOT here is anything that DRIVES a browser — logging in, clicking, filling a
form. That runs over CDP through a real browser session and cannot be reached from an API, so a
card promising it would be a card that never works. Driving a browser is the optional
`agent-browser` tool's job instead: signing in, authenticator codes and the browser acts that wait
for your press are described under
[When the agent opens a browser](tasks-and-agents#when-the-agent-opens-a-browser).

**Social** — **LinkedIn**, **Bluesky** and **Mastodon**. Nothing from these reaches the rail as
work: a public timeline is not an inbox, so they are report sources and tools rather than triggers.
Like every connection they start at full authority, so an agent can post. A public post cannot be
recalled: set the card to `read` and a post an agent drafts becomes a proposal you approve on the task.

**Agent tools** — **treg** puts thousands of endpoints across many providers behind one key, billed
per call. Searching its catalogue is free and commits nothing, so an agent may do it unattended;
calling an endpoint spends real money and can reach services that publish or order. The card starts
at full authority like every connection; set it to `read` and every call becomes a proposal.

**Reason Network** — your teammates' coding agents and yours, messaging each other peer to peer
([Reason Network](https://github.com/reason-machines/reason-network)). It is a program you install and
keep up to date yourself; Taskuary never ships or installs it, it finds it on this computer and speaks
to its command line. The card shows who is on the network and what each of their sessions is doing,
and holds the people you trust — a whole person, or one of their sessions.

- **Only people you trust reach your agents.** With the switch on, Reason Network's own setting holds
  every message from anyone else; it reaches no agent on this computer, Taskuary's or your own, until
  you deliver it. Each one becomes an item on your rail, and the card lists it with Deliver and Drop.
  A person trusted for one session only is held too, and Taskuary lets that session's messages through
  while it runs.
- **On the task.** A message one of your agents is shown goes on its task as a note, its words
  fenced and any credential taken out. An agent's own message to a teammate is noted there too, and
  one to someone you have not trusted is stopped.
- **Your OK, in Taskuary.** When a teammate's agent asks for something only you can approve, the
  request is an approval on the task instead of Reason Network's pop-up.
- **Ask from the Assistant.** "Ask Erin's agent whether the token format changed" sends the question
  to Erin's live session; the reply lands on the task.
- **Off the network.** Each repository's checkout has a switch that keeps its sessions off the
  network (`reason-network folder <path> off`). The Assistant's own folder goes off when you turn on
  the trust switch.

What Taskuary cannot stop: a session it does not run, an agent typing `reason-network send` in its
shell, or anything while Taskuary is closed — there, Reason Network's own held-message setting is the
guard, and it holds whatever is not trusted until you are back.

**Agent Desktop** — your agents read and operate the desktop apps on this computer through each app's
accessibility tree: the list of buttons, boxes and menus the app keeps for screen readers, not
screenshots. It runs on [agent-desktop](https://github.com/vercel-labs/agent-desktop), Vercel's sibling
of the `agent-browser` tool, on Windows, macOS and Linux. You install it yourself
(`npm install -g agent-desktop`); Taskuary finds it and never installs or updates it. Use it for a
desktop app with no connection and no web page. A connection comes first, then the browser.

- **Off until you turn it on.** With the card off, no agent is told about it, and any agent-desktop
  command from one of Taskuary's sessions is refused. On macOS the program asks for Accessibility
  permission the first time; the card's **Test** says whether it has it.
- **Only on a task marked "needs desktop".** Turning the card on is not enough: mark the task too.
  With the card on, the New sheet's **Needs desktop** box marks a new task. Triage marks one whose work
  it reads as done in a desktop app. On a task without the mark, the agent is not told about it and
  every agent-desktop command is refused. An agent cannot mark its own task.
- **Your own tasks only.** A task with a message from someone you have not vouched for never drives
  your desktop. The task does not get it, as it does not get the browser.
- **What can't be undone waits for you.** A command that only looks (a snapshot, a list of apps or
  windows) runs. Any other command goes to your AI with the control it names. A command that would
  send, pay, delete, submit or close unsaved work is refused to the agent and put on the task for your
  **Approve**. Approving runs that exact command. If the control has gone since, agent-desktop refuses
  it and nothing is done. With no AI connected, typing into a box passes and everything else waits.
- **Beside you, not instead of you.** It acts through the apps' own controls without moving your
  mouse or taking your keyboard, so you can keep working. Agents are told never to take the foreground,
  and never to type a password or code into an app. A sign-in is yours.

**Your own documents** — the **Knowledge base** card indexes SharePoint library folders and
folders on this machine (docx, pptx, xlsx, html, text, and pdf with `pypdf`) into Taskuary's own
SQLite. Once anything is indexed, a `kb_search` report answers questions from it on a schedule,
agents call the same search as a tool, and the reply drafter, the assistant and coding sessions
are handed the passages that bear on a thread. Passages are treated as facts to cite, never as
instructions.

Search matches words by default, so "time off" misses a policy titled "Leave of absence". Switch on
**Semantic search** (Settings → Assistant) and each passage is also embedded by a small model
when it is indexed; a search then merges the passages nearest in meaning with the keyword hits, and
every caller gets results in the same shape. It is off by default, and off changes nothing. The
embedder is any server that answers `/v1/embeddings`; the default is Ollama on this machine
(`ollama pull nomic-embed-text`), so no document leaves it. Pointing the address at a remote server
sends your documents' text there. Passages indexed before you switched it on are embedded by the next
Reindex, a changed model re-embeds them the same way, and if the model is unreachable search simply
uses keywords. `pip install taskuary[semantic]` adds numpy for a faster scan on a large library.

:::warn Planned is not available
The Connections page lists cards that are on the roadmap as well as ones that work — NetSuite,
SAP, Workday, ADP, Epic, Cerner, PointClickCare among them. A planned card tells you so on its
face. If the assistant suggests connecting one, saying yes is a vote for building it, not a
connection.

(This callout used to name "a long tail of market-data providers" here. Eight of them were built
and the sentence was not updated, so the docs called working cards planned — the market cards
above all work.)
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

Every CLI card has a **light model** as well as a main one. Naming the same CLI as the brain your coding
agent runs on and as your triage brain is normal and cheap, and it is the light gear that keeps it cheap.

## Voice notes and dictation

A card under **AI · voice** turns speech into text: a voice note that arrives (a WhatsApp voice
message) and the microphone beside each box. Groq (Whisper), OpenAI transcription, Google Gemini
transcription, Deepgram and ElevenLabs Scribe take a key; **Any Whisper server** points at one you
run; **Local Whisper** runs on this computer with no key, and the audio never leaves it
(`pip install taskuary[voice]`). With no voice card a voice note still lands, filed with a line
saying it was not transcribed and why, its audio attached so one click transcribes it later.

With no voice card the microphone still works, using the computer's own voice typing. In a
browser tab that is the browser's recogniser. In the Windows app it is **Windows voice typing**
(the one behind Win+H), which needs **Online speech recognition** on under Settings > Privacy &
security > Speech; with that off, the mic falls back to Windows' older offline recogniser, which is far
less accurate, and its hover says how to turn the better one on. On a Mac, the app window cannot
call Apple's recogniser: click in the box and press the Dictation key (or Fn twice). A voice card
is still more accurate, and it is what transcribes voice notes.

## A system with no card

Search the catalogue first. When nothing matches, **Request** under the empty grid drafts a feature
request for that card, and the Assistant offers the same when you ask it to connect something the
catalogue lacks. You read the draft and submit it on GitHub yourself; nothing is filed for you.

## Adding another of the same kind

**Add another** on any card creates a second connection of that type with its own name,
credentials, roles and schedule. Use it for:

- a second mailbox, where one is yours and one is a shared team address;
- production and staging databases, so a report says which it read;
- two GitHub organisations, so repository discovery does not mix them.

Every prompt, report source and agent tool names the connection it used, so two cards of the same
type never become ambiguous downstream.

## Pushing something in yourself

Anything that can make an HTTP request can put an item on the rail:

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

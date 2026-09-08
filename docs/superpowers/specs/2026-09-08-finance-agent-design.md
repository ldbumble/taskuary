# The finance agent: market data, card spend, and a trade you approve

*A design note, 2026-09-08. The fourth instance of `docs/beyond-code.md`, and the one that needed
the least new machinery — which is the point of that note. The question that prompted it: "an agent
that monitors stocks you want to trade, or your portfolio for changes, showing up as a report — and
if you actually want to trade on it, an agent action with a playbook." Then, in the same breath:
"how much did I spend today across my credit cards, and the assistant promotes anything weird."*

**Owner constraint (2026-09-08): no code changes besides new connectors, and a playbook or two as
testing.** That constraint shaped this document more than anything else in it. Two things this
design wants are named in *Known holes* and deliberately not built.

## Why this fits without a new engine

`docs/beyond-code.md` argued that a task is "text plus context, handed to an agent standing in a
folder with tools", and that a new *kind* of job needs three things: a connection, a playbook, and a
receipt. Finance monitoring needs a fourth of nothing. The machinery below already exists and is
used unchanged:

| What the feature needs | What already does it |
|---|---|
| Poll something on a schedule | a report source: `ConfigJson {"type", "title", "every_minutes"}` (`reports.py:1044`) |
| Rows, capped honestly, with a spreadsheet and a chart | `rows_out` + `attach_report_output` (`reports.py:35`) |
| Show up on the Timeline, never as a task | `Status: 'feed'` + `add_route(..., 'feed', ...)` |
| Show up in Work when it needs doing | `cfg['triage']` + `watch_for` → `ingest_message` (`reports.py:1130`) |
| Ping the phone only when something trips | `alert_fires` + `send_alert` (`reports.py:1202`) |
| Notice the odd one and put it in front of the owner | `type: 'assistant'` with `watch_source_ids` (`reports.py:1113`) |
| An agent that reads several feeds and writes commentary | `type: 'agent'` + `sources: [...]` (`reports.py:234`, `reports.py:809`) |
| An agent that may not act, only ask | `scopes.py` ceiling + `proposals.py` `run_tool` (`proposals.py:206`) |
| How this company does this kind of job | `playbooks.py` |

So the whole build is **new connector modules plus additive registry entries**. Nothing in the
shared path is edited.

## Part 1 — `taskuary/markets.py`

One module, not one per provider, following `research.py`: every executor here is plain REST with a
key on a card, no SDK, nothing new frozen into the single-exe build. `research.py` holds four
providers in 113 lines for exactly this reason, and market data has the same shape.

Each executor returns `(headline, body)` through `rows_out`, so a market source drops into a report
pipeline beside a SQL query and feeds the same prompt.

### Free, no key at all

The cards that work before you sign up for anything. `run_reader` is the precedent — it is in
`research.py` specifically because "a research pipeline should not need a paid account to read one
public page."

| Card | Executor types | Endpoint | Notes |
|---|---|---|---|
| `stooq` | `stooq_history` | `stooq.com/q/d/l/?s=<sym>.us&i=d` (CSV) | Officially free, no signup, no key. EOD and some intraday. The honest free-no-key card. |
| `sec_edgar` | `edgar_filings`, `edgar_facts` | `data.sec.gov/submissions/CIK<10>.json`, `data.sec.gov/api/xbrl/companyfacts/CIK<10>.json` | Official and free; requires a `User-Agent` naming a contact, and honours a fair-access rate. The only source here that hands back the actual 8-K. |
| `coingecko` | `coingecko_prices` | `api.coingecko.com/api/v3/simple/price` | Free tier; a demo key raises the limit and rides as `x-cg-demo-api-key`. |
| `frankfurter` | `fx_rates` | `api.frankfurter.app/latest` | FX, no key. Roughly eight lines. |
| `yahoo` | `yahoo_quotes`, `yahoo_history` | `query1.finance.yahoo.com/v8/finance/chart/<sym>` | **Best-effort, and labelled so on the card.** See below. |

**On Yahoo.** Yahoo retired its official API in 2017 and never replaced it; what everyone uses are
undocumented internal endpoints that now generally want a cookie and a `crumb`, and whose JSON
shape changes without notice. The owner chose to include it anyway (2026-09-08) because it is the
most useful keyless quote source in practice. Two consequences the card copy must state plainly,
in the same voice the Robinhood note below uses:

- It is the only card in this module that is **not stateless** — a cookie/crumb handshake is session
  state, which is a different shape from every other executor here.
- It is the card most likely to break, and breaking is not a bug to be fixed under pressure. If it
  breaks, `stooq` covers the same free-no-key need officially.

Scope the implementation to the `v8/finance/chart` path, which has historically served keyless, with
the crumb handshake as a fallback rather than the primary road.

### Free tier with a key

All but one of these is a single `_apikey_card('<card>')` line in `CONNECTION_OF`
(`reports.py:753`) — a card whose whole configuration is one key, arriving as `api_key`.

**Alpaca is the exception, and it matters for the wiring:** it needs *two* credentials, a key id and
a secret, so `_apikey_card` does not fit it. It takes the `aws_connection` shape instead — `_card(store,
'alpaca', 'secret_key')`, with `key_id` and `env` as ordinary ConfigJson fields and only the secret
stored write-only (`reports.py:702`).

| Card | Executor types | Base | Auth | Why it is distinct |
|---|---|---|---|---|
| `alpaca` | `alpaca_quotes`, `alpaca_bars` | `data.alpaca.markets/v2` | `APCA-API-KEY-ID` / `APCA-API-SECRET-KEY` headers | Real-time IEX free; SIP is 15-minute-delayed without a subscription. **The same card becomes the broker in Part 4**, so one credential does double duty. |
| `finnhub` | `finnhub_quotes`, `finnhub_news`, `finnhub_earnings`, `finnhub_insiders` | `finnhub.io/api/v1` | `token` query param | The most generous free tier, and the widest single key: quotes, company news, earnings calendar and insider transactions from one card. |
| `alphavantage` | `av_quotes`, `av_indicator`, `av_news` | `www.alphavantage.co/query` | `apikey` query param | **Server-side technical indicators** — RSI, MACD, SMA/EMA, Bollinger — plus news sentiment. This is what makes strategy matching possible without us writing indicator math. Its free daily cap is small, hence the next row. |
| `twelvedata` | `td_quotes`, `td_indicator` | `api.twelvedata.com` | `apikey` query param | The same indicators at a per-minute rather than per-day limit. The working alternative when Alpha Vantage's daily cap bites. |
| `tiingo` | `tiingo_history`, `tiingo_news` | `api.tiingo.com` | `Authorization: Token <key>` | EOD plus a genuine news corpus, cheap. |
| `fmp` | `fmp_fundamentals`, `fmp_ratios`, `fmp_screener` | `financialmodelingprep.com` | `apikey` query param | Fundamentals, ratios and a screener — the "is this company any good" half nobody else here covers well. |
| `polygon` | `polygon_snapshot`, `polygon_bars` | `api.polygon.io` | `apiKey` query param | The serious paid road when free tiers stop being enough. Free tier is end-of-day and heavily rate-limited; it is here so outgrowing free does not mean rewriting. |
| `fred` | `fred_series` | `api.stlouisfed.org/fred` | `api_key` query param | Macro series — rates, CPI. The context for "why did everything move at once." |

**Rate limits are deliberately not tabulated here.** Every provider above has changed its free tier
at least once, and a number in a design doc is a number that goes stale and then misleads. Each
card's `howto` lines state the limit as found at build time, next to the link where it is
authoritative — the same way the Teller card states its enrolment tier.

### Named but not built

Into `reports.PLANNED`, which exists precisely so a misconfig is visible on the Timeline instead of
silently absent, and so an empty category does not answer "does this reach my provider" worse than a
list does:

`plaid`, `ibkr`, `schwab`, `tradier`, `robinhood`, `eodhd`, `marketstack`, `intrinio`, `benzinga`.

**On Robinhood.** It is in the planned list rather than the built one for a specific reason worth
writing down. Robinhood has no official equities API; their only public developer product is the
Crypto Trading API. Stocks and options run on undocumented private endpoints that community
libraries reverse-engineer. An unsupported, silently-changing dependency sitting between an LLM and
a brokerage account is not a tradeoff this design accepts. If Robinhood is built later, it is built
as the **crypto** card their API actually supports.

### Registry wiring

Purely additive, no shared logic touched:

- `reports.REGISTRY` — one `_lazy('markets', 'run_<type>')` entry per executor type.
- `reports.CARD_OF` — every executor type mapped to its card (`'finnhub_news': 'finnhub'`, …).
- `reports.CONNECTION_OF` — `_apikey_card('<card>')` per keyed card, `_card(store, 'alpaca',
  'secret_key')` for Alpaca. `stooq`, `sec_edgar`, `frankfurter` and `yahoo` need no entry at all.
  `coingecko` takes one anyway: it works with no key and a key raises the limit, which is exactly
  `run_reader`'s precedent — "a key raises the rate limit; without one it still works, which is the
  point" (`research.py`).
- `scopes.ACTIONS` — every type above is `'read'`. Nothing upstream moves.
- `scopes.DEFAULT_SCOPE` — every card `'read'`.
- `website/src/ConnectorsView.jsx` — a new **"Markets & finance"** group, plus `plannedCards` for the
  list above. `website/src/logos.jsx` — one tile each.
- `docs/integrations.md`, `tests/test_markets.py`.

## Part 2 — Card spend: `teller_spend`

Teller is already the credit-card and bank feed, built 2026-09-01, chosen over Plaid because this is
a local install and the owner does their own enrolment (`taskuary/teller.py`). Its rows already carry
`direction: spend | inflow` so the bank's sign convention is decoded once, in code
(`teller.py:103`). What is missing is the aggregate: `teller_transactions` hands back rows, and
"how much did I spend today across my cards" answered by an LLM adding up a table is arithmetic done
by the wrong tool.

`teller_spend` is a new **type** on the existing Teller **card** — the pattern `quickbooks_accounts`
and `intacct_fields` already use. It lives in the new module so `teller.py` is not edited:

- `CARD_OF['teller_spend'] = 'teller'`
- `CONNECTION_OF['teller_spend'] = _teller_connection`
- `scopes.ACTIONS['teller_spend'] = 'read'`

Config: `{"days": 1, "account": "" , "group": "account"}`. Output: one row per card — account, last
four, transaction count, spend total, largest single charge — plus a `TOTAL` row. The sum happens in
Python.

### The headline carries the number

`alert_fires` has no field comparison; `more_than` compares a **row count**, taken from the leading
number of the headline (`result_count`, `reports.py:1193`). Under the connectors-only constraint,
that is not something to go and change. It is, however, something to *use*: `_LEADING_COUNT` parses a
leading number and strips commas, so a headline of

```
1,240.55 spent today across 3 cards
```

makes `alert: {"when": "more_than", "count": 500}` compare **dollars**. Cents are ignored and the
number must lead. This is the intended idiom for every numeric executor in this module, not a trick —
document it in the card's `howto` so the next person setting a threshold knows why the headline reads
the way it does.

### Promoting the weird one

This needs no new code. A report of `type: 'assistant'` runs `assistant.run(..., watch_source_ids=[…],
systems_only=True)` on its own schedule with its own instruction, and posts idea rows with buttons
and state rather than a report row (`reports.py:1113`). Point one at the Teller sources with an
instruction about what "weird" means for this owner's spending, and that is the feature. Its
`watch_for` sentence is the only thing it gets to say about its own verdict, so it is worth writing
carefully.

## Part 3 — The strategy monitor: three layers, cheapest first

**Layer 1 — `markets_screen`, deterministic.** Symbols plus conditions (`pct_change <= -5`,
`rsi < 30`, `price < sma200`), returning **only the matches**. Quiet when nothing matches, which is
what makes `alert: {"when": "something_came_back"}` the correct rule rather than a rule that fires
every run and stops being read.

The threshold belongs here, in config, and not in a playbook. A playbook is prose flattened onto the
command line (`playbooks.py:137`); a number living in prose is a number re-judged by a model on every
run, and it will drift. `docs/beyond-code.md` already draws this line: the `alone:` line of a
playbook *is* a routing policy, the deterministic gate the AI cannot override.

**Where the screen gets its credentials.** `markets_screen` reads through whichever provider supplies
the indicator, but `CONNECTION_OF` is keyed by executor type, so it cannot reach another card's
credentials on its own. It uses the **borrow** pattern already in the codebase — `azure_connection`
borrows the Outlook app, SharePoint borrows the Outlook tenant, Sheets borrows the Gmail client
(`reports.py:706`). So: a `screen` card whose config names `provider` and `connector_id`, and whose
connection function resolves that provider's card. No fourth mechanism is invented for this.

**Layer 2 — the agent that reads it. Already built.** `type: 'agent'` runs a saved skill or prompt on
the schedule through a CLI agent, and `sources: [...]` feeds several sources into one report, stacked
under labelled headers, with one source failing reported in place rather than taking the report down.
It even carries the previous run's *shape* forward so runs stay comparable — a real problem someone
already hit ("two runs twenty minutes apart came back as two different documents"). Point it at
quotes plus news plus indicators and it writes the strategy commentary. This is configuration, not
code.

**Layer 3 — when a match needs doing.** `triage: true` plus a `watch_for` sentence sends the row
through `ingest_message`, and triage decides whether it is work. That is the Timeline-row → Work-tab
promotion, and it is the same road a bank transaction takes.

## Part 4 — Trading: propose only

Broker: **Alpaca**, chosen for three reasons. It is an official keyed REST API, unlike Robinhood's
equities endpoints. Its paper endpoint is the *identical code path* — `paper-api.alpaca.markets`
against `api.alpaca.markets` — so the whole propose → approve → receipt loop is exercisable with fake
money before real keys exist. And its market-data card is already Part 1, so one credential serves
both.

New types on the `alpaca` card:

| Type | Scope | What it does |
|---|---|---|
| `alpaca_positions` | `read` | Holdings, cost basis, unrealised P/L |
| `alpaca_orders` | `read` | Open and recent orders |
| `alpaca_order` | `write` | Place one order |
| `alpaca_cancel` | `write` | Cancel one order |

The card ships at `DEFAULT_SCOPE['alpaca'] = 'read'`. That single line is the whole gate: below
`write`, an agent cannot place an order, it can only

```
TASKUARY-PROPOSE {"action": "run_tool", "type": "alpaca_order", "symbol": "…", "side": "…", "qty": …, "limit": …}
```

which lands in Review with the symbol, side, quantity and limit, and the owner's click places it.
This needs **no core change**, because `proposals.execute`'s `run_tool` branch already executes any
`REGISTRY` type generically and re-validates on approval (`proposals.py:206`). Raising the card to
`write` is the owner's decision, taken later, deliberately — exactly how QuickBooks' bill and expense
writes shipped.

The environment (`paper` / `live`) is a card field, and it ships `paper`.

## Known holes

Two things this design wants and does not build, both because they are edits to shared logic rather
than new connectors. They are recorded here so neither gets discovered later as a surprise.

**1. Numeric alert conditions.** `alert_fires` has no `above` / `below` on a named row field. The
headline-carries-the-number idiom in Part 2 covers the common case at the cost of ignoring cents and
constraining every numeric headline's word order. The proper fix is roughly ten lines in
`alert_fires` plus a condition name, and every future numeric report will want it.

**2. Re-quote at approval — the one with a real edge.** A bill does not move while it waits in
Review. A limit order approved forty minutes after an agent proposed it is a different trade.
`proposals.execute` already re-validates on approval, and `verdicts.py:135` already marks a pinned
reply draft stale when the thread moved underneath it — so the pattern exists and the hook is in the
right place. Teaching it to re-price and refuse when the market has moved past a band the proposal
declared is a small change in a shared file, which puts it outside this scope.

Until it exists, the mitigations are honest but weaker than a gate: the playbook's `ask first:` line,
and keeping the Alpaca card on the paper endpoint. **Do not raise the Alpaca card to `write` scope
while this hole is open.**

## The playbooks — two, and deliberately two shapes

A playbook is not the strategy. It is what tells a non-code task that it *is* a non-code task, and
that turns out to be mechanical rather than philosophical: `terminal.py:1074` appends
`CODING RULES (CODER.md)` to every worker seed unconditionally, and the counterweight —
*"THIS IS NOT A CODE CHANGE: the systems named in USES are the ground … do not go looking for a
codebase to edit"* — lives inside `seed_block`, which only fires when triage has tagged the task
`playbook:<slug>` (`playbooks.py:146`). A playbook-less "NVDA is 8% below your cost basis, decide"
task hands an agent CODER.md's "work only in the repository the task names", and it will go hunting
for a repo. The playbook is also where `alone:`, `ask first:` and `done when:` live, and `done when:`
is what a receipt gets checked against.

**`watch-card-spend.md`** — a judgment job with no writes.
`uses:` teller (read) · `done when:` the odd charge is named on the task with its merchant, card and
amount. Tests that a non-code task gets worked without an agent going repo-hunting.

**`propose-a-trade.md`** — hand-written, and the "hand-written" is the design decision.
`uses:` alpaca (read, propose: orders) · `alone:` nothing · `ask first:` every order ·
`done when:` the Alpaca order id is on the task and the filled quantity matches the proposal. Tests
the propose → approve → receipt road end to end on the paper endpoint.

**Why hand-written and not accreted.** `playbooks.draft` asks the closing transcript *"did this
session do a kind of job that will recur, done well enough to write down?"* (`playbooks.py:180`).
That question works for an AP bill because a bill has a verifiable right answer — the merchant
matched a vendor, the amount matched the transaction. A trade does not; you cannot know for months,
and `proof.py` can verify that a fill happened but never that the trade was right. Letting `draft`
file a trading playbook means one trade that happened to work becomes company policy — survivorship
bias with a slug. So trading playbooks are written by the owner, and `draft` should decline when the
playbook would be about a broker. *(That decline is itself a change to `playbooks.py` and therefore
out of this scope; until it exists, the mitigation is that `playbooks_enabled` drafts land as
proposals and nothing is ever filed without a click.)*

## Build order

Sequenced smallest-certain-value first, per the owner (2026-09-08):

1. **`teller_spend`** plus the assistant pointed at it. Smallest change, on a connector that is
   already live, and it answers a question the owner asked directly.
2. **`markets.py` breadth** — the keyless cards first (they are testable with no signup, which makes
   them the ones CI can actually exercise), then the keyed ones.
3. **`markets_screen`** and the `type: 'agent'` strategy report — the latter being configuration.
4. **The Alpaca card**, reads first, then the two proposal-gated writes, on paper.

## What this is not

- **Not a trading engine.** Reports are scheduled in minutes (`every_minutes`); Taskuary is a
  minutes-scale poller, not a streaming system. Any strategy needing sub-minute reaction does not fit
  here and this design should not pretend otherwise.
- **Not advice.** Every number on the Timeline is a number a provider returned, with the provider and
  the run time on the row. The agent's commentary is commentary.
- **Not a workflow builder.** A playbook is a page of prose an agent reads, as `docs/beyond-code.md`
  says. No boxes, no arrows.
- **Not automatic.** Nothing here can place an order. The card ships at `read`, and while the
  re-quote hole above is open, it stays there.

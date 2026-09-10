# The SimpleFIN card: a bank feed anyone can turn on

**Built 2026-09-10** (`taskuary/simplefin.py`). Supersedes the Teller card as the bank/card feed to
reach for; `taskuary/teller.py` stays for owners who already hold Teller credentials.

## Why

Teller stopped being obtainable. Checked 2026-09-10: `teller.io/settings/application` still serves a
login form, the marketing site still advertises "free for independent developers… 100 live
connections", but `teller.io/signup` is a 404, there is no signup link anywhere on the site, and
`dashboard.teller.io` no longer resolves in DNS. Owners report a shutdown email. Whatever the
company's status, **a card nobody new can connect is not a card**, and the finance agent spec
(`2026-09-08-finance-agent-design.md`) rests on this feed.

The replacement had to pass the test the whole beyond-code page is written against: *anyone must be
able to turn it on themselves.* That rules out more than it sounds like:

| option | why not |
|---|---|
| Plaid | production pricing is a sales conversation; an owner was quoted $1,000/month for a hobby app |
| Stripe Financial Connections | needs a Stripe **business** account and is shaped around ACH/underwriting |
| MX / Finicity / Akoya direct | enterprise contracts, no self-serve |
| BAI2 / EDI bank files | set up per company by the bank's treasury desk and priced for that. The corporate banks already send them (MFA's FanApp consumes them), but nobody else can get one |
| an open-source aggregator | does not exist and cannot: the data comes from bank agreements, not code. What is open source is the client side — SimpleFIN is an open protocol, Actual Budget and Firefly III are open clients |

**SimpleFIN Bridge** is the one that passes: $1.50/month or $15/year **billed to the owner**,
self-serve, no application to register, and read-only by protocol rather than by our promise.

## The shape

- **The Secret is an access URL** — `https://user:pass@bridge.simplefin.org/simplefin` — credentials
  inside the string. `_split` takes them out before any request, so they ride as basic auth and
  never as part of a URL that could be logged.
- **Connecting is one field.** The owner links banks at their own bridge account, presses "Get a
  setup token", pastes it. `POST /api/connectors/{cid}/simplefin/claim` base64-decodes it, POSTs the
  claim URL, keeps the access URL. No `connect.js`, no application id, no mTLS certificate pair.
- **The claim is one-shot.** A second claim answers `Forbidden (was it already claimed?)`, so the
  endpoint validates the token's *shape* before spending it (a typo must not throw a token away)
  and reports "already claimed" in those words rather than as a network fault.
- **One fetch, four tools.** `GET /accounts` returns every account with its balance *and* its
  transactions, so `accounts` / `transactions` / `balances` / `spend` share one cached response.

## The two limits, and what they cost

1. **~daily refresh** (MX upstream). `simplefin_spend` with `days: 0` therefore means "as of the last
   sync", not intraday — so balances carry an `as_of` date and pending transactions are counted
   rather than hidden, because on a daily feed the alternative is a rollup that ignores this morning.
2. **24 reads a day**, and the bridge disables a token that keeps overrunning. `CACHE_TTL` (15 min)
   collapses the four tools onto one call and `DAY_BUDGET` (20 of the 24) refuses locally, with a
   sentence saying why, rather than letting the owner's token be switched off by someone else.

Also missing from the protocol, next to Teller's rows: no account **type**, no **last four**, no
per-transaction category or counterparty. So an account is picked by id or by a word of its name or
its bank, and `spend` reads the sign alone — positive is money *into* the account, so a card purchase
is negative and paying the card off is positive. The rollup keeps Teller's row shape (`charges`,
`spend`, `largest`, `inflow`, a `TOTAL` row, headline leading with the total so a `more_than` alert
compares dollars), which is what lets an owner move a report across without rebuilding its alert.

## Surface

`simplefin_accounts`, `simplefin_transactions`, `simplefin_balances`, `simplefin_spend` — all
`read` in `scopes.py`, and not merely by policy: there is no write verb in the protocol to expose.
`POST /api/connectors/*` is already on `guard.DENIED`, so an agent cannot claim a token.

Tests: `tests/test_simplefin.py` (26) and `website/test/simplefinCard.test.mjs` (3).

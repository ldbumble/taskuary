# Teller spend rollup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer "how much did I spend today across my cards" as a report — a `teller_spend` type on the existing Teller card, per account and in total, with the arithmetic done in Python and a headline that lets a dollar threshold work.

**Architecture:** One new rollup function and one new executor in `taskuary/teller.py`, beside the three reads already there, plus additive registry lines (`REGISTRY`, `CARD_OF`, `CONNECTION_OF`, `scopes.ACTIONS`), the card's `types` array and its copy. No shared logic is edited: nothing in `alert_fires`, `proposals.py`, `terminal.py` or the seed changes. The threshold works because the executor's headline **leads with the total** and `reports.result_count` parses a leading number with commas stripped — so `alert {"when": "more_than", "count": 500}` compares dollars.

**Tech Stack:** Python 3.10, `requests` (already a dependency, mocked at the HTTP edge in tests), pytest with `unittest` style under `tests/`, React/JSX + vite for the card, loguru.

**Spec:** `docs/superpowers/specs/2026-09-08-finance-agent-design.md` — Part 2 ("Card spend: `teller_spend`") and *Known holes* item 1.

## Global Constraints

- **Connectors only.** New executor code plus additive registry entries. Do not edit `alert_fires`, `result_count`, `proposals.py`, `terminal.py`, `playbooks.py`, or the seed. If a task appears to need one of those, stop and report rather than editing.
- **Deviation from the spec, already decided:** the spec said the rollup would live in the new `markets.py` "so `teller.py` is not edited". It goes in `teller.py` instead, beside `run_teller_balances`. A bank rollup in a market-data module is the wrong home, and adding an executor to its own connector's module is exactly what connector code is. Amend the spec's Part 2 in Task 5.
- Dense fast.ai code style; no formatters. `teller.py` is LF — preserve it.
- Never write a backslash line-continuation or a Windows path through a heredoc; patch by line index when editing (`docs`-recorded hazard).
- Tests from the repo root: `python -m pytest <files> -q -p no:cacheprovider`. Never run a test file directly. "no tests ran" is a failure, not a pass.
- The packaged UI in `taskuary/web/assets/` is committed. A JSX change is not done until the bundle is rebuilt (Task 4).
- This checkout is shared with other agents, which share one git index. Build every commit **off-index**: `GIT_INDEX_FILE=$(mktemp -u) git read-tree HEAD` → `hash-object -w` → `update-index --cacheinfo` → `write-tree` → `commit-tree -p HEAD` → guarded `update-ref <ref> <new> <old>`. Never `git add` in this checkout.
- **After every off-index commit, repair the shared index.** With `GIT_INDEX_FILE` unset, run
  `git update-index --add -- <the files you committed>`. Without this the shared index stays blind to
  new files, `git status` reports them as staged deletions, and another agent running `git commit -am`
  commits their removal. Found live on 2026-09-08. Use `--add` on named paths only — never
  `git read-tree HEAD` against the real index, which would discard another agent's staged work.
- **Nothing is pushed.** The plan stops at a review gate. Before any later push, the whole suite runs from the repo root.
- Money words stay plain and unexcited (owner taste: colour identifies, copy does not shout). No emoji in card copy.

---

### Task 1: The rollup sums the spend, and the headline leads with the total

**Files:**
- Modify: `taskuary/teller.py` — add after `balances()` (ends line 128), before `probe()` (line 131)
- Modify: `taskuary/teller.py` — add `run_teller_spend` at the end of the file, after `run_teller_balances`
- Test: `tests/test_teller.py` (append a new class at the end)

**Interfaces:**
- Consumes: `teller.transactions(cfg, which, days, count) -> list` (existing, `teller.py:110`), whose rows carry `account`, `account_last_four`, `amount`, `date` and `direction` (`'spend' | 'inflow' | 'zero'`).
- Produces: `teller.spend(cfg, which: str = '', days: int = 0) -> list` — one dict per account plus a final `TOTAL` dict, each with keys `account`, `last_four`, `charges`, `spend`, `largest`, `inflow`. And `teller.run_teller_spend(cfg) -> (headline, body)` where `headline` begins with the total formatted `,.2f`. Task 2 wires both by name; Task 3 asserts the headline shape.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_teller.py`. It reuses `TheRows`' HTTP mock, so subclass it rather than restating the fixture:

```python
class TheSpendRollup(TheRows):
    """The one question the rows could not answer: how much, across which cards. Summed here,
    because a total added up by a language model is a total nobody can check."""

    def _spend(self, days=3):
        with mock.patch.object(teller, 'date') as d:
            d.today.return_value = __import__('datetime').date(2026, 9, 1)
            with mock.patch.object(teller.requests, 'get', side_effect=lambda url, **kw: self._get(url, **kw)):
                return teller.spend(self.cfg, '', days)

    def test_spend_is_per_account_biggest_first_with_a_total_and_inflow_kept_apart(self):
        rows = self._spend()
        self.assertEqual([r['account'] for r in rows], ['Operating', 'Platinum Card', 'TOTAL'])  # biggest spender first
        op, card, tot = rows
        self.assertEqual((op['charges'], op['spend'], op['largest']), (1, 1200.0, 1200.0))
        self.assertEqual((card['charges'], card['spend'], card['largest']), (1, 318.2, 318.2))
        self.assertEqual(card['inflow'], 500.0)              # the payment is not negative spend
        self.assertEqual((tot['charges'], tot['spend'], tot['largest'], tot['inflow']), (2, 1518.2, 1200.0, 500.0))

    def test_the_window_is_inclusive_and_the_old_row_is_out(self):
        self.assertEqual(self._spend(days=0)[-1]['spend'], 0.0)     # nothing posted on 2026-09-01 itself
        self.assertEqual(self._spend(days=3)[-1]['charges'], 2)     # 08-29 .. 09-01, and the 01-01 row cut

    def test_the_headline_leads_with_the_total_so_a_dollar_threshold_works(self):
        from taskuary.reports import alert_fires, result_count
        with mock.patch.object(teller, 'date') as d:
            d.today.return_value = __import__('datetime').date(2026, 9, 1)
            with mock.patch.object(teller.requests, 'get', side_effect=lambda url, **kw: self._get(url, **kw)):
                head, body = teller.run_teller_spend({**self.cfg, 'days': 3})
        self.assertTrue(head.startswith('1,518.20 spent '), head)
        self.assertEqual(result_count(head, body), 1518)            # dollars, not rows - commas stripped
        cfg = {'alert': {'when': 'more_than', 'count': 500, 'to': 'me@example.com'}}
        self.assertIn('more than the 500', alert_fires(cfg, head, body))
        self.assertEqual(alert_fires({'alert': {'when': 'more_than', 'count': 5000, 'to': 'me@example.com'}}, head, body), '')

    def test_every_account_row_is_json_on_its_own_line(self):
        with mock.patch.object(teller, 'date') as d:
            d.today.return_value = __import__('datetime').date(2026, 9, 1)
            with mock.patch.object(teller.requests, 'get', side_effect=lambda url, **kw: self._get(url, **kw)):
                _, body = teller.run_teller_spend({**self.cfg, 'days': 3})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual(rows[-1]['account'], 'TOTAL')
        self.assertEqual(len(rows), 3)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_teller.py::TheSpendRollup -q -p no:cacheprovider`
Expected: FAIL with `AttributeError: module 'taskuary.teller' has no attribute 'spend'`.

- [ ] **Step 3: Write the rollup**

Insert into `taskuary/teller.py` after `balances()` and before `probe()`:

```python
def _window(days: int) -> str:
    return 'today' if days <= 0 else 'since yesterday' if days == 1 else f'over the last {days + 1} days'


def spend(cfg, which: str = '', days: int = 0) -> list:
    """Per-account spend over the window, biggest spender first, and a TOTAL row.

    The window is INCLUSIVE and counted in days back from today, so days=0 is today alone - which
    is the question people actually ask. `transactions` cannot express that (it floors at one day),
    so the fetch is widened by a day and the rows are cut here.

    Inflow is carried beside spend and never subtracted from it: a card payment is not negative
    spending, and a rollup that nets them answers a question nobody asked.
    """
    days = max(0, int(days or 0))
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = [r for r in transactions(cfg, which, days=days or 1, count=500) if str(r.get('date') or '') >= since]
    seen = {}
    for r in rows:
        a = seen.setdefault(r.get('account') or '?', {'account': r.get('account') or '?', 'last_four': r.get('account_last_four'),
                                                      'charges': 0, 'spend': 0.0, 'largest': 0.0, 'inflow': 0.0})
        try: amt = abs(float(r.get('amount')))
        except (TypeError, ValueError): continue
        if r.get('direction') == 'spend': a['charges'], a['spend'], a['largest'] = a['charges'] + 1, a['spend'] + amt, max(a['largest'], amt)
        elif r.get('direction') == 'inflow': a['inflow'] += amt
    out = sorted(seen.values(), key=lambda a: -a['spend'])
    for a in out: a['spend'], a['largest'], a['inflow'] = round(a['spend'], 2), round(a['largest'], 2), round(a['inflow'], 2)
    return out + [{'account': 'TOTAL', 'last_four': None, 'charges': sum(a['charges'] for a in out),
                   'spend': round(sum(a['spend'] for a in out), 2), 'largest': max([a['largest'] for a in out] or [0.0]),
                   'inflow': round(sum(a['inflow'] for a in out), 2)}]
```

- [ ] **Step 4: Write the executor**

Append to `taskuary/teller.py`, after `run_teller_balances`:

```python
def run_teller_spend(cfg):
    """{"days": 0 (today) | 7, "account": "1234" | "Amex" (blank = every account)} - what you
    actually spent, per card and in total, with the largest single charge beside each.

    The headline LEADS WITH THE TOTAL deliberately: reports.result_count parses a leading number
    and strips its commas, so alert {"when": "more_than", "count": 500} on this report compares
    DOLLARS rather than row count - the only way to say "tell me if I spend over 500 today"
    without teaching alert_fires a new condition. Cents are ignored by that comparison.
    """
    from .reports import BODY_CHARS
    days = max(0, int(cfg.get('days') or 0))
    rows = spend(cfg, cfg.get('account') or '', days)
    n = len(rows) - 1
    head = f"{rows[-1]['spend']:,.2f} spent {_window(days)} across {n} account{'' if n == 1 else 's'}"
    return head, '\n'.join(json.dumps(r, default=str) for r in rows)[:BODY_CHARS]
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_teller.py -q -p no:cacheprovider`
Expected: PASS, all classes in the file, no failures.

- [ ] **Step 6: Commit (off-index, per the Global Constraints)**

```bash
export GIT_INDEX_FILE=$(mktemp -u /tmp/tqidx.XXXXXX); OLD=$(git rev-parse HEAD); git read-tree "$OLD"
for F in taskuary/teller.py tests/test_teller.py; do git update-index --add --cacheinfo 100644,"$(git hash-object -w $F)","$F"; done
TREE=$(git write-tree); NEW=$(git commit-tree "$TREE" -p "$OLD" -m "feat: teller_spend sums what left the cards, and its headline carries the number

The rows could say what posted; nothing could say how much. The sum happens in Python because a
total added up by a language model is a total nobody can check, and the headline leads with it so
result_count reads dollars - which is what makes alert more_than 500 mean five hundred dollars
without teaching alert_fires a new condition.

Inflow rides beside spend and is never netted against it: a card payment is not negative spending.")
git update-ref refs/heads/master "$NEW" "$OLD"; rm -f "$GIT_INDEX_FILE"; unset GIT_INDEX_FILE
```

---

### Task 2: Wire the type — registry, card, credentials, ladder

**Files:**
- Modify: `taskuary/reports.py:611` (`REGISTRY`), `taskuary/reports.py:654` (`CARD_OF`), `taskuary/reports.py:769` (`CONNECTION_OF`)
- Modify: `taskuary/scopes.py:44` (`ACTIONS`)
- Modify: `taskuary/docsync.py:69` (the type list an agent is shown)
- Test: `tests/test_teller.py` (append to `TheCard`)

**Interfaces:**
- Consumes: `teller.run_teller_spend` from Task 1.
- Produces: `'teller_spend'` resolvable through `reports.executor_for` and `reports.resolve_cfg`, needing scope `read` on the `teller` card. Task 3 runs it through `resolve_cfg`.

- [ ] **Step 1: Write the failing test**

Append these methods inside the existing `class TheCard` in `tests/test_teller.py`:

```python
    def test_spend_is_a_read_on_the_teller_card_and_resolves_its_token(self):
        from taskuary import reports
        s = MemoryStore(); _card(s)
        self.assertEqual(reports.card_of('teller_spend'), 'teller')
        self.assertEqual(scopes.needs('teller_spend'), 'read')       # a rollup of a feed still moves nothing
        self.assertTrue(scopes.allows(s.get_connector_by_type('teller'), 'teller_spend'))
        self.assertIs(reports.executor_for('teller_spend'), reports.REGISTRY['teller_spend'])
        cfg = reports.resolve_cfg(s, {'type': 'teller_spend', 'days': 0})
        self.assertEqual(cfg['access_token'], 'test_token_abc')      # the card's secret, not the report's
        self.assertEqual(cfg['days'], 0)

    def test_the_agent_type_list_names_spend(self):
        from taskuary import docsync
        self.assertIn('teller_spend', ''.join(docsync.SYSTEMS_HINT) if hasattr(docsync, 'SYSTEMS_HINT') else open('taskuary/docsync.py', encoding='utf-8').read())
```

> Note for the implementer: the second assertion reads the source because that list is built inside a function, not exported. If you find it is exported under a different name, assert against the export instead and drop the file read.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_teller.py::TheCard -q -p no:cacheprovider`
Expected: FAIL — `reports.card_of('teller_spend')` returns `'teller_spend'` (the `CARD_OF` fallback) rather than `'teller'`.

- [ ] **Step 3: Add the four registry lines**

`taskuary/reports.py:611` — extend the teller block in `REGISTRY`:

```python
            'teller_balances': _lazy('teller', 'run_teller_balances'),
            'teller_spend': _lazy('teller', 'run_teller_spend'),      # the rollup: how much, per card and in total
```

`taskuary/reports.py:654` — extend the `CARD_OF` line:

```python
           'teller_accounts': 'teller', 'teller_transactions': 'teller', 'teller_balances': 'teller', 'teller_spend': 'teller',
```

`taskuary/reports.py:769` — extend the `CONNECTION_OF` tuple:

```python
                 **{t: _teller_connection for t in ('teller_accounts', 'teller_transactions', 'teller_balances', 'teller_spend')},
```

`taskuary/scopes.py:44` — extend the teller line:

```python
    'teller_accounts': 'read', 'teller_transactions': 'read', 'teller_balances': 'read', 'teller_spend': 'read',    # a feed cannot move money
```

- [ ] **Step 4: Name it in the list an agent is shown**

`taskuary/docsync.py:69` — add `teller_spend` to the pipe-separated type string, after `teller_balances`:

```python
                     'intacct|intacct_fields|quickbooks|quickbooks_vendors|quickbooks_accounts|teller_accounts|teller_transactions|teller_balances|teller_spend", ...} — '
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_teller.py tests/test_agent_identity.py tests/test_playbooks.py -q -p no:cacheprovider`
Expected: PASS. Those last two are in the list because both already assert over Teller's types and will catch a typo in the tuple.

- [ ] **Step 6: Commit**

Same off-index recipe as Task 1 Step 6, with `taskuary/reports.py taskuary/scopes.py taskuary/docsync.py tests/test_teller.py` and the message:

```
feat: teller_spend is a read on the Teller card, and agents are told it exists

Four additive registry lines and one name in the type list an agent is shown - a rollup of a feed
still moves nothing upstream, so it sits at read like the three reads beside it.
```

---

### Task 3: A spend report runs end to end and its alert compares dollars

**Files:**
- Test: `tests/test_teller.py` (append a new class)

**Interfaces:**
- Consumes: `'teller_spend'` from Task 2; `reports.render_report`, `reports.alert_fires` (both existing, unmodified).
- Produces: nothing new. This task exists because Tasks 1 and 2 each pass while the *pipeline* is still broken — `render_report` applies `resolve_cfg`, the row cap and the AI switch, and none of that is covered above.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_teller.py`:

```python
class TheSpendReport(unittest.TestCase):
    """The pipeline, not the function: a saved report config, resolved credentials, and the alert
    rule the owner would actually write."""

    def setUp(self):
        self.s = MemoryStore(); _card(self.s)

    def _run(self, cfg):
        from taskuary import reports
        rows = TheRows(); rows.s = self.s; rows.cfg = teller.connection(self.s)
        with mock.patch.object(teller, 'date') as d:
            d.today.return_value = __import__('datetime').date(2026, 9, 1)
            with mock.patch.object(teller.requests, 'get', side_effect=lambda url, **kw: rows._get(url, **kw)):
                return reports.render_report(self.s, reports.resolve_cfg(self.s, cfg))

    def test_a_saved_report_needs_only_the_window_and_gets_the_token_from_the_card(self):
        head, body = self._run({'type': 'teller_spend', 'title': 'Card spend today', 'days': 3})
        self.assertTrue(head.startswith('1,518.20 spent '), head)
        self.assertIn('"account": "TOTAL"', body.replace("'", '"')) if '"account"' in body else self.assertIn('TOTAL', body)

    def test_the_owners_threshold_fires_on_dollars_and_stays_quiet_under_it(self):
        from taskuary.reports import alert_fires
        head, body = self._run({'type': 'teller_spend', 'days': 3})
        over = {'alert': {'when': 'more_than', 'count': 1000, 'to': '+15550000000', 'channel': 'whatsapp'}}
        under = {'alert': {'when': 'more_than', 'count': 2000, 'to': '+15550000000', 'channel': 'whatsapp'}}
        self.assertIn('more than the 1000', alert_fires(over, head, body))
        self.assertEqual(alert_fires(under, head, body), '')

    def test_a_failed_run_says_so_rather_than_reporting_zero_spend(self):
        from taskuary import reports
        s = MemoryStore()                      # no card connected: no token
        with self.assertRaisesRegex(teller.TellerError, 'Connect a bank'):
            reports.render_report(s, reports.resolve_cfg(s, {'type': 'teller_spend', 'days': 0}))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_teller.py::TheSpendReport -q -p no:cacheprovider`
Expected: FAIL. If it fails on `render_report`'s signature or an AI pass being attempted, read `reports.render_report` (`reports.py:860`) and pass what it needs — do **not** change `render_report`.

- [ ] **Step 3: Make it pass**

No production code should be needed. If a test fails for a real reason, fix the *test* to match the pipeline, or fix Task 1/2 code — never `reports.py`'s shared functions. The third test asserts the spec's rule that a failed run is not zero spend: `render_report` lets the executor raise and `_run_report_source` files it as FAILED, which is the behaviour we want and already have.

- [ ] **Step 4: Run the whole file**

Run: `python -m pytest tests/test_teller.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

Off-index recipe, `tests/test_teller.py`, message:

```
test: the spend report runs through the pipeline and its threshold is in dollars

Tasks 1 and 2 both pass while the pipeline is still broken - render_report is where resolve_cfg,
the row cap and the AI switch actually meet. Also pins the rule that a run which could not reach
the bank reports FAILED rather than zero spend.
```

---

### Task 4: The card says the type exists, and says why the headline reads oddly

**Files:**
- Modify: `website/src/ConnectorsView.jsx:537` (the `types` array), `:546-551` (`howto` and `agent` lines)
- Modify: `docs/integrations.md:60` (the Teller row)
- Rebuild: `taskuary/web/assets/` (committed bundle)

**Interfaces:**
- Consumes: the `'teller_spend'` type name from Task 2. No JS imports change.
- Produces: nothing other tasks consume.

- [ ] **Step 1: Add the type to the card**

`website/src/ConnectorsView.jsx:537`:

```jsx
  teller: { title: "Bank & card feed (Teller)", types: ["teller_accounts", "teller_transactions", "teller_balances", "teller_spend"],
```

- [ ] **Step 2: Add one `howto` line explaining the headline**

Append to the `howto` array on the teller card. This is the only place the dollar-threshold idiom is explained to a human, so it must be explicit rather than clever:

```jsx
      "Spend as a number, not a list: the 'teller_spend' report totals what left each card over a window (days 0 = today) and adds a TOTAL row. Its headline starts with the total on purpose — an alert of 'more than 500' on this report therefore compares DOLLARS, not the number of rows, which is how you get 'tell me if I spend over 500 today'. Cents are ignored by that comparison.",
```

- [ ] **Step 3: Add one `agent` line**

Append to the `agent` array on the teller card:

```jsx
      "Do not add up transactions yourself to answer 'how much did we spend' - run_tool with type teller_spend does it, per account and in total, and its numbers are the ones the owner's alerts are set against.",
```

- [ ] **Step 4: Amend the integrations table**

`docs/integrations.md:60` — extend the Teller row's description, before the closing ` |`:

```
 Spend is a report of its own (teller_spend): per-card and total over a window, with a headline that leads with the total so a 'more than' alert compares dollars
```

- [ ] **Step 5: Check the JSX compiles and has no undefined references**

pytest never loads JSX, so a syntax error here ships silently. Both commands run from `website/`:

Run: `npm run lint:undef`
Expected: no errors.

Run: `npm run build`
Expected: a successful vite build writing into the committed `taskuary/web/assets/`.

If Node is not on PATH at v22, use `npm exec` per the project's Node-22 gate rather than an older global Node.

- [ ] **Step 6: Commit the source and the rebuilt bundle together**

The bundle is committed, so a JSX change without its rebuild ships a UI that does not match the code. Off-index recipe, listing `website/src/ConnectorsView.jsx docs/integrations.md` **plus every file `git status --porcelain taskuary/web` reports**, message:

```
feat: the Teller card offers spend, and says why its headline starts with a number

The dollar-threshold idiom is invisible unless the card explains it: an owner setting "more than
500" on a rollup whose headline led with "3 rows" would have been setting a row count. The agent
line exists because the alternative - an agent adding up the transactions itself - produces a
number the owner's alerts are not set against.
```

---

### Task 5: Reconcile the spec with what was built

**Files:**
- Modify: `docs/superpowers/specs/2026-09-08-finance-agent-design.md` (Part 2)

- [ ] **Step 1: Correct the module claim**

Part 2 says the rollup "lives in the new module so `teller.py` is not edited". Replace that clause with what was actually decided and why:

> `teller_spend` is a new type on the existing Teller card — the pattern `quickbooks_accounts` and
> `intacct_fields` already use. It lives in `teller.py` beside the three reads: an earlier draft put
> it in `markets.py` to avoid editing `teller.py` at all, which put a bank rollup in a market-data
> module for no benefit. Adding an executor to its own connector's module *is* connector code.

- [ ] **Step 2: Mark Part 2 built**

Add to the Part 2 heading, matching how `docs/beyond-code.md` marks its own steps: `— *built 2026-09-08*`.

- [ ] **Step 3: Commit**

Off-index recipe, `docs/superpowers/specs/2026-09-08-finance-agent-design.md`, message:

```
docs: the spend rollup lives in teller.py, and Part 2 is built

The spec routed it through markets.py to avoid touching teller.py; that was caution serving
nothing, and it put a bank rollup in a market-data module.
```

- [ ] **Step 4: Run the whole suite from the repo root and stop**

Run: `python -m pytest -q -p no:cacheprovider`
Expected: PASS, and a non-zero number of tests collected. "no tests ran" is a failure.

Then **stop**. Report the suite result and wait — nothing is pushed by this plan.

---

## What follows this plan

Recorded so the remaining spec scope is not lost:

- **Plan 2 — `markets.py`:** the 5 keyless cards (`stooq`, `sec_edgar`, `coingecko`, `frankfurter`, `yahoo`) then the 8 keyed ones, plus `markets_screen` with the `azure_connection`-style credential borrow. Written after this plan lands, so each provider's endpoint and free-tier limit is verified at the time it is built rather than assumed now.
- **Plan 3 — the Alpaca card:** `alpaca_quotes` / `alpaca_bars` / `alpaca_positions` / `alpaca_orders` at `read`, then `alpaca_order` / `alpaca_cancel` at `write` with the card shipping at `read`, plus `propose-a-trade.md`. Blocked on Plan 2 landing the `alpaca` card's credentials (`_card(store, 'alpaca', 'secret_key')`, two credentials, not `_apikey_card`).
- **Not in any plan, by the owner's constraint:** numeric alert conditions in `alert_fires`, re-quote-at-approval in `proposals.execute`, `playbooks.draft` declining broker playbooks, and `if rules and repo_tag(t) != NO_REPO` in the seed. All four are edits to shared logic. The re-quote hole is the one with teeth: **do not raise the Alpaca card to `write` scope while it is open.**

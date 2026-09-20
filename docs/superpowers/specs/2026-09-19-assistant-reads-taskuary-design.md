# Taskuary is the Assistant's source, and every line says which query it came from

2026-09-19

## The problem

The Assistant report's instruction is the owner's to write, from the Reports tab. What the
instruction can reach is not. `assistant.inputs()` is nine hardcoded calls with hardcoded windows -
threads two days, arrivals two days, calendar two days, done seven, open work top twenty, already
said forty - and a model can only speak about what that function already put in front of it.
Rewriting the instruction to say "look at the past month" changes nothing: the month is not in the
payload. Three settings exist (`assistant_producers`, `assistant_followup_hours`,
`assistant_cold_days`), which is enough to turn a producer off and not enough to say what the
assistant reads.

The owner's words (2026-09-19), after asking what the assistant does now and finding the window was
two days: *"shouldn't we make the assistant configurable in the report which tables it should look
at, which data, how far back etc.. it should be a paradigm, so like reports is a source that you can
choose sql server, here assistant is the source it taskuary itself with queries pre built, and what
data gets pulled in is yours to update and change. default of course should be good and ready to
go."* And: *"assistant should show source for its input... you can show the sql in the source or more
like taskuary as a source with table names."*

Two things follow from that, and this design is both:

- **A report card that configures its reads.** A SQL Server report picks a connection and a query. An
  Assistant report should pick **Taskuary** and a set of pre-built queries, each with its own window
  and cap, priced so the owner can see what a wider window costs before saving it.
- **A post that names its evidence.** Every line should say which query produced it and link to the
  rows. The connect-ideas bug of the same day - "3 threads this month were about Interactive
  Brokers", which was three replies to one pull request titled *add Taskuary interactive demo* - was
  invisible for a day precisely because the row carried no way back to what it counted.

## The shape this takes

One structural change, and everything else hangs off it: **each context block becomes a
declaration**, and `inputs()` becomes a loop over the blocks a report chose.

```python
Block(id='gone_quiet', label='Work gone quiet', kind='query',
      tables=('task', 'comment', 'message', 'run'),
      sql=GONE_QUIET_SQL,                       # shown verbatim on the card
      window=('days', 3, 'Quiet days before a task has gone cold'),
      cap=20, default_on=True, proposes=True,
      render=lambda rows: ...)                  # rows -> the lines the model reads
```

`window` is `None` for a block that has none (`open work`, `already said`). `proposes=True` marks the
blocks that also post a row of their own with no model behind it.

### Two kinds of block, both labelled

Not every block is one SELECT, and printing SQL for the ones that are not would be a new lie in a
feature built to end one. `arrivals` rolls up in Python because it folds in each report's schedule
and each failure's cause - the logic that stopped the assistant calling 25 startup runs a scheduler
bug. `knowledge` is an FTS search with relevance. So a block declares which kind it is:

- **`query`** - one SELECT. The card shows the SQL verbatim, read-only.
- **`view`** - composed in code. The card names its tables and says so plainly ("composed in code -
  3 queries + a schedule lookup"), with the function named.

Either way the card answers "what does this read" with table names. New blocks default to `query`, so
the catalogue grows in the inspectable direction.

### The starting catalogue

Today's behaviour, block by block, so nothing moves on upgrade.

| Block | Kind | Reads | Default | Proposes |
|---|---|---|---|---|
| threads (what people said) | view | message, route, task | 2d | |
| arrivals | view | message, route, source | 2d | |
| calendar | query | message | 2d | |
| open work | query | task, run, review | top 20 | |
| gone quiet | query | task, comment, message, run | 3d | yes |
| waiting on (unanswered asks) | query | message, review | 24h | yes |
| promised (and not done) | query | message, review | 24h | yes |
| done this week | query | task, run | 7d | |
| already said | query | idea | 40 | |
| connectors mentioned | query | message, routing_fact, doc | 30d, floor 3 | yes |
| app health | query | source, report_run, connector | on | yes |
| knowledge | view | kb_fts | off | |
| system checks | view | source, connector | scoped | |
| my notes from last check | query | setting | on | |

`waiting on` and `promised` are one function (`followups`, which takes which of the two it wants), and
they stay two blocks because `assistant_producers` already lets the owner run one without the other.

`connectors mentioned` is the connect-ideas producer, and this is where it gains a window and a
floor the owner can turn. It stays **input and a guaranteed row**: its counts go to the model like
any other block, and it still posts its own row when a system clears the floor - a `COUNT(*)` that
has already proved something should not need a model's permission to be said.

### The three settings that already exist

`assistant_producers`, `assistant_followup_hours` and `assistant_cold_days` say today what a block
declaration will say tomorrow, and an owner who has tuned them must not lose that. They become the
**default a block resolves to when the report has not overridden it**: `gone quiet` reads its window
from `assistant_cold_days`, `waiting on` and `promised` from `assistant_followup_hours`, and a
producer absent from `assistant_producers` resolves `default_on: false`. The settings page keeps them
and their help text gains the sentence that says so. `assistant_max_lines` has nothing to do with
blocks and does not move.

The resolution order is one line and is worth stating flatly, because three places now hold a
number: **block declaration -> the global setting, where one exists -> the report's own override.**

## Where the configuration lives

The report row's `ConfigJson`, beside `watch_source_ids`. Only **overrides** are stored:

```json
{"type": "assistant", "blocks": {"threads": {"days": 7}, "knowledge": {"on": true}}}
```

Two consequences, both deliberate:

- A report with no `blocks` key behaves exactly as it does today. There is no migration.
- A block shipped later arrives `default_on: false`. Nobody's payload and nobody's bill changes
  because the catalogue grew.

## The card

A **"Reads Taskuary"** panel on the Assistant report, next to its schedule and instruction:

```
ASSISTANT · reads Taskuary

  ✓ threads            7d   12 rows   ~8.2k
  ✓ arrivals           2d   41 rows   ~3.1k
  ✓ open work          —    18 rows   ~0.9k
  ✓ gone quiet        14d    3 rows   ~0.2k
  ✓ connectors        30d  612 thr    ~0.1k
  ✗ knowledge          —    off
  ─────────────────────────────────────────
  ~12.5k tokens/run · ~$0.04 · 48 runs/day
```

Row counts come from an endpoint that runs each chosen block's `COUNT(*)` and never its bodies -
cheap enough to refresh as a knob moves. Token weight is measured on the block's **rendered text**,
not guessed from its row count, because a block's cost is its words. The money line appears only when
the chosen brain has a known price; otherwise the panel shows tokens and runs per day and stops
there, rather than inventing a number.

**Nothing is forbidden.** A hard ceiling that silently trims blocks would make the card say the
assistant read something it did not, which is the class of bug this design exists to end. The owner
sees the price and decides.

Expanding a row shows its tables and, for a `query` block, the SQL. The existing Preview
(`reports.run_assistant` -> `assistant.facts`) stays and renders exactly the blocks chosen, so the
card and the payload cannot drift.

## Every line says where it came from

```
— Marcus asked for the Q3 numbers Thursday and the thread went quiet;
  I would send before his Monday 1pm.
     why: his last word, no reply since
     from: threads (7d) → 2 messages

— 4 threads name Interactive Brokers and nothing here reads it.
     from: connectors mentioned (30d) → 4 threads
```

Attribution is **looked up, never asked for**:

- A candidate from a `proposes` block carries its own block id. No model is involved, so follow-ups,
  gone-quiet, health and connectors are attributed exactly.
- For the model's own `idea:*` lines, the contract already returns the message id the line is about.
  Each block records the message and task ids it contributed while inputs are assembled, giving a
  `mid -> block` index the source is read from.
- A model line with no mid carries **no** source line. It never guesses.

The source rides on the idea (`ActionJson.source`: block id, window, the row ids), so the post reads
correctly tomorrow the way `Brief` already snapshots `flight` and `stats`.

### The receipt replaces a hardcoded sentence

`_footer()` today writes a fixed sentence with hand-counted numbers ("3 thread(s) of what people
said, 41 sender/subject line(s) from the last two days..."), and `reviewed()` exists to count them.
Both are generated from the blocks that actually ran, with each block's window and row count. Posts
written before this carry the old `Brief.reviewed` shape, so the renderer tolerates both.

## Keeping it honest

- **Defaults are today.** A test asserts `inputs()` with no `blocks` config produces the same text as
  the current implementation. That is the whole migration story, and it is the test that must never
  be relaxed.
- **A block that cannot say what it reads cannot ship.** Every catalogue entry declares its tables
  and either SQL or a builder; every `query` block's SQL parses and runs against the fixture store.
- **Attribution.** A deterministic candidate carries its own block; a model line with a mid resolves
  to the block that supplied that mid; a model line without one carries no source.
- **The card cannot lie.** The Preview is generated from the same block list the panel shows, and one
  test renders both and compares the blocks named.

## Order of work

1. **The registry and the loop.** `assistant/blocks.py`: the `Block` declaration, the catalogue as
   today's fourteen, and `inputs()` rewritten as a loop. No config read yet, no UI. The
   defaults-are-today test lands here and gates everything after it. About two days.
2. **Configuration.** `blocks` in the report's `ConfigJson`, the resolver (declaration + overrides),
   the count/weight endpoint. Reachable by API, no card yet. About a day.
3. **The card.** The "Reads Taskuary" panel, the SQL and tables on expand, the running cost. About
   two days.
4. **Sources on the lines.** The `mid -> block` index, `ActionJson.source`, the per-line rendering
   and its click-through, the generated receipt. About two days.

Each lands on master on its own with its tests.

## What this deliberately leaves out

- **Your own SQL.** A free SELECT is a new egress surface - it can hand the model any column,
  including message bodies the prompt doors scrub today - and a schema change would break it
  silently. The catalogue is the boundary; a missing query is a card to add, not a box to type in.
- **LLM-written blocks.** A block described in words and compiled by a model can be wrong quietly,
  which is the failure mode this design is answering.
- **Per-block model routing.** One report, one brain, as now.
- **Sharing block sets between installs.** Not until there is a second install that wants one.

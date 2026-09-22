Reports are how Taskuary reads the systems you work in. The Assistant is a report with a different
job: instead of filing what it read, it decides whether any of it is worth your attention. They
share one builder, which is why they share one page here.

## A report is a pipeline

One report is one saved configuration on the **Reports** tab, built in four steps.

| Step | What it decides |
|---|---|
| **Pipeline** | The title, the sources it reads, and the one prompt that reads all of them |
| **Test & preview** | Test calls a single source; Preview runs the whole pipeline, AI pass included, filing nothing |
| **Schedule & save** | How often it runs, and whether each run goes through triage |
| Delivery and alerts | Optional, on the Pipeline step: send each run somewhere, or say nothing unless the result trips a rule |

Sources at the top, one prompt at the bottom. Every source runs on its own connection and query,
the results are stacked under labelled headers, and the prompt sees all of them at once. One
source failing is reported in place and never takes the whole report down.

:::rule Connections owns the credential, Reports owns the question
You do not configure a connection here. A source names the connector card its credentials live
on. That separation is why the same database can answer five different reports without five
copies of its password.
:::

## Sources

A source card carries a type, an optional label, whatever that type needs to run, and a row cap.
The type picker is grouped by where the data lives: this computer, files and sheets, databases,
AWS, Azure, Microsoft 365, monitoring, corporate systems, the AI itself, the web, and Taskuary's
own data.

Three things are worth knowing:

- **label** is how the prompt refers to that data. Two queries against the same database are two
  sources, and without labels the prompt cannot tell them apart.
- **max rows** is blank by default, and blank means 200 — a cap nobody chose. When a run is
  capped the headline says so, so the AI can never describe a truncated slice as complete.
- **Test — show me the data** returns the exact text a scheduled run would hand the prompt. Use
  it before assembling the rest of the pipeline.

Drag cards to reorder them; duplicate one to ask the same connection a second question.

## Letting the AI write the source cards

A source card asks you to know things first: which of thirty-odd types your data sits behind,
what that type's config keys are called, and the query language of whatever is on the other end.
Nobody remembers that a GL entry's amount is `AMOUNT` but a bill's is `TOTALENTERED`. So you can
describe what you want instead, in three places:

| Where | What it writes |
|---|---|
| **Describe the report you want**, top of the Reports tab | A whole report — type, query, prompt and schedule — dropped into the builder |
| **let AI fill this in**, on any source card | That one card, in the type it is already set to |
| **Describe what the Assistant should keep an eye on** | Every source the ask needs, plus the instruction to judge them by |

Four things keep this from being a wish machine:

1. **It may only choose a type whose connection actually exists.** The catalogue is built from
   this install's live connectors, so it cannot answer "connect to Salesforce" — only tell you
   that nothing here reaches Salesforce and what you would have to connect.
2. **The config keys come from the executors' own docstrings**, so a composed card cannot drift
   from the keys the code really reads.
3. **It reads the real schema before writing a query** — an object's field list, a table's
   columns, which `LOCATIONID` the site you named actually has. Up to three look-ups per ask,
   each a real call whose result goes back to the model.
4. **It is allowed to say it does not know.** Questions come back as questions, at most three,
   each answerable in a few words. A guessed `WHERE` clause on a finance report is silently wrong
   forever; a question costs five seconds.

Everything it writes is checked before you see it: a real type, a connected one, and the keys
that type needs to run at all. Nothing is saved — a composed card lands in the boxes you would
have filled in by hand, and **Preview** runs it for real so you look at actual rows before
anything is scheduled.

## The AI pass

The prompt at the bottom of the pipeline turns rows into prose. Leave it empty and the raw rows
file as they are.

- Write a concrete instruction — "Summarise spend by site; flag any vendor above 10k or new this
  month" — not "summarise the data".
- **Brain**: the triage brain writes it by default; any connector with a saved key can be picked
  per report. A saved pick that has lost its key stays visible and disabled rather than silently
  vanishing.
- With a prompt set but no AI connector active, the raw data files and the builder says so.
- When one column is a measure worth plotting, the model that just read every row says so and the
  run hands back a bar chart beside the text.

## Where a run goes

Every run lands on your Timeline. Two optional additions, both off by default:

- **Send it somewhere** — email, Teams, Telegram, WhatsApp, iMessage or Discord. It waits on
  the task for approval by default. "Send it without asking" is the one place in Taskuary where
  that gate can be switched off, and it is deliberate.
- **Tell me when it looks wrong** — silence is the normal outcome. An alert fires only when the
  result trips a rule: nothing came back, anything came back, fewer or more rows than N, the
  result mentions (or never mentions) something, or the report failed. Alerts send the moment the
  rule trips, with no Review step.

**Can become work** sends each run through triage like an inbound message, so `TRIAGE.md` decides
whether it becomes a task. Off by default — a report is informational. A failed run is never
triaged.

Under each report row, the last run shows what it read, what came out, and the error when it
failed.

## Schedules

Pick one: every N minutes, daily at `HH:MM`, a five-field cron, or on app startup. Everything
blank means once a day while the app is open, and a slot missed while the app was closed fires
once on reopen.

**Run due now** on the Reports tab runs everything owed; **Run now** on a row runs that one
report immediately.

:::note Once a day means once a day
A daily slot is a cap on the whole report, not on each way of triggering it. If the 08:00 slot
has already produced today's run, opening the app at 09:00 does not produce a second one.
:::

## The Assistant

The Assistant is a report of type `assistant`. It runs on its own schedule and when the app
opens, and it posts on the Timeline **only** when it finds something worth saying: an unanswered
reply, context for an upcoming meeting, a task gone quiet, a pattern across incoming work, or
something in the systems it watches that does not look right. Each suggestion names its evidence
and offers **Make it a task**, **Done**, **Snooze a day** and **Not this**.

Its pipeline is itself, so its Pipeline step looks different from every other report:

- **Systems and data views to check** — source cards owned by this check alone. Anything a report
  can read belongs here, and no saved report needs to stand behind it: the Assistant pulls each
  one silently and files no intermediate report.
- **…and pull these saved data views too** — existing reports it should also read. A report can
  stay switched off as a standalone schedule and still be pulled here.
- **What should the Assistant surface?** — one instruction over all of the above plus its own
  view of your work.

Every post records what it reviewed and leaves a note for its next check, so it does not research
the same silence twice or repeat a suggestion you have seen. **Not this** teaches it which kinds
of nudges you do not want.

Four things shape it:

- `COUNSEL.md` in Settings → Docs — how it speaks, and how readily it takes a position.
- The **Assistant** report — what it watches, its schedule, its model.
- **Settings → Assistant** — thresholds such as how long a reply or task must be quiet.
- **Settings → Learning** — whether your verdicts feed back into `LEARNED.md`.

Delete the Assistant report to switch it off. Its **Preview** shows exactly what a run would hand
the model, which is the fastest way to find out whether a watched source returns what you think
it does.

The morning brief is a separate report of type `digest`: it writes `DIGEST.md` and lands on the
Timeline daily. Deleting that report turns the brief off.

### Ideas it raises

Beyond what it watches, the Assistant looks at the shape of your own work and occasionally raises
an **idea**: a system your mail keeps naming that nothing here reads, for instance. It raises at
most one per run and never one you have already answered. If the connector is on the roadmap
rather than built, saying yes is a vote for building it.

## Stateful workflows

**Monthly Zoho invoices** is the first workflow on the Reports page that is not a query returning
one result. One scheduled run opens a batch, the batch holds one row per customer, and each row
advances separately through amount, draft, Review and sent.

1. Connect **Zoho Invoice**, then use **Monthly invoices** on Reports.
2. Choose the customers and a monthly cron. Saving enables the workflow.
3. On schedule (or **Open this month**), Taskuary reads each customer's latest prior sent invoice
   and prefills its total. No new invoice exists yet.
4. Confirm or change the amounts, then **Prepare Zoho drafts** — each prior invoice is duplicated
   as a draft and gets one durable Review card.
5. Edit and approve each email. Approval sends that invoice; leaving the page, restarting
   Taskuary or approving a different customer does not lose the others.

The duplicate boundary is `(workflow, customer, YYYY-MM)`, stored locally and written into Zoho's
`reference_number`. A retry after a timeout reuses an existing draft; an existing non-draft
invoice blocks the retry rather than creating another. A changed total is applied automatically
only when the previous invoice had one line — a multi-line invoice with a changed total stops for
attention, because Taskuary cannot safely guess how to allocate it.

## Sage Intacct, specifically

Intacct is the case that made the AI card composer necessary, so it gets explicit help.

- Objects are named, not picked: `APBILL`, `APBILLITEM`, `APPYMT`, `ARINVOICE`, `VENDOR`,
  `CUSTOMER`, `GLENTRY` / `GLDETAIL`, `GLACCOUNT`, `LOCATION`, `DEPARTMENT`, `GLBUDGETITEM`,
  `PROJECT`.
- Field ids are UPPERCASE and not guessable — `WHENCREATED` is entered, `WHENPOSTED` is posted, a
  bill's total is `TOTALENTERED`, a GL entry's is `AMOUNT`. Every company also has custom fields.
- **What fields does APBILL have?** on the source card asks Intacct itself and lists every field
  in *your* company with its label and datatype. There is also a report type for that question,
  so you can hear about it the day somebody adds a field.
- Filters are `FIELD op value`, one per line — `WHENDUE <= 08/31/2026`. Dates are `MM/DD/YYYY`,
  and `in` takes a comma-separated list.
- `readByQuery` does not group or count. "How many bills per person" is the rows with the person
  field included, plus a prompt that counts them.

:::warn A named business number is not a query to write from scratch
The chart of accounts is configured per organisation, so a hand-written GL query is plausible and
wrong. Use a metric that has been proved against figures you already knew, and say plainly when
a number has not been.
:::

Leaving the field list blank returns every field on the object — right for a list you want to
eyeball, wrong for GL detail.

## API

| Endpoint | Does |
|---|---|
| `POST /api/reports/compose` | A sentence in, a whole report configuration out (or its questions) |
| `POST /api/reports/compose-sources` | A sentence in, source cards out |
| `POST /api/reports/preview` | Dry-run a configuration, AI pass and chart included, filing nothing |
| `POST /api/sources` | Save a report |
| `POST /api/sources/{id}/run` | Run one report now |
| `POST /api/ingest/poll` | Run everything that is due |
| `GET /api/report-types` | Every type this install can run, and whether its connection is ready |
| `GET /api/intacct/fields?obj=APBILL` | What that object carries in this company |

The full interactive reference is at `/api/docs` while Taskuary is running.

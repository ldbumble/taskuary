# Reports and the Assistant

Reports are how Taskuary reads the systems you work in, and the Assistant is a report with a
different job: instead of filing what it read, it decides whether any of it is worth your
attention. They share one builder, which is why they share one page here.

- [A report is a pipeline](#a-report-is-a-pipeline)
- [Sources](#sources)
- [Let the AI write the source cards](#let-the-ai-write-the-source-cards)
- [The AI pass](#the-ai-pass)
- [Where a run goes](#where-a-run-goes)
- [Schedules](#schedules)
- [The Assistant](#the-assistant)
- [Monthly invoice workflows](#monthly-invoice-workflows)
- [Sage Intacct, specifically](#sage-intacct-specifically)
- [API](#api)

## A report is a pipeline

One report is one saved configuration on the **Reports** tab, built in four steps:

| Step | What it decides |
|---|---|
| **Pipeline** | The title, the sources it reads, and the one prompt that reads all of them |
| **Test & preview** | Test calls a single source; Preview runs the whole pipeline, AI pass included, without filing anything |
| **Schedule & save** | How often it runs, and whether each run goes through triage |
| Delivery and alerts | Optional, both on the Pipeline step: send each run somewhere, or say nothing unless the result trips a rule |

Sources at the top, one prompt at the bottom. Every source runs on its own connection and
query, the results are stacked under labelled headers, and the prompt sees all of them at once.
One source failing is reported in place and never takes the whole report down.

The connections themselves are **not** configured here. A source names the connector card its
credentials live on — Connections owns the credential, Reports owns the question.

## Sources

A source card carries the type, an optional label, whatever that type needs to run, and a row
cap. The type picker is grouped by where the data lives: this computer, files and sheets,
databases, AWS, Azure, Microsoft 365, monitoring, corporate systems, the AI itself, the web,
Taskuary's own data. See [Integrations](integrations.md) for the full list.

Three things are worth knowing:

- **label** is how the prompt refers to that data. Two queries against the same database are
  two sources, and without labels the prompt cannot tell them apart.
- **max rows** is blank by default, and blank means 200 — a cap nobody chose. When a run is
  capped the headline says so, so the AI can never describe a truncated slice as complete.
- **Test — show me the data** on the card returns the exact text a scheduled run would hand the
  prompt. Use it before assembling the rest of the pipeline.

Drag the cards to reorder them. Duplicate one to ask the same connection a second question.

## Let the AI write the source cards

A source card asks you to know things first: which of thirty-odd types your data sits behind,
what that type's config keys are called, and the query language of whatever is on the other end.
Nobody remembers that a GL entry's amount is `AMOUNT` but a bill's is `TOTALENTERED`. So you can
describe what you want instead, in three places:

| Where | What it writes |
|---|---|
| **Describe the report you want**, top of the Reports tab | A whole report: type, query, prompt and schedule, dropped into the builder |
| **let AI fill this in**, on any source card | That one card, in the type the card is already set to |
| **Describe what the Assistant should keep an eye on**, on the Assistant's Pipeline step | Every source the ask needs, plus the instruction to judge them by |

Four things keep this from being a wish machine:

1. **It may only choose a type whose connection is actually set up.** The catalog is built from
   this install's live connectors, so it cannot answer "connect to Salesforce" — it can only say
   that nothing here reaches Salesforce, and what you would have to connect.
2. **The config keys come from the executors' own docstrings.** One source of truth, so a
   composed card cannot drift from the keys the code actually reads.
3. **It reads the real schema before writing a query.** It can look up an object's field list, a
   table's columns, or a lookup value (which `LOCATIONID` the site you named actually has) and
   then answer with the names this company has, custom fields included. Up to three look-ups per
   ask; each one is a real call and its result is fed back to the model.
4. **It is allowed to say it does not know.** Questions come back as questions — at most three,
   each answerable in a few words. A guessed `WHERE` clause on a finance report is silently
   wrong forever; a question costs five seconds.

Everything it writes is then checked before you see it: a real type, a connected one, and the
keys that type needs to run at all. A card with only a type in it is your own empty form handed
back to you, and is refused as an error rather than presented as an answer.

Nothing is saved. A composed card lands in the same boxes you would have filled in by hand;
**Preview** runs it for real and you look at actual rows before anything is scheduled. Report
titles, schedules and delivery are never written onto a source card — those belong to the report
around the cards.

## The AI pass

The prompt at the bottom of the pipeline is what turns rows into prose. Leave it empty and the
raw rows file as they are.

- Write it as a concrete instruction — "Summarize spend by site; flag any vendor above 10k or
  new this month" — not "summarize the data".
- **Brain**: by default the triage brain writes it. Any connector with a key saved can be
  picked per report instead. A saved pick that has lost its key stays visible and disabled
  rather than silently vanishing.
- If a prompt is set with no AI connector active, the raw data files and the builder says so.
- When one column is a measure worth plotting, the model that just read every row says so and
  the run hands back a bar chart alongside the text.

## Where a run goes

Every run lands on your **Timeline**. Two optional additions, both off by default:

- **Send it somewhere** — email, Teams, Telegram, WhatsApp, iMessage or Discord. It waits in
  Review for your approval by default; "send it without asking" is the one place in Taskuary
  where that gate can be turned off, deliberately.
- **Tell me when it looks wrong** — silence is the normal outcome. An alert fires only when the
  result trips a rule: nothing came back, anything came back, fewer or more rows than N, the
  result mentions (or never mentions) something, or the report failed to run. Alerts send the
  moment the rule trips, with no Review step — an alert waiting for approval is not an alert.

**Can become work** sends each run through triage like an inbound message, so `TRIAGE.md`
decides whether it becomes a task. Off by default: a report is informational. A failed run is
never triaged.

Under each report row, the last run shows what it read, what came out, and the error when it
failed. Full history per report is kept alongside it.

## Schedules

Pick one: every N minutes, daily at `HH:MM`, a five-field cron, or on app startup. Everything
blank means once a day while the app is open. A slot missed while the app was closed fires once
on reopen. **Run due now** on the Reports tab runs everything that is owed; **Run now** on a row
runs that one report immediately.

## The Assistant

The Assistant is a report of type `assistant`. It runs on its own schedule and when the app
opens, and it posts on the Timeline **only** when it finds something worth saying: an unanswered
reply, context for an upcoming meeting, a task gone quiet, a pattern across incoming work, or
something in the systems it watches that does not look right. Each suggestion names its evidence
and offers **Make it a task**, **Done**, **Snooze a day** and **Not this**.

Its pipeline is itself, so its Pipeline step looks different from every other report:

- **Systems and data views to check** — source cards owned by this check alone. Anything a report
  can read belongs here, and nothing else needs to exist: the Assistant pulls each one silently
  on its own schedule and files no intermediate report. Saved as `watch_sources`.
- **…and pull these saved data views too** — existing reports it should also read. A report may
  stay switched off as a standalone schedule and still be pulled here; its query and credentials
  remain owned by that report and its connector. Saved as `watch_source_ids`.
- **What should the Assistant surface?** — one instruction over everything above plus its own
  view of your work.

Every post also records what it reviewed and leaves a note for its next check, so it does not
research the same silence twice or repeat a suggestion you have seen. **Not this** teaches it
which kinds of nudges you do not want.

Four things shape it:

- `COUNSEL.md` on the Docs tab — how it speaks to you, and how readily it takes a position.
- The **Assistant** report — what it watches, its schedule, and the model it uses.
- **Settings → Assistant** — thresholds such as how long a reply or task must be quiet.
- **Settings → Learning** — whether your verdicts feed back into `LEARNED.md`.

Delete the Assistant report to turn it off. Its **Preview** shows exactly what a run would hand
the model, which is the fastest way to see whether a watched source is returning what you think
it is.

The morning brief is a separate report of type `digest`; it writes `DIGEST.md` and lands on the
Timeline daily. Deleting that report turns the brief off.

### The interactive guide, on desktop and WhatsApp

The floating Taskuary logo is the interactive side of the Assistant. It is a durable chat with a
fresh snapshot of needs-me email and messages, open tasks, pending Review items, recent Timeline
activity, and filed coding or other agent output on every turn. It can prioritize that state and
walk through it with you; it is not a second scheduled report.

The AI strip in the floating panel shows exactly which provider and model answer the guide. The
choice is saved and shared with WhatsApp. A configured API or local-model connector is the fast,
in-process default; a CLI agent remains selectable when the conversation needs its tools. Use
**Walk through all** for a turn-by-turn review: the guide presents one unresolved item, asks one
question, and waits for the answer before advancing.

The same conversation can travel over WhatsApp:

1. Pair the WhatsApp connector and send a message to WhatsApp's private **Message yourself** chat.
2. Under the connector's chat list, click **Use for assistant** beside that direct chat. This adds
   the Notifications role, names the chat, and enables **Settings → Notifications → Chat with the
   assistant in WhatsApp**.
3. Ask naturally: “what needs me?”, “walk through important email,” “what is outstanding?”, or
   “what did the coding agents finish?” Answers also remain in the desktop guide conversation.

Only messages sent by the linked owner account in that exact direct chat are accepted. Groups
cannot be selected because guide answers may reveal private workspace information. Taskuary marks
its own bridge output so notifications and answers cannot loop back into the guide. Tagged agent
answers and Review verdicts continue to use `[tq…]` and `[rv…]`; explicit `approve`, `reject`, and
`no reply` retain their phone shortcuts.

## Monthly invoice workflows

**Monthly Zoho invoices** is the first stateful workflow living on the Reports page. It is not a
query that produces one result: one scheduled run opens a batch, the batch contains one row per
customer, and every row advances separately through amount, Zoho draft, Review, and sent.

1. Connect **Zoho Invoice** under Connections, then use **Monthly invoices** on Reports.
2. Choose the customers and a monthly cron. Saving enables the workflow.
3. On schedule (or **Open this month**), Taskuary reads each customer's latest prior sent invoice
   and prefills its total. No new invoice exists yet.
4. Confirm or change the amounts, then **Prepare Zoho drafts**. Taskuary duplicates the prior
   invoice as a draft and creates one durable Review card per customer.
5. Edit and approve each email in Review. Approval sends that invoice through Zoho; leaving the
   page, restarting Taskuary, or approving a different customer does not lose the other drafts.

The duplicate boundary is `(workflow, customer, YYYY-MM)`. Taskuary stores it locally and writes
it into Zoho's `reference_number`. If preparation is retried after a timeout, an existing draft
is reused; an existing non-draft invoice blocks the retry rather than creating another. A changed
total is applied automatically only when the previous invoice has one line. A multi-line invoice
with a changed total stops for attention because Taskuary cannot safely guess how to allocate it.

This is deliberately under **Reports** for now. It shares the scheduler, connector model, Timeline
receipt, and Review gate. If more stateful workflows join it and the page becomes primarily about
multi-step work rather than read-only outputs, renaming the page to **Workflows** will then describe
what the page actually contains instead of anticipating it.

## Sage Intacct, specifically

Intacct is the case that made all of this necessary, so it gets explicit help.

- Objects are named, not picked from a menu: `APBILL`, `APBILLITEM`, `APPYMT`, `ARINVOICE`,
  `VENDOR`, `CUSTOMER`, `GLENTRY` / `GLDETAIL`, `GLACCOUNT`, `LOCATION` (sites and entities),
  `DEPARTMENT`, `GLBUDGETITEM`, `PROJECT`.
- Field ids are UPPERCASE and not guessable — `WHENCREATED` is entered, `WHENPOSTED` is posted,
  a bill's total is `TOTALENTERED`, a GL entry's is `AMOUNT`. Every company also has its own
  custom fields.
- **What fields does APBILL have?** on the source card asks Intacct itself and lists every field
  in *your* company with its label and datatype. Click one and it lands in the card's field list.
  There is also a report type, **Intacct — what fields exist**, so you can schedule that question
  and hear about it the day somebody adds a field.
- Filters are `FIELD op value`, one per line — `WHENDUE <= 08/31/2026`. Dates are `MM/DD/YYYY`.
  `in` takes a comma-separated list.
- `readByQuery` does not group or count. "How many bills per person" is the rows with the person
  field included, plus a prompt that counts them.
- A named business number is not a GL query anyone should write from scratch: the chart of
  accounts is configured per organisation, so a hand-written one is plausible and wrong. Use a
  certified metric (**Assistant → Numbers**) when the number has been proved against figures you
  already knew, and say so plainly when it has not.

Leaving the field list blank returns every field on the object, which is the right default for a
list you want to eyeball and the wrong one for GL detail.

## API

| Endpoint | Does |
|---|---|
| `POST /api/reports/compose` | A sentence in, a whole report configuration out (or its questions) |
| `POST /api/reports/compose-sources` | A sentence in, source cards out; `type` scopes it to one card of that type |
| `POST /api/reports/preview` | Dry-run a configuration, AI pass and chart included, filing nothing |
| `POST /api/sources` | Save a report (`Channel: "report"`, config as `ConfigJson`) |
| `POST /api/sources/{id}/run` | Run one report now |
| `POST /api/ingest/poll` | Run everything that is due |
| `GET /api/report-types` | Every type this install can run, and whether its connection is ready |
| `GET /api/intacct/fields?obj=APBILL` | What that object carries in this company, custom fields included |
| `GET /api/reports/{id}/invoice-batches` | Monthly batches for a Zoho invoice workflow |
| `POST /api/reports/{id}/invoice-batches` | Idempotently open a `YYYY-MM` batch |
| `PATCH /api/invoice-batches/{batch}/items/{item}` | Save a customer amount or recipient |
| `POST /api/invoice-batches/{batch}/prepare` | Create/reuse Zoho drafts and place their emails in Review |

The full interactive API reference is at `/api/docs` while Taskuary is running.

## Related documentation

- [Product guide](product-guide.md)
- [Integrations](integrations.md)
- [Getting started](getting-started.md)

# Beyond code: how one funnel handles a million kinds of task

*A design note, 2026-09-01. Step 1 is built; the rest is the shape the owner and the agents
agreed to build toward. The question that prompted it: "a credit-card transaction arrives; it should
become an AP bill in QuickBooks. The task can be anything. How do we handle the million assorted
tasks, not just development?"*

## What is already general

A task in Taskuary is not a coding task. It is **text plus context, handed to an agent standing in a
folder with tools**. The agent happens to be a coding CLI because that is the best general-purpose
worker anyone ships today - it reads, reasons, runs commands, calls APIs, writes files. `kind:
coding` is a misnomer; it means "an agent works this from a keyboard", and triage already sends
almost everything there (TRIAGE.md: "a system to change, an account to unlock, a database to query,
a document to draft, a vendor to chase - all `coding`").

So the runtime does not need a second engine. Posting a credit-card transaction into QuickBooks
needs exactly what fixing a bug needs, and the three things are the same three:

1. **A connection** - something the agent can read from and write to. For code that is a checkout
   and GitHub. For AP it is the card feed in and QuickBooks out.
2. **A playbook** - how *this company* does *this kind* of job, and where the line is between
   "just do it" and "ask". For code that is CODER.md. For AP it does not exist yet.
3. **A receipt** - what it did, with ids, so the owner can check and undo. For code that is a diff,
   tests and a PR. For AP it is the bill number, the vendor, the amount, the period.

Where the current design falls short is (2): there is one playbook, CODER.md, and it is about code.
"Work ONLY in the repository the task names" is the wrong first rule for a bill.

## The proposal: playbooks, accreted one at a time

You do not enumerate a million tasks. You let the company's playbooks accrete, one per **kind of
job**, the first time each is done - the way Social accretes facts.

**A playbook** is a markdown file under `~/.taskuary/playbooks/<slug>.md` (beside the operator
documents, versioned like them). It has two doors: a *Playbooks* shelf on the Docs tab, where they
are read and edited like SOUL.md, and a *Playbooks* section on each connector card listing the
ones whose `uses:` line names that connection - the QuickBooks card shows every job that posts to
the books. One file, two doors; the connector is where you look for "what does this thing do for
us", the Docs tab is where you edit the words. Five parts:

```
# Post a card transaction as an AP bill
when:      a transaction or statement line from the card feed; a mail from Amex with a statement
uses:      quickbooks (write: bills, vendors)  ·  card-feed (read)
steps:     match the merchant to a vendor (create one only if the owner says so) → pick the
           expense account from the memo and the vendor's history → create the bill dated the
           transaction date, memo = card last-4 + transaction id → attach the receipt if one came in
alone:     bills under $500 to a vendor seen before, in an open period
ask first: a new vendor · anything over $500 · a closed period · a split across accounts
done when: the bill exists in QuickBooks and its DocNumber is on the task
```

**Triage learns a new road: `playbook`.** Today `kind` decides *who* works a task (coding = agent,
general = chat, reply = the drafter). A task that matches a playbook's `when` is seeded with
SOUL.md + **that playbook** - and CODER.md only when the playbook is about code. The seed prompt's
shape does not change; what rides in it does. `context.py` already builds the per-task context
file; the playbook is one more section.

**The first run is assisted, not automatic.** When a transaction arrives and no playbook matches,
the task still lands on the agent with the ask, and the agent does the job *with the owner in the
session* (that is what the live terminal is for). On close, the same on-close pass that writes
Social entries (`handbook.learn_from_session`) asks one more question: *did this session do a kind
of job that will recur? Draft its playbook.* The draft lands in Review as a proposal; approving it
files it. The second transaction matches it. That is the accretion: every kind of task is done by
hand once, by the agent with the owner watching, and never twice.

**The money gate is the one that already exists.** Writes to a financial system never happen
directly. The agent emits `TASKUARY-PROPOSE {"action": "run_tool", "type": "quickbooks_bill", ...}`
(proposals.py) and the proposal is a Review card: vendor, amount, account, period, the receipt
image beside it. The playbook's `alone:` line is a **routing policy** (Settings → Routing
policies), the deterministic gate the AI cannot override: *auto-approve quickbooks_bill when vendor
known and amount < 500 and period open*. Until a playbook has one, every bill waits for a click -
exactly how "send" and "push" work today, and for the same reason. Report deliveries already have
the switch that turns this off deliberately ("send it without asking"); a playbook earns the same
switch the same way.

**The receipt is the proof card.** `proof.py` today measures git; for a playbook run it measures
what the playbook's `done when` names: the DocNumber exists, the amount matches the transaction,
the period was open. A thin card still says what is missing.

## What to build, in order

1. **QuickBooks Online connector** - *built (taskuary/quickbooks.py, 2026-09-01)*. OAuth2 against
   the owner's Intuit app with Connect on the card, five tools: `quickbooks` (QBO's query
   language), `quickbooks_vendors` and `quickbooks_accounts` (read), `quickbooks_bill` and
   `quickbooks_expense` (write, proposal-gated below scope `write`).
2. **Playbooks** - the folder, the Docs-tab shelf, the `when` matcher in triage, the seed section,
   and the on-close "draft its playbook" question. Small: it is a fourth operator document with a
   directory instead of a file.
3. **A card feed in.** Two roads, cheapest first:
   - *Statement mail.* Card issuers already email statements and alerts; the mailbox connector
     already ingests them and their attachments. A playbook that reads the PDF/CSV needs no new
     connector. This is where to start - it exercises the whole loop with zero new plumbing.
   - *A bank-data aggregator* - **Teller, built (taskuary/teller.py, 2026-09-01)**: the owner
     enrols each bank login themselves in the card (Teller Connect), development tier free to 100
     logins, certificate auth outside sandbox. Chosen over Plaid because this is a local install
     and the owner does the enrolment - no hosted approval flow, no per-account fee at this size.
     Its transactions report with "can become work" on is the trigger: each new transaction is a
     message triage judges.
4. **Proof for non-code.** Teach `proof.py` to read a playbook's `done when` and check it.

## What this is not

- Not a workflow builder. No boxes and arrows; a playbook is a page of prose the agent reads, the
  same way CODER.md is. If a step needs code, the agent writes the code.
- Not a second agent. The CLI the owner already pays for does the work; QuickBooks is a tool it
  calls through Taskuary, gated like every other tool.
- Not automatic on day one. Every new kind of job is done once with the owner watching, and only
  the owner's approval of the drafted playbook makes the second one hands-off.

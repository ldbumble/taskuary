# Working in this repository

## Never commit the owner's own data

This repository is **public**. It is also built by reading one person's real mail, so the pull is
constant: the quickest way to write a test for a bug is to paste the message that caused it, and
the clearest way to explain a fix is to name the people in it. Both put a private thing somewhere
it cannot be taken back from — a commit message, a fixture, a comment, a screenshot.

**None of it goes in.** Not in code, tests, fixtures, docs, comments, commit messages, or images:

- names of colleagues, senders, residents, patients or customers
- company names, facility names and numbers, internal repository names
- mailbox addresses and the domains around them
- what a real thread actually said, where it identifies the people in it
- anything a divestiture, a contract or a salary could be read out of

What a bug NEEDS is its shape — a forwarded chain, a report that repeats, two mails in one poll.
Write that, with invented people. A test reads better for it, and the failure it pins is the same.

### The stand-ins this repository already uses

Addresses use RFC 2606's reserved names — `*.example`, `example.com`, `.test`, `.invalid` — and
nothing else. `tests/test_demo.py::test_nobody_real_is_in_it` enforces that for the demo world, and
it asserts the invariant rather than naming any real domain, which is the pattern to copy: a guard
that spells out the thing it guards against has published it.

| for | use |
|---|---|
| the owner | Alex Doyle, `alex@northwind.example` |
| their company | Northwind, `northwind.example` |
| colleagues | Erin Blake, Gail Moreno, Paula Vance, Ray Colton, Marcus Reed, Omar Keller |
| a vendor | `vendor.example`, Payworth, Trainly, Spendly, PhishGuard |
| repositories | `northwind/ledger`, `northwind/portal`, `org/app` |

**The one exception** is the connector catalogue (`taskuary/connectorcatalog.json`,
`website/src/logos.jsx`, `docs/site/connections.md`, the keyword list in `taskuary/reports.py`).
Naming PointClickCare, ADP, Epic or Cerner there says what this app can connect to. That is a
feature of the product, not a fact about its owner.

### A commit message is public too

Say what changed and why it was wrong. The story can keep its shape without its cast: "a sender
wrote twice in one morning", not the sender's name; "two divested sites", not which ones. If the
detail is what makes the commit understandable, it belongs in the code comment — with invented
names there as well.

### Screenshots and recordings

`docs/*.png` and `docs/product-demo/*.mp4` are shot from a running app. Shoot them against the
demo world (`taskuary --demo`), never against a live mailbox, and check the sidebar, the titles and
the notification tray before committing the frame.

## How this product is built: the owner's rules

The north star, in the owner's words: **"job of agent is to be helpful and do as much as possible."**
The agents run the show; the code's job is to give them the right tools, tell them the truth, and
keep the few things that must be exact, exact. Every change and every audit is judged against the
rules below.

### 1. The agent does the work

- Whatever arrives that needs work or an answer goes to the task's agent **as it arrives**: no
  second voice drafts, judges or edits for it (no one-shot writer, no side model rewording its
  cards or asking questions in its name).
- The agent goes as far as it can by itself. Where the next step is the owner's to press, it sets
  that step up as **one action card** and says what it will do after the press ("deploy, then I
  reply that it is live"). When the press comes it is woken and does it.
- Inside a task only the task's agent recommends. The Assistant and the Advisor speak on the rail,
  and act when the owner asks them to.
- A missing fact only the owner has is **one question in the task**, never a guess sent as their
  answer, and never a question on the rail.

### 2. AI for judgement, plain code for actions

- **Meaning is a model's to read**: is this a question, is it urgent, is it finished, what kind of
  work is it, who is a person. No word lists, keyword tuples or regexes decide meaning. A regex may
  parse structure (a header, a command's grammar, a marker the app itself wrote).
- **Actions are deterministic**: sending, pushing, paying, saving, deleting, scheduling, and the
  record of what was pressed are plain code, the same every time, with a test. Anything that
  leaves the computer or cannot be undone is **held as a card for one press** - never done
  silently, never flatly refused where the owner could simply say yes.
- **No model call where stored facts already answer**: a review's status, an audit row, a worker
  event, a setting, a message's stored sender class.
- A rule that is the same every run is code, not a prompt: a routine's script step computes it,
  and an AI step reads what it printed.
- Guidance to an agent is general - one or two sentences where it is told its job - never a rule
  per scenario. If the prompt grows, something else in it should go.

### 3. One road, less code, robust code

- **One road per job.** Before adding a function, find the one that already does it and make that
  one serve. Two paths deciding the same thing drift, and the drift is the bug.
- **Shared and short.** A fix that removes a duplicate beats one that adds a case. Dead code left
  by a change goes in the same change.
- **Consistent.** The same fact reads the same on the rail, in the task, on the phone and in what
  the agent is told: one function says it, every surface calls it.
- **Robust means it handles the shape, not the example.** No special case per provider, sender,
  host or task kind where one general rule can serve.
- **Tell the truth.** Never say something is being done when nothing is doing it; never "sent",
  "taken off" or "asked" for something that did not happen; an agent is told whose decision a no
  was.

### 4. No dead ends

A dead end is any state where something is owed and nothing is running, nothing is said, and no
button is lit. For every state ask: who moves next, and can they see how?

- A start that cannot happen now is **queued and retried**, or says why in one line.
- Every press leaves a line in the chat in the owner's voice and reaches the agent once.
- A failure is kept where it happened, with the way past it.
- Nothing an agent can call answers without saying what to do next.

### 5. What a stress round covers

Push shapes through the **real** code and follow each one to the end - who works it, what the
owner sees, what a press does, what the agent is told after. A round is not finished until it has:

- **Every sender class** from arrival to every card that names a recipient: a person, a stranger,
  an automated notice, a list, a no-reply address, the owner's own message.
- **Timelines on one task**, not single arrivals: a draft exists, the owner answers outside the
  app, the sender writes again, a press, a second press, a restart in the middle.
- **Real session shapes** fed through to the chat: a long session the CLI compacted, a resumed
  one, a tool error, a turn that ended mid-work, a session that ended before its press.
- **Every action against every answer**: approve, edit, reject, withdraw, replace, pressed twice,
  pressed after the agent stopped, a press whose execution fails.
- **Every way a start can be refused**: the switch off, no AI, a full house, a stranger held, a
  channel that waits - each must queue, light a move, or say why.
- A bug the owner reports from the live app is added to the round as its shape, with invented
  people, before it is fixed - and first check which build the running app is on.
- **Every on-screen scenario is recorded and watched** (`website/browser/recorder.mjs`), before and
  after a fix: a flicker, a jump, a thing that appears then moves, or a blank beat is a finding even
  where every assertion passed.

Then the same pass for the code: duplicate roads folded, dead code deleted, fixed rules that judge
meaning and model calls that plain data could answer listed with file and line.

### 6. How a fix lands

- A test that fails on the old code and passes on the new, in the nearest existing test file,
  reproducing the live shape - timing and order included.
- What changes what the owner sees or presses beyond these rules is asked first, in plain words.
- Small commits straight to `master`; targeted tests locally, the full suites in CI; red CI is
  fixed forward at once, rerunning only what failed.

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
- **The code never tells an agent how to do its job** (the owner, 2026-11-23, said many times). An
  agent gets CONTEXT (the owner, SOUL/JOB, memory, the task's material and history, what his screen
  shows - as facts), TOOLS (each tool's description says what it does, never how to behave), and
  ONE SENTENCE: do what is asked; a step that needs the owner's yes or something only they can give
  is an action card; otherwise do not bother them. The agent decides how a turn ends. Only security
  is hard-coded: what an agent may touch, and which acts wait for his press.
- **A fix never adds a sentence to what an agent is told, and never adds a special case.** It
  changes state, a tool, a card or an action - and it should delete more than it adds. A fix that
  needs words to the agent to work is the wrong fix.

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
- Every press shows its result on what was pressed (a card says what it did, never repeated as a chat line) and reaches the agent once.
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
- **Everything that rides into a prompt, through every door**: a picture, a PDF, a sheet, a report, a
  dashboard, an FYI, a routine - attached in New, on a chat's line, a coding task's line, Send to agent and
  Continue - followed until the agent has READ it (its own log, not the app's), and shown on his line.
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
- tests/contract/ is locked: no agent edits it or its LOCK without the owner's written OK.

### The basic interactions (locked)

How a card is raised, pressed and handed off never changes without the owner's written OK. Each
rule below is pinned by a plain test in `tests/contract/` (the real tools and routes, no browser,
no model); `tests/contract/LOCK` holds the hash of those files, of this section and of what every
agent is told about its cards (`taskuary/templates/agents.md`), and `tests/test_contract_lock.py` fails
when any of them differs. A contract test that fails is a broken
product: fix the code, never the test.

1. **Raise.** The agent supplies the content; Taskuary builds one valid card and picks the road
   from the connection's state: connected, its press goes through the connection; not connected,
   the post goes up through the browser at his press, with Connect beside it - that one press is his
   yes for the site's own Post of exactly those words, and no second card asks it again (the owner,
   2026-11-27: "yes do all 10"). A bad card (over the
   network's limit as the network counts it, a picture that is not there) is never shown: the agent
   is answered with the exact fix. A field the card does not draw is ignored.
2. **Press.** Approve or Send executes exactly what was shown, once. A second press does nothing.
   A card changed after it was shown does not run. A press after the agent stopped still executes.
   A failed execution stays on its card, with the way past it, and its agent is woken once with what
   failed and why. His no is told to the agent as his own.
3. **Wake.** His press executes without waking the agent, at work or at rest, unless the card
   carries its `then` - the agent's own next act after the press - or the execution fails. A press
   Taskuary confirmed went is its own check: a `then` that only does what the press did (the to-do
   the card does, which the press ticks) wakes nobody. A press with no `then` that went wakes nobody,
   and answers the question the agent asked about that card; a bulk card's run is the same, once.
   His Dismiss never wakes the agent: his no is told to it, as his, at its next turn. A `then` starts
   only when every card of that task that still waits is settled.
4. **Question.** The agent's question stands until he answers; no card is raised under it, in
   that turn or after, until he answers; his answer reaches the agent once.
5. **Hand-off on a page.** A step handed to him shows that step; his "I'm done" wakes the agent
   once. The agent may open and read a connected service's site, and hand him its sign-in where
   reading needs it; posting or sending there goes only through its card. Where a service is not
   connected its card comes first, and its sign-in is his step only after his press - drawn on that
   card, as its next step. No
   sign-in is put to him beside a card that waits: one thing is asked at a time, and what the
   browser shows belongs to the card on his screen.
6. **The turn's end.** Exactly one of needs-him / done / working. The chat shows words, cards and
   files handed over on purpose; working files are kept in the task's files, not drawn; a card's
   picture is drawn on its card only.
7. **Restart.** A restart between a card and its press keeps all of the above.
8. **Bulk, one component.** The agent chooses by how it calls, never a count: one call with
   `items` (one act to many people) is one card that does every item with one press, exactly as
   shown; one call with `versions` (one thing written several ways, on any card with words) is one
   card where he picks one, and only that one goes (the owner, 2026-11-27: "yes do all 10");
   separate calls are separate cards, one after another. Files handed
   over in one call are one artifact holding all of them. A review card and a file artifact are
   drawn by the same component (`website/src/Artifact.jsx`).
9. **Every write waits for his press.** An agent's call that writes, changes, creates, deletes or
   sends on any connector is a card, at any Authority; nothing runs before his press. What is a
   write is the executor's line in `scopes.ACTIONS` - one not listed is a write; a read (a query, a
   search, a report pulling data) runs with no card. Only Taskuary's own store is written unpressed.
   A post card pressed for the browser is that press: the site's own Post of exactly its words goes
   on it; other words, or another site, wait for his press.
   A routine's write step waits too, unless he pressed "Always approve this step" on it: that
   routine's step, exactly as saved, then runs unpressed; any other target, executor or an agent's
   own call during the run is a card as usual. Taken back under Settings → Agent permissions.
10. **Cards stay** (the owner, 2026-11-26: "Things on chat don't go away. No text after an approval
   card until the approval card is denied or approved, then the agent moves on. Cards never just
   disappear."). Nothing drawn in the chat ever disappears, hides or moves by itself. A card raised
   in a turn is drawn once, when that turn ends, under all its words, and nothing of the agent's is
   drawn after a card that waits; only his own line may come after it. A press never changes which
   tab of a card is shown, and a pressed card shows its result where it stands. Nothing he greyed is
   raised again by Taskuary: only the agent brings it back. Unrelated acts are separate cards; tabs
   are only for one call's set; a bulk act is one list card with its progress.
11. **His edit is what goes** (the owner, 2026-11-26: "never even overwrite an edit of a text for any card from
   user ... They would send email with generated email instead of their edits."). On every card with words he
   can change, his press sends exactly what he typed, it is kept as what went, and the card shows it - before
   the press, after it, and when it fails. Nothing writes over what he typed: no redraw, refresh, re-raise,
   agent update or retry. Only something new (a new message on the thread) may bring the agent's rewrite, as
   a new card beside his.

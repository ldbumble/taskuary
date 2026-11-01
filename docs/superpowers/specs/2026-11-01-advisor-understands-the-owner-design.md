# The Advisor understands the owner (design, 2026-11-01)

Status: **phase 1, diagnose and design.** Nothing here is built yet, and the Advisor's behaviour has not changed.
The owner asked for this on 2026-11-01: "Work on the advisor ideas really making it killer though you will have to make the
job.md/soul.md and memory working better from history of mail and understanding saving things about the user. especially when it
comes to users that work on multiple things."

Every example below is invented (Alex Doyle at Northwind and the stand-ins in CLAUDE.md). The measurements were taken on a copy of
a real home. Only totals and kinds of mistakes appear here, never what a message said or who sent it.

---

## 1. In one paragraph

Today the Advisor knows one thing about its owner: a single flat job description, written once, and a memory full of reply times.
Most of the buttons it lights come from rules that never read either. Someone who runs a day job, a side product with a small team
and a personal life over the same apps gets judged by the day job's rules everywhere. The fix has three parts. First, give the owner
model **one home per workstream**: built from months of the owner's own sent mail, kept current, and naming who the people are in
each. Second, make every reader use **the item's workstream**, not the first 600 characters of everything. Third, raise **only the idea
kinds that proved useful**, kept quiet until they are right at least 80% of the time on this owner's own record.

## 2. What we measured

The measurements ran on a copy of a real home: 7 and 30 days of presses, the last 32 rail ideas, and the current SOUL.md, JOB.md and
LEARNED.md.

### Lit buttons (`tools/advisor_agreement.py --replay`, last 7 days)

| | value |
|---|---|
| agreement | **44%** (51 right, 65 wrong, 14 unclear, of 130 decisions); 30 days: 41% |
| precision on what was lit | 44% on 116 (the finish check 0% on 5) |
| silent | 40% of 218 decisions |
| dropped-ball misses | 14 |
| with today's code, replayed | 49%: the fixes since then mostly turned wrong lights into silence |
| rule-lit vs model-lit | about 70% of advice rows were decided by a rule with no model and no memory read |

**Why the 65 wrong ones were wrong** (each miss was classified by hand from the item, the advice row and what the owner did next):

| cause | count | what it looks like (invented) |
|---|---|---|
| A rule decided alone and never read the owner model | 20 | Continue lit on a finished investigation that Alex reads and closes. Next lit while an agent runs that Alex then stops. Reply lit on an ask Alex settles in person. |
| Wrong workstream: side-product chat judged by day-job norms | 14 | Ledger-app tester chat in a group: Approve the draft, but Alex fixes the bug and closes, with no reply needed |
| The habit exists in Alex's behaviour but not in memory, or it sits unadopted in Proposed | 13 | Alex hands report-data asks to an agent, but the Advisor said Remind me |
| A measurement artefact (twin buttons, a light one press behind, a sent reply scored wrong) | 7 | |
| A personal chat became a task and got a lit Reply | 4 | "come over at 1:30" |
| An own-promise task made from casual talk, or a duplicate of a live task | 4 | "I'll walk you through it" |
| A second ask in the thread, or one in another thread, was missed | 3 | |

Stale memory adds to most of these. JOB.md was generated once, two weeks before the measurement, and never refreshed. The work that
dominated the last fortnight, a budget season and two new dashboards, does not appear in it.

**The 14 dropped balls.** 6 are real: Alex stopped an agent that nothing had flagged, so the Advisor does not watch whether a running
agent is still going the right way. 8 are Alex steering a long coding task with Continue, which the metric wrongly counts as a dropped
ball.

### Rail ideas, the last 32 graded

| grade | count | the pattern |
|---|---|---|
| useful | 19 | Every one connects things: a promise two days unkept; a draft 8 hours unsent; one thread's answer deciding another thread's open point; three changes to the same app, so batch them; a second report of the same outage, so the earlier "not stuck" close may not hold; a second ask hidden beside a newer reply; prep for tomorrow's meeting from the open asks of the people in it |
| obvious | 11 | Eight restate one failure row a monitoring report already showed, and two of those are the same failure on two days. Plus an out-of-office auto-reply, and a direct report's chat that Alex handles in person |
| wrong or stale | 2 | "Your CI has failed for 30 days" about the side product Alex works on daily. "This task has no next step" on a task Alex was steering that day |
| creepy | 0 | |

**Idea precision: 59%.** Without the single-row restatements it is **90%**. The thinking is good when it reasons across threads. The
noise is one idea type.

### The owner documents, judged against the mail

The mail shows at least four streams: the day job, which covers several sister companies under one mailbox domain; a side product
with its own team chat, repository and testers; a monitoring mailbox that is most of the volume (a sensor for the day job, not
work); and personal chats. The documents get this wrong in several ways:

- **JOB.md covers only the day job.** It is one block generated from 90 days and never refreshed. Its title for the owner disagrees
  with SOUL.md's and with the owner's own signature.
- **SOUL.md** has good hand-written priorities, such as two people whose asks always come first. But its machine-written project
  section files day-job colleagues under a repository.
- **LEARNED.md, "Your people"**, is 22 reply-time lines and nothing else: no "what they are to you" and no workstream. It includes a
  mail-system relay address and a personal contact.
- **LEARNED.md, "What becomes a task"**, has about 4 good general lines and about 18 one-off "filed this subject" lines. Some of those
  quote subjects that name third parties.
- **LEARNED.md, "How you work"**, is five near-identical lines about resuming a coding agent. They hold only for the side product.
- **LEARNED.md, "Promises" and "What to bring up"**, are empty, although promise ideas fire and about 500 ideas were decided.
- **LEARNED.md, "Proposed rules"**, has 11 rules waiting for adoption, one with 31 pieces of evidence ("friendly chat with no ask is
  not a task"). Adopting them would have prevented most of the side-product and personal misses.

### The live A/B yardsticks (run as scripts on copies)

| eval | memory empty | memory filled |
|---|---|---|
| lit button (`tests/test_advisor_memory_live.py`, 28 asked cases) | 20 right, 5 wrong, 3 gap | **25 right, 3 wrong**: 5 better, 0 worse, nothing dead cited |
| rail ideas (`tests/test_rail_advisor_memory_live.py`, 17 cases) | 5 hit, 2 miss, 10 quiet, 0 noise | **the same, 5 / 2 / 10 / 0** |

The memory helps the lit button when the right line exists. On the rail it changed nothing. "Your CFO hasn't answered in three days"
misses with and without the line saying to chase her within a day. Neither eval has a single case with two workstreams, so neither
can see the problem this design is about.

## 3. How it works today

| piece | how it is made | how it stays current | who reads it, and how much |
|---|---|---|---|
| SOUL.md | an interview at setup, a "How I work" block from up to 40 sent mails, and connection, project and repo sections kept in sync | by hand; the synced sections update by themselves | triage the first 2,500 chars; the event Advisor **the first 600**; the rail Advisor and the Assistant all of it; agents all of it minus the triage rules; strangers none |
| JOB.md | "Generate from history": 90 days, up to 300 sent and 500 received per mailbox; one `## At {org}` section per **mailbox domain** | only when someone presses Generate again | triage 2,500; the event Advisor **600**; the nightly memory rewrite **600**; the rail Advisor and the Assistant all of it; agents all of it |
| STYLE.md | the same generator, from 60 sent mails | edited drafts and lines per recipient | the drafter, 2,500 |
| LEARNED.md | a one-line lesson per correction (into Watching) and a full rewrite at most daily (40 episodes, 5,000 chars of events) | strength decays only on Watching and Proposed; Keep / Wrong / Forget; a line is closed when a later fact contradicts it | triage all of it; the event Advisor a 4,000-char cut of four sections; the rail Advisor and the Assistant 2,000 chars; an agent the people on its task, the rest on demand |
| person pages | built from the outcome ledger | rebuilt at each rewrite | Advisor, Assistant |
| rail ideas | `assistant.run` every 30 minutes reads the blocks above and returns `idea:` entries | the owner's take-up or dismissal teaches a line | the owner |

Where multiple workstreams are lost:

- No task, message, idea or memory line records which workstream it belongs to.
- Organisations are split by mailbox domain only, so sister companies under one domain, or a side product run from the same mailbox,
  collapse into one.
- `owner_title` and `owner_company` each hold a single value.
- Section caps (15 lines in use) are shared by every workstream.
- The 600-character cuts mean the event Advisor never sees a second workstream section, even if one existed.

There is also a gap against an existing ruling. **"Pause learning" in Settings, ruled 2026-10-23, does not exist in the code**: the
setting is deleted at startup.

## 4. The top five root causes

1. **Most lights never consult the owner.** About 70% of advice comes from rules that read neither JOB nor LEARNED, and 20 of the 65
   misses are those rules. They light Continue, Reply or Next by state alone, though their own track record in that state is 0-25%.
2. **One flat owner, many workstreams.** One JOB, one title, one company, and no workstream on anything. 22 of the 65 misses (14 side
   product, 4 personal, 4 casual-talk promises) are the day job's norms applied where they don't belong.
3. **The memory saves the wrong things.** It saves reply times and one-off filings. It does not save who people are, what was promised,
   what to bring up, or which habits belong to which stream. The strongest lessons wait unadopted in Proposed.
4. **The owner model goes stale.** JOB.md is written once from one 90-day window. The nightly rewrite sees 600 characters of it and 40
   episodes. This season's work is invisible.
5. **The Advisor watches the wrong things, and the yardstick can't tell.** It doesn't watch whether a running agent has drifted (6 real
   dropped balls). A third of its ideas restate a single report row. The rail eval scores the same with or without memory. The
   agreement tool counts the owner steering a task as dropped balls and also counts twin buttons as misses.

## 5. The design

### 5.1 One home per workstream

A **workstream** is a body of work with its own people, systems, goals and norms. Alex Doyle has four:

| workstream | what makes it one | invented people |
|---|---|---|
| Northwind finance systems (day job) | `alex@northwind.example`, Teams, the `northwind/ledger` and `northwind/portal` repos | Erin Blake (manager), Ray Colton (runs payroll), Paula Vance (CFO) |
| The Ledger app (a product Alex builds with two friends) | a chat group, `org/app`, testers | Omar Keller (tester), Marcus Reed (co-builder) |
| A nonprofit board seat | a second mailbox, quarterly cadence | Gail Moreno (board chair) |
| Personal | family and friends' chats | not learned, not shown |

**Where it lives.** JOB.md keeps its name and its place in the layers. It becomes an **index** (one line per workstream: what it is,
its role, the people who matter most, active or quiet) followed by **one marked section per workstream**:
`<!-- ws:ledger-app:start -->` ... `<!-- ws:ledger-app:end -->`. Each section holds:

- what this work is, and Alex's role in it
- who the people are, and what each is **to Alex** ("Omar Keller tests the Ledger app; his bug reports become coding tasks")
- the systems, repositories, channels and mailboxes it runs on, plus the feeds that report on it
- **this season**: live goals with an end date, such as "Q4 budget due 2026-11-15"
- the cadences, what Alex decides, and what Alex hands up
- what wins when this workstream clashes with another

Lines the owner writes outside the markers survive, as today. Personal has an index line and no section.

**Mapping everything to a workstream.** Each message, task, idea and memory line gets a `Workstream` field. A message is mapped from
the strongest signal available:

1. its thread, if the thread already has a workstream
2. its mailbox or identity, and its chat group or Teams team
3. the people on it: a person belongs to one or more workstreams, weighted by where Alex writes to them
4. the repository or system it names
5. otherwise triage's own model reads it and decides, and says "unsure" when it can't

A task inherits its workstream from its source. An idea carries the workstream of its evidence; a cross-workstream idea carries both.
Machine mail, such as monitoring and notifications, joins a workstream as a **feed**: it informs, and it is never a person and never a
habit.

**People lines change shape.** "You answer Erin Blake within 2h" becomes "Erin Blake: your manager (Northwind finance); you answer her
the same day; you hand her budget sign-offs." The reply time stays, but as one fact among the useful ones. A mail relay or a no-reply
address is never a person.

### 5.2 Built from history, kept current

**Bootstrap**, at setup or from "Generate from history":

1. **Read N months of mail in both directions.** The default is 6 (an open question), through the same brain and connections as today.
   **Sent mail and threads Alex started weigh most**, because they show what Alex does rather than what lands on Alex.
2. **Cluster without a model.** Build a graph of who Alex writes to together, in which thread, mailbox, chat group, repository and
   domain. Its dense groups are the candidate workstreams. This step is cheap and deterministic, and it catches sister companies that
   share one domain.
3. **Name each cluster with the model.** For each cluster the model reads a sample of Alex's own sent words in it, then writes the
   section: what it is, the role, the people, the season and the cadences.
4. **Write the result into JOB.md's markers** for Alex to correct in Docs, or confirm it on one screen (an open question).

**Keeping current:**

- **Weekly:** each active workstream's section is refreshed from its last 14 days: new people, this season's goals, and finished goals
  dropped.
- **On events:** a person Alex has written to twice in a stream is added to it. A stream with no activity from Alex for 60 days goes
  **quiet**: its index line stays and its section leaves the readers' prompts until it wakes.
- **Season goals carry an end date** and expire unless activity confirms them.

### 5.3 Who reads what (the layer rules, made per-workstream)

The order is unchanged: SOUL.md + JOB.md, then AGENT.md, then the profile. Strangers' tasks get none of it.

| reader | gets |
|---|---|
| triage | SOUL, **the JOB index plus every active section**, and the whole LEARNED.md (ruled). It reads every line's workstream tag. Its verdict now names the workstream |
| event Advisor (the lit button) | SOUL's priorities, **the whole section for the item's workstream** (not the first 600 chars of everything), LEARNED lines tagged with that workstream or untagged, then the rest by budget |
| rail Advisor | the index, every active section, all of LEARNED (budget raised from 2,000 chars), and one calendar across workstreams |
| agents | SOUL, **the task's workstream section**, AGENT.md, the profile; LEARNED on demand. Strangers: none |
| drafter | STYLE plus the norms of the reply's workstream (a group chat is not an email) |
| Assistant | everything |

**Calibrated silence: rules stop guessing.** A rule may light a button only where that button's own measured precision, in that
state and that workstream on this owner's record, is at least 80%. Below that, the rule hands the item to the model, which reads the
workstream and the memory, or lights nothing. Each verdict comes from counting the owner's own presses, never from matching words, so
it respects "no hardcoded words" and the rev-2 ruling "when unsure, nothing is lit." On this home it would have silenced Continue on
stopped investigations (23% today) and Reply on asks the owner settles in person (0%) within days.

### 5.4 What makes an idea killer

**Idea kinds worth raising.** Every one had real hits in the graded set or in the misses.

| kind | the shape (invented) |
|---|---|
| promise unkept | "You told Ray on Tuesday you'd send the accrual file by Thursday. Nothing has gone to him." |
| ball dropped on you | "Paula asked at 9:10. The draft has sat unsent for 8 hours, and you usually answer her within 2." |
| second ask buried | "Erin asked two things. The draft answers the first only." |
| pattern across threads | "Omar and Marcus both report the export button greyed today. The task closed yesterday as 'can't reproduce' may not hold." |
| one thread decides another | "Gail's answer about seat counts settles the open question on the Trainly renewal." |
| cross-workstream clash | "The Ledger app demo you promised Omar for Thursday 2pm overlaps the Northwind board prep. One has to move." |
| waiting too long on others | "Ray owes the payroll file. He is 3 days past his usual." |
| meeting prep | "Tomorrow's 10:00 has Paula and Erin. Each has an open ask on your list." |
| agent drifting | "The agent on the portal fix has run 40 minutes. The ask changed in the thread at 11:02, after it started." |

**Not ideas.** Restating one row a report already shows. Anything about work Alex touched in the last day. Anything from Personal. A
kind Alex has said no to (learned into "What to bring up").

**The precision bar.** An idea is raised only when all four hold:

- it cites concrete evidence (message or task ids)
- it says what is new since Alex last looked
- it passes a second model check that reads the workstream section: **"would Alex already know this?"**
- its kind's measured precision for this owner, over the last 30 graded ideas of that kind, is at least 80%

A kind that falls below 80% goes quiet and is retried on the replay eval, not on Alex. The target is **useful at 80% or more, obvious
at 10% or less, and wrong or creepy at 5% or less**.

Grading uses only Alex's own acts:

- **useful:** taken up, turned into a task, or a reply sent within a day on the item it names
- **wrong:** dismissed, or "Wrong here"
- **obvious:** walked past

No new button is needed.

### 5.5 Memory hygiene

- **What is saved**, only lines that teach something about the owner:
  - a person's role in a workstream
  - a habit with 3 or more episodes from 2 or more people or threads (as today), now tagged with its workstream
  - a promise, until it is kept
  - a season goal, with its end date
  - a bring-up preference
- **What is not saved.** A one-off "filed this subject" is a verdict, and the verdict table already keeps it as triage evidence. The
  rewrite folds repeats into one general line, and a one-off that never repeats expires after 30 days. Lines never quote a subject or
  body that names a third party; they keep the role and the habit only.
- **When it is saved:**
  - per correction (the fast path, unchanged)
  - a nightly rewrite **per active workstream**, so one busy stream can't crowd out the rest
  - a weekly JOB refresh
- **How it stays small.** Caps apply per section **per workstream** (15 lines in use), inside a document budget of about 12k. Anything
  over the cap goes back to Watching.
- **How lines expire.** Every machine line carries a valid-until date:
  - habits: 90 days after they were last seen
  - season goals: their end date
  - promises: when kept, or 14 days after they were due, at which point the unkept promise becomes an idea instead of memory
  - people's roles: never on their own; they go quiet with their workstream
- **How it is corrected.** Keep / Wrong / Forget are unchanged. A line or idea in the wrong workstream needs a way to say so (an open
  question). **Pause learning in Settings is restored as ruled on 2026-10-23.**
- **Proposed rules** stop waiting silently. The open question is whether the Advisor may bring up the strongest one once, in its own
  section.

### 5.6 Privacy

- **Personal is a workstream that is never learned from.** Its messages are sorted by triage, which has to read a message to sort it.
  Nothing from Personal reaches LEARNED, JOB, the idea rail, an agent or the Advisor's prompts. Personal is detected by:
  - the mailbox flag (as today)
  - a chat or person Alex marks personal
  - the bootstrap's proposal, once Alex confirms it
- **Nothing leaves the machine** except calls to the AI Alex chose. The bootstrap, the clustering and the evals run locally against
  the local database. No new service is involved.
- **Third parties are not memorised.** A resident's, patient's or customer's name in a subject is never copied into a memory line.
- **Evals on real data** run on a copy and write their findings only to a scratch folder, never to the repository.

## 6. The eval plan

| eval | what it proves | today | target |
|---|---|---|---|
| `advisor_agreement --replay` (offline, no model), with the artefacts fixed and per-workstream and per-cause columns | the lit button | 44% agreement, 44% precision | **at least 80% precision on what is lit**; silence allowed |
| dropped balls, split into "agent stopped unflagged" and "owner steering" | the real misses | 14 (about 6 real) | at most 2 real a week |
| idea grader (new, offline, from the idea table and Alex's acts) | idea precision by kind | 59% (hand-graded) | **at least 80% useful, at most 10% obvious** |
| live lit-button A/B, with a multi-workstream world added | memory and workstream change the answer | filled 25/28, 0 worse | filled at least 90% right, 0 worse, the empty arm wrong on every workstream case |
| live rail A/B, with cases only memory can win | the rail uses the memory | empty = filled | filled beats empty by 3 or more cases; 0 noise |
| workstream mapping (on a copy, against 50 hand-labelled messages, results kept private) | the mapping is right | none | at least 90% |
| privacy invariant (in the suite) | Personal never reaches a line, an idea or a prompt | none | 0 |

The **invented multi-workstream world** for the tests: Alex runs Northwind finance systems by day, the Ledger app with Omar and Marcus
in a chat group, and has personal chats. In its cases the right button or idea differs by workstream:

- a tester's bug report: hand it to an agent, don't reply
- a friend's "come over at 1:30": no task, nothing learned
- the manager's ask: reply the same day
- a clash between a Ledger demo and a Northwind deadline: raise it

## 7. The slices

Each slice lands on its own tests and is measured with the replay before the next one starts.

| # | slice | lands on |
|---|---|---|
| S0 | **Measure honestly.** Fix the agreement artefacts (twins, a light one press behind, sent scored as a reply), split the dropped balls, add an idea grader and a cause column | unit tests on fixture rows (Northwind) |
| S1 | **Calibrated silence.** A rule lights a button only where that button's measured precision is at least 80%; otherwise it hands to the model or stays silent | replay on a fixture home: rule Continue and Reply on low-precision states go quiet |
| S2 | **Workstream on everything.** The JOB.md index and markers, a `Workstream` on message, task, idea and memory line, the mapping order, and triage's verdict naming it | a multi-workstream fixture world; mapping tests |
| S3 | **Personal is never learned.** Detection, plus the exclusion checked at every reader | the privacy-invariant test |
| S4 | **Readers by layer.** The Advisor gets the item's section whole, agents get their workstream, triage gets the index; the 600-char cuts go | prompt-capture tests (as in `test_advisor_memory_live` plumbing) |
| S5 | **Memory hygiene.** People roles per workstream, Promises filled from sent words, Bring-up filled from idea decisions, one-offs expire, no system senders, valid-until dates, per-workstream caps, Pause learning restored | reflection tests with a scripted brain |
| S6 | **Bootstrap from history.** Clustering, naming and JOB sections, then the weekly refresh and quiet streams | the clustering is deterministic on a fixture mailbox; naming uses a scripted brain |
| S7 | **Killer idea kinds.** Cross-thread patterns, a buried second ask, one thread deciding another, cross-workstream clashes, an agent drifting; the "would Alex already know" check; per-kind calibrated quiet; single-row restatements dropped | `rail_advisor_cases` worlds per kind, with noise held to zero |
| S8 | **Yardsticks.** Multi-workstream worlds in both live A/Bs, and the idea grader's line added to the release line | the live scripts, run on a copy |

The proposed order is S0, S1, S2, S3, S4, S5, S6, S7, S8. S1 alone should lift lit precision visibly within a week of presses.

## 8. Open questions for the owner

These decide what Alex sees or how Alex interacts, so none is assumed.

1. **Where workstreams live.** Sections inside JOB.md, which keeps one Docs page, or one document per workstream? *Proposed: sections.*
2. **Confirming the bootstrap.** After "Generate from history", should there be a one-screen "Here's what I think you work on" to
   rename, merge, split or mark personal? Or should it write into JOB.md and let Docs be the place to correct it?
3. **How far back** the bootstrap reads: 3, 6 or 12 months? *Proposed: 6.*
4. **"Wrong workstream" as a correction.** Should it be a new choice beside Wrong here / Forget, a pick-list inside Wrong here, or only
   an edit in JOB.md?
5. **Labelling ideas.** Should an Advisor idea show its workstream with a small label in the Advisor section?
6. **Personal asks.** "Pick up the car at 5" from family: a task that is never learned from, only an FYI, or nothing? Today these become
   tasks, and the owner closes them.
7. **Proposed rules.** May the Advisor bring the strongest waiting rule up once, in its own section, with Adopt or No? Some have
   waited weeks on strong evidence.
8. **Clashes.** May the Advisor read every calendar, personal included, to find clashes, saying only "a personal commitment" for the
   personal side?
9. **Falling coverage.** Calibrated silence lights fewer buttons at first. Is that acceptable until precision reaches 80%?
10. **Writing style.** Should STYLE.md get lines per workstream, since a team chat and a vendor email read differently?
11. **Pause learning.** It was ruled on 2026-10-23 and is missing from the code. Restore it in Settings as ruled? *(A confirmation, not a
    new decision.)*

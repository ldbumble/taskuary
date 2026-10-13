The Advisor is the one of Taskuary's three models that thinks about your work as a whole. Triage
judges each arrival and the assistant moves things on a turn; the Advisor reads everything, on a
clock, and says what should happen next: what is late, what nobody followed up, which step a mail
served, what worked, which system is worth connecting. It never acts. It leaves a line, an idea
row or a proposal, and you or the assistant do the rest. `COUNSEL.md` is its voice and the
assistant's both.

The operational side - the report that runs it, its schedule, the five words under an idea - is on
[Reports and the Advisor](reports#the-advisor). This page is what goes into it, and what it learns
from.

## What it reads

What one run of the Advisor report hands the model, today:

| Input | What it tells the Advisor |
|---|---|
| `SOUL.md` and `JOB.md`, the head of each | Who you are and what matters: it weighs a slipped thread by whom it serves, and never contradicts the constitution. The chat reads both whole; the report takes the opening of each |
| `COUNSEL.md` | How it speaks and how readily it takes a position |
| Your work as the hub sees it | The threads of the last two days with your own lines marked, what arrived, the open tasks and what closed this week, who is out of office from their auto-replies |
| The calendar | Who you meet and when: context for a meeting, and a chase that should wait for the one on Thursday |
| The knowledge base | What agents have learned, by name, so it does not raise what is already known |
| The sources it watches | The systems and saved data views on its report card, pulled silently each run |
| Its own notes | What it reviewed last time and what you put down, so it never raises the same silence twice |
| `LEARNED.md`'s promoted lines | What your own verdicts taught, with their counts - the habits it weighs, never restates as news |
| The outcome ledger | The last month of what came of actions, each with an id to cite, and the ledger's page on each person the run names |

Two more inputs reach the Advisor at **reflection**, the pass that rewrites `LEARNED.md`, rather
than on a report run: `LEARNED.md` itself, whole, hypotheses included, and the outcome ledger
below. The playbooks and your mutes are designed as inputs and not yet read.

None of this is copied into a prompt you cannot see. The report's **Preview** shows exactly what one
run hands the model.

## Two clocks

**On the clock, today.** The Advisor report runs on its schedule and when the app opens; the
morning brief runs daily; reflection runs at launch and after three corrections, and reads the
ledger whenever it runs. These find
what only a window shows: a promise gone quiet, a task nobody touched, a goal with no movement,
a sender you keep hearing from through a system you have not connected. Their findings are rows,
judged like any arrival, because a forgotten task is work waiting on you and belongs on the rail
where **Next** reads it in turn. Nothing fires for absence; something has to look.

**On the event.** The same brain also runs when one item changes: an agent stops or asks (or was cut
off by Taskuary closing, which the next launch reports), a reply arrives on a watched thread, a mail is attached to a task, a pull request opens, a task closes, a
due day is missed, a report lands. One small prompt on the light model reads the event, the item's
facts, the verbs the item carries, the promoted lines of `LEARNED.md` and the ledger rows that bear
on it, and answers with one verb from the actions the app already has and one line, or nothing.
Code checks the verb is one the item offers; a verb it does not is dropped and noted. Those
findings are never rows. They attach to the item at its revision and show when the walk reaches
it, as ghost text in the prompt box with one pill where the send arrow sits: "Continue session ·
8 of 8 times". The number is read from the outcome ledger, never written by the model. The pill is
the card's own button through the same proposal and the same receipt; typing anything brings the
arrow back. A changed item drops its old line by one comparison. The item on the table earns one
bigger read, with what the hub knows about the people on it and the month's outcomes. The rail's
order does not read advice, by construction: the test that pins it builds the rail with and
without advice and asks for the same order. Two settings govern it, in Settings → Advisor: the
switch, and a cap on judgements per hour.

**Seeing what it did.** The clock menu on the stage opens the Advisor's notes for the item on the
table: a receipt, not a transcript. Each entry says the event, what it decided (the pill and the
line) or what it dropped and why (nothing to say, a verb the item did not carry, the hour's cap,
no brain), and the evidence it cited by id - what it cited, not everything it read. "Why?" in the chat is answered from the same line.

## What was not followed up

A thread you wrote on that nobody answered, or a step somebody owes past its day, is **slipped**
once it has been quiet past that person's usual day: half again their median answer, once the
ledger has seen them answer three times, and the default from Settings → Advisor until then.
Someone whose auto-reply says they are away never slips. A slipped row sits inside **On you**, the
pipe count says "3 slipped", and when Next brings it up the card offers four answers, each an
outcome the ledger keeps:

- **Chase them** drafts a short nudge on the thread, in your voice, for your yes - copying whoever
  the ledger has seen get them to answer, when it has. When it goes out, the reply is marked a chase,
  and how long the answer took is counted against them.
- **Let it go** puts it down: the step is dropped, or the follow-up closed. Three Let-it-gos on one
  person and the Advisor stops raising that person; nothing else changes.
- **They answered elsewhere** closes the step as done (its box ticks) and keeps where, in your words.
- **Remind me** is the same Remind me as everywhere else.

A reply arriving ends it on its own: the follow-up closes and the step leaves the lane. The morning
brief carries the same facts, one line each, with the person's day named.

## A page per person

Facts about other people go to a page per person, derived from the ledger at reflection and kept
under **Settings → Docs → People** by address: how fast they answer, whether a chase is needed, who
on copy moves them, what they deliver late - each line with the evidence ids it rests on, and the
counted numbers underneath. The lines are the model's reading; the numbers are the ledger's. Your
own lines above the block are yours and survive every recompile. The page is read wherever the hub's
dossier is read: the reply drafter, triage's context, meeting prep, and the Advisor's bigger read.

Facts about kinds of work go to the playbook they belong to, as a proposal: once a playbook has
five closes on the ledger, reflection writes a bullet block - how often a close came open again,
and how often the ones closed with a question still open did - and it waits for your yes on the
Review queue. Nothing edits a playbook on its own; your own lines on it are never touched.

## The outcome ledger

Every store Taskuary keeps is written from one signal: your click or your sentence, at the moment
you give it. `LEARNED.md` is what you do when you correct; the verdict and routing memories stop at
the verdict. Nothing recorded what you did next, or what the world did after Taskuary acted. That
is what the ledger records: one row per action the app took or proposed, filled in two halves.

| The action, recorded when it happens | What the sweep looks for | Verdict |
|---|---|---|
| A reply sent (approved as drafted, or edited first) | More material mail from them on the thread in a week. An auto-reply and a calendar response are not rounds; your own later mail is not theirs | settled · unsettled: N more |
| A task closed, by any road | Is it still closed a week on | held · reopened |
| An agent stopped (with or without a pull request open) | Your next move: a continue, with the words you typed into the pane or the session, or a close; or nothing in two days | continued · closed · left |
| A pull request merged | Two weeks on, nothing says otherwise | held |
| A promise you made in a sent mail, as a task on you with its day | Delivered when, against the day you named; or a week past it with nothing | kept · kept late · late |
| A sender ignored by a rule | Whether their mail became a task anyway in sixty days | no regret · regret |

Two things keep it honest. A stop is one row per stretch of waiting, not one per turn, and it
closes the moment you type into the pane: that is your next move, in your words. And resolving a
row is bookkeeping, not judgment: did mail arrive, did the task reopen, did the person deliver and
when are facts already in the store, and the once-a-day sweep reads them without a model. What the
facts mean is always the model's, at reflection.

**Reflection distils it into the stores that exist.** The resolved rows reach reflection as
evidence lines with their own ids, `out` beside the `mem`, `rv` and `task` ids a learned line
already cites. Habits about you go to `LEARNED.md` with the same grammar, the same strength, the
same decay: "green PR from the coder: you merge it, 8 of 8"; "the agent asks 'open the PR?': you
always say yes". A habit carries the one number it never had, the regret count. Facts about other
people ("Ray answers in three days and needs a second chase") and about kinds of work ("closing
from a thread with an open question reopens 40%; ask first") go elsewhere: a page per person
derived from the ledger, and work facts proposed into the playbook they belong to (both below).

## The one rule

A derived line never acts on its own. It changes which button comes first, what a proposal says,
what triage weighs, which day a chase goes out. Autonomy stays a proposal you click. "Stop
offering" on any line writes the opposite evidence, and deleting the line from `LEARNED.md` is the
whole undo. Earned autonomy - the Advisor proposing to do itself what you have done the same way
every time, revocable from the same line - is shaped for but not built; every piece here is made
so it needs nothing new.

## What is built, and what is next

Built - all five steps of the design: goals as tasks (a task whose boxes are tasks, a person as an
assignee, a promise as a task on you with its day, one row per goal on the rail); the outcome
ledger with its daily sweep and reflection reading it; the Advisor on the event, with the
prompt-box pill and the notes in the clock menu; a page per person and a per-person day, with the
slipped lane and its four answers; and triage naming which goal step a mail serves (the mail lands
under that step, and may tick a box nobody holds), opening a goal for the open-ended ask with the
planner proposing its steps, and work facts proposed into playbooks.
Next, kept in mind but not built: earned autonomy.

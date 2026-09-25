Taskuary's whole behaviour is one loop: something arrives, it gets a verdict, the verdict decides
who does the work, and whatever comes out waits for you. This page follows one message the whole
way, then explains the machinery underneath it.

## The Timeline

The Timeline is the front door: every connection with a *trigger* or *feed* role lands here, in
the order things happened. An email from a vendor, a pull request, a Teams message, this
morning's spend report and a failed nightly export are one list.

Each row shows where it came from above its original time, so mail, chat, GitHub, a SQL report
and an Advisor post are told apart at a glance. Calendar entries show the meeting time. Open a
row for the full message, its attachments, what triage decided and why, any drafted reply, and
the actions available on it.

Beside the Timeline, the **work rail** holds what is actually waiting on you, in lanes — unread,
needs an answer, an agent is waving, stopped, later. A finished or closed item gets no row: the
rail is what still wants something from you, never a history.

## The five roads a message can take

Every message gets exactly one verdict, and there are only five places it can go.

| Road | What it means | What happens |
|---|---|---|
| **fyi** | nothing to do | filed; it stays readable and nothing is created |
| **reply** | a sentence settles it | a draft goes to the task for you to approve |
| **coding** | an agent at a keyboard | a CLI session starts in the checkout it picks |
| **general** | worth thinking about | a conversation opens on the task; no system is touched |
| **task** | yours to do | it lands on your list and nothing works it |

Three of those — `coding`, `general`, `task` — are *kinds* stored on the task, and the kind is
what routes the work. `reply` is a kind too. `fyi` creates nothing at all.

Only `coding` is ever dispatched automatically. A conversation you did not ask for is noise, and
a `task` is yours by definition, so both land on the Board and wait for your click.

:::note What "general" means
It means the assistant's conversation: there is nothing to type at a system, but thinking,
reading or research would help — weigh an option, make sense of a thread, work out what to ask.
Work a person genuinely has to do in the world (sit a course, sign a form, attend, decide) is the
`task` road instead.
:::

## What triage actually decides

The verdict is the *last* thing that happens, not the first. Eleven checks run in a fixed order,
and only two of them ask a model anything. A **gate** is deterministic: same input, same answer,
no AI call, no cost. Knowing which is which is how you tell "triage got this wrong" from "a rule
caught it before triage ever saw it".

| # | Step | Gate or AI | What it does |
|---|---|---|---|
| 1 | Dedupe | gate | A message whose id is already stored is dropped. Nothing below runs. |
| 2 | Feed connections | gate | A connection marked *feed* lands on the Timeline and stops — no verdict, no AI call, no task. |
| 3 | Policy rules | gate | Your rules, plus whether the sender is known. `skip` and `ignore` end it here. |
| 4 | Deferral | gate | Deferred triage lands the message as `triaging` so the Timeline shows it at once; the rest runs later. |
| 5 | Chat opener | gate | "hi", "you there?" — filed to wait for the ask it opens, so a greeting never becomes a task. |
| 6 | Threading | gate (scored) | Similarity against open tasks picks *attach* or *create*; then a thread that is not yours is refused. |
| 7 | Still the same ask? | **AI** | Chats only, and only when step 6 attached: does this line continue that task or start a new one? |
| 8 | Your standing ruling | gate | If you already ruled on this conversation it is filed, quoting your own words. Your rulings outrank the classifier. |
| 9 | An agent is waiting | gate | If a run is live on the attached task, no verdict is asked for — the message goes to the agent as its answer. |
| 10 | The verdict | gate, then **AI** | Tracker items, obvious noise and calendar invites settle with no call. Everything else is one call reading `TRIAGE.md`, `SOUL.md`, `LEARNED.md` and your past verdicts. |
| 11 | Acting on it | gate | `fyi` files. A reply files instead of drafting when replies are off for that channel. Anything else becomes a task with its kind. |

Two rules hold wherever AI is involved. With no AI connector, a message is **filed** with
"awaiting AI triage" rather than guessed at. A call that fails, or answers something unreadable,
is filed too — never assumed to be work. Triage breaking is quiet and safe, not destructive.

So a message that never reached the classifier was stopped by steps 1–6 or 8–9, and the fix is a
rule, a feed or a ruling. A message the classifier *did* judge and got wrong is corrected on the
Triage tab.

## Nothing sends itself

Review is the outbound decision queue, and it is the only road out. A drafted reply sits there
with the original request beside it; you edit the wording or the recipients, then **Approve &
send** returns it through the channel the conversation started on. You can also ask for a
redraft, reject it, or decide no reply is needed.

The same gate covers more than mail: a GitHub comment, an invoice, a bill posted to your finance
system and a file written to a share are all proposals until you approve them. A connector card
ships at a read-only authority, and raising it is a deliberate act.

:::rule One way to finish
A task ends with **Mark done** — on the task page, on the Assistant's card, or by saying "done" in
the chat. Sending the reply marks it done too, unless an agent is still working on it or a new
message arrived meanwhile. An agent that says it is finished closes its own task, and that result
stays on your work rail until you have read it. See [Tasks and agents](tasks-and-agents#who-is-allowed-to-close-it).
:::

## Correcting it teaches it

The roads on the Triage tab are not decoration. Correcting a verdict writes the reason into
`TRIAGE.md`, the document the classifier reads on the next message — so the correction applies to
the next message *like* this one, rather than becoming a rule about this one sender.

Every verdict is evidence. Editing a draft teaches voice; rejecting one teaches what should not
be drafted; **Not our task** teaches where your responsibility ends. The exact decision is kept
with its date, sender and subject, so future triage can judge whether a new message is genuinely
similar.

Repeated patterns become lessons in `LEARNED.md`. Each machine-written line carries its evidence:

```text
- John drops greetings and signs off in one word. [s:4 | ev: rv12,rv15,rv31 | seen: 2026-08-19]
```

- `s` is strength. A hypothesis starts at 2 and is promoted at 4 or more, supported by at least
  three episodes across two people or threads. Contradictions weaken it; stale hypotheses decay.
- `ev` names the verdicts that taught it, so you can go and read them.
- `seen` is the last date on which it held.

Delete a learned line and it is gone. Lines you write yourself carry no machine tag and are never
rewritten. An inferred rule that would *hide* work waits in Proposed rules until you adopt it.
`SOUL.md` always outranks `LEARNED.md`, and one setting switches the whole loop off.

## The documents that govern it

Taskuary's behaviour is plain Markdown on the **Docs** tab. These are not configuration files
around the edges — they are what the models are actually told.

| Document | Purpose | Read by |
|---|---|---|
| `SOUL.md` | The constitution: rules, voice, escalation lines, repository map | triage, replies, coding agents |
| `TRIAGE.md` | What makes something a task, a reply or an FYI | triage |
| `STYLE.md` | Greeting, tone, length, phrasing | reply drafts |
| `COUNSEL.md` | How the assistant speaks, and how readily it takes a position | the assistant, the morning brief, replies |
| `CODER.md` | How coding agents work and close out | coding agents |
| `LEARNED.md` | The profile learned from your verdicts; always below `SOUL.md` | triage, replies, coding agents |
| `DIGEST.md` | The current morning brief | you |
| Playbooks | One page per kind of job: when it starts, which connections it uses, the steps, what an agent may do alone, what counts as done | triage's `when` line, and the agent working it |

Playbooks are the ones that grow. `CODER.md` is the playbook for code; every other kind of job —
a card charge to post as a bill, a new hire to set up — gets its own page the first time an agent
does it. On close, Taskuary asks whether that was a kind of job that will recur, and drafts the
playbook onto the task.

**Generate from history** on `TRIAGE.md` and `STYLE.md` bootstraps all of this from your last
three months of mail: it compares what arrived with what you actually answered, and writes the
result into a marked block, leaving anything you wrote outside that block alone.

## Where the rest of the workspace fits

- **Board** — queued, working, waiting and completed agent tasks, with a live terminal and the
  files changed so far on the working cards.
- **Studio** — agent capacity as a floor: one desk per slot, occupied when a task is running, a
  raised hand when a session needs you.
- **Wall** — every live terminal side by side, each with its own prompt box.
- **Tasks** — the durable task, its agent sessions and the reply, as three separate records.
- **Review** — the outbound queue.
- **Reports** — connected data on a schedule; see [Reports and the Advisor](reports).
- **Hub** — what agents have learned, by topic, so knowledge survives past one job.
- **Docs** — the documents above.
- **Settings** — everything else; see the [Settings reference](settings).

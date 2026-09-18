Most things that go wrong in Taskuary go wrong quietly and safely — a message gets filed instead
of guessed at, a run reports its error in place instead of taking the report down. That is by
design, and it means the answer to "why did nothing happen?" is usually written down somewhere.
This page is where to look, in the order worth looking.

## It will not start

**Nothing opens.** Taskuary serves `http://127.0.0.1:7787`. If the browser shows nothing, check
whether the process is running and, more usefully, what is actually listening:

```bash
# Windows
netstat -ano | findstr :7787
# macOS / Linux
lsof -i :7787
```

More than one Taskuary can run against the same database, and their command lines look alike. The
listening port is the only reliable way to tell which one is serving you — a second instance on
another port will happily keep polling and triaging with older code.

**The port is taken.** Set `TASKUARY_PORT` to something else, or stop whatever holds it.

**It started and immediately closed.** Read `~/.taskuary/taskuary.log`; the last lines before the
exit are the reason. A corrupt `config.toml` is the common one — rename it and Taskuary writes a
fresh default.

## A connection stopped

A connector card shows its own last poll and its last error, and that is the first place to look.

| Symptom | Usual cause |
|---|---|
| Nothing new since a fixed time | The sign-in expired. Reconnect on the card |
| "could not read your channels" | The app is older than the page expects — restart it |
| Mail arrives but no replies go out | Replies are off for that channel, or the card has no send authority |
| A tracker connected but silent | Nothing is assigned to the connected user — that is what it reads |
| WhatsApp went quiet | The bridge lost its session. Re-pair it; the unofficial protocol does this periodically |

If the card looks healthy and items still are not appearing, check the card's **roles**. A
connection with no `trigger` or `feed` role is never polled, which looks exactly like a broken
connection from the Timeline.

## Triage got it wrong

First, work out whether triage ever saw it. Open the row: it says what decided the outcome and
why. [What triage actually decides](how-it-works#what-triage-actually-decides) lists the eleven
steps and which of them are deterministic gates.

- **Stopped by a gate** (a feed connection, a policy rule, your own standing ruling, an agent
  already waiting) — the fix is that rule, that role or that ruling. The classifier was never
  asked.
- **Judged and wrong** — correct it on the Triage tab. The correction is written into `TRIAGE.md`
  and applies to the next message *like* this one.
- **"Awaiting AI triage"** — there is no AI connector active, so nothing was guessed. Add a key,
  and the retry sweep picks it up.
- **"Triage failed"** — the call failed or returned something unreadable. It was filed rather
  than assumed to be work; the row keeps the error.

:::note A verdict you disagree with is not a bug
Triage is supposed to be argued with. The correction loop exists because the right general rule
is rarely knowable from one message — and a correction teaches the class, not the sender.
:::

## An agent is stuck

**It is waiting on you.** A raised hand on the Studio floor, a waving badge on the Board, or a
`stopped` lane row in the work rail all mean the same thing: the session asked something. Open
the task and answer it.

**It is waiting on its CLI.** A headless agent without its noninteractive flag hangs forever on a
prompt that cannot be answered. The connector presets set the flag; a custom CLI needs it added.
The card's **Test** action reproduces it in ten seconds.

**It hit a limit.** The saved result says so. **Start new coding session** picks a different
harness and keeps the checkout and the history.

**It is gone.** If the process died, the row moves to the `stopped` lane and is forced unread, so
it comes back to you rather than disappearing. Only **Later** holds it.

**Stop session** ends the process and deliberately changes nothing else — not the task state, not
the reply. If you want the task closed, **Mark task done** does both.

## A report returned nothing

Open the report row: the last run shows what it read, what came out, and the error if it failed.

- **One source failed** — it is reported in place and the rest of the pipeline still ran.
- **Fewer rows than you expected** — check **max rows**. Blank means 200, which is a cap nobody
  chose, and a capped run says so in its headline.
- **The prose does not match the numbers** — **Test — show me the data** on the source card
  returns the exact text the prompt was handed. That is almost always where the surprise is.
- **It never ran** — a slot missed while the app was closed fires once on reopen, not once per
  missed slot. **Run due now** forces everything owed.

## Reading the audit log

**Settings → Audit integrity** is the answer to "why did this happen" and "who did this". Every
consequential action is one row: routed, filed, replied, opened, saved, deleted — with the actor,
the time, and the thing it happened to.

**Verify** recomputes the hash chain from the first row and tells you whether the record has been
altered since it was written. "Out of order" is benign — two writers raced once. "Contents
altered" is not, and it names the rows.

## Where the logs are

| Thing | Where |
|---|---|
| Application log | `~/.taskuary/taskuary.log` |
| The database | `~/.taskuary/taskuary.db` |
| Configuration | `~/.taskuary/config.toml` |
| A coding session's full transcript | the task page → **Work details → Full artifact** |
| The context an agent was handed | `~/.taskuary/context/` |
| Playbooks | `~/.taskuary/playbooks/*.md` |

Under Docker, all of it is `/data` inside the container. `TASKUARY_HOME` moves it anywhere.

## Still wrong

- The live API reference at `/api/docs` shows exactly what the app exposes, and is the fastest way
  to check whether a thing you expect is actually there.
- Issues: [github.com/ldbumble/taskuary/issues](https://github.com/ldbumble/taskuary/issues).
- Security problems go through [SECURITY.md](https://github.com/ldbumble/taskuary/blob/master/SECURITY.md),
  not a public issue.

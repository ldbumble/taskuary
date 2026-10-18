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

**The port is taken.** If another Taskuary owns the port, the CLI opens that instance. If a
different process owns it, the CLI automatically selects a free port and prints the new address.
Use `taskuary --port PORT` or set `TASKUARY_PORT` when you need a specific port instead.

**It started and immediately closed.** A corrupt `config.toml` is the common cause, and it fails
before Taskuary can write the useful error to `taskuary.log`. If you started Taskuary from pip,
read the traceback in the terminal where you ran `taskuary`. If you started the desktop app, read
`~/.taskuary/desktop-error.log`. Rename a corrupt `config.toml` and Taskuary writes a fresh default.

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

## A reply has no confirmed delivery

Approval stays pending while Taskuary sends the reply. Repeated clicks do not start another
send. A sent reply never closes the task - that is **Mark done**, pressed when you are finished.

**Delivery unknown** means the provider timed out, the process stopped during sending, or a
receipt could not be verified. Check the provider's sent messages before taking any further
action. Approving again checks the original attempt; it does not resend just because a receipt
is missing. Providers that cannot verify the attempt leave it pending for you to investigate.

**Sending failed** means the attempt was rejected or blocked. Fix the connection or send
permission, then review and approve the draft again.

## An agent is stuck

**It is waiting on you.** A raised hand on the Studio floor, or a 👋 **agent waiting on you** row
on the Board or the work rail, all mean the same thing: the session asked something. Open the task
and answer it.

**It is waiting on its CLI.** A headless agent without its noninteractive flag hangs forever on a
prompt that cannot be answered. The connector presets set the flag; a custom CLI needs it added.
The card's **Test** action reproduces it in ten seconds.

**It hit a limit.** The saved result says so. **Start new coding session** picks a different
harness and keeps the checkout and the history.

**It says there is no local path for the repository.** Map that repository to its checkout on
the AI CLI agent card, or make the checkout discoverable. A task naming a repository cannot
fall back to an unrelated default working folder.

**It is gone.** If the process died, the row reads ⏹ **agent stopped** and is forced unread, so
it comes back to you rather than disappearing. Only **Later** holds it.

**Stop and save** ends the session, files what it did and drafts the reply for you to
approve; it leaves the task state alone and sends nothing. If you want the task closed, **Mark
done** does both.

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
| Desktop startup crash | `~/.taskuary/desktop-error.log` |
| The database | `~/.taskuary/taskuary.db` |
| Configuration | `~/.taskuary/config.toml` |
| A coding session's full transcript | the task page → the **Agent work** step → the session's **More → Every step** |
| A finished session's written result | `~/.taskuary/artifacts/` |
| The context an agent was handed | `~/.taskuary/context/` |
| Playbooks | `~/.taskuary/playbooks/*.md` |

Under Docker, all of it is `/data` inside the container. `TASKUARY_HOME` moves it anywhere.

## Report a bug

Every error the Assistant shows, and every failing item under the bell, has a small **Report this
bug** link. The Help icon in the top bar opens the same popup when nothing failed but something is
wrong.

The popup is already filled in: a title, two or three sentences on what happened, and a collapsed
**Technical details** section - where it happened, the error, the Taskuary version, your OS, which
kinds of AI and connections are on, and the log lines around the error. You can edit all of it.

- **Scrubbed before you see it.** Email addresses, names, task titles, message text, repository
  names, server names and paths under your user folder are replaced with `[removed]`. If the report
  cannot be made safe, the popup says so and offers only to copy the error.
- **A screenshot is off by default.** Tick it and the Taskuary window is captured with every word
  blurred; it goes on your clipboard to paste into the issue.
- **Send opens GitHub's new-issue page with everything filled in.** You press Submit there - no
  GitHub account is connected to Taskuary for this. If the report is too long for the link, the full
  text is on your clipboard to paste.

It goes to a public page: read it before you submit.

## Still wrong

- The live API reference at `/api/docs` shows exactly what the app exposes, and is the fastest way
  to check whether a thing you expect is actually there.
- Issues: [github.com/ldbumble/taskuary/issues](https://github.com/ldbumble/taskuary/issues).
- Security problems go through [SECURITY.md](https://github.com/ldbumble/taskuary/blob/master/SECURITY.md),
  not a public issue.

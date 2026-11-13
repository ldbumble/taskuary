The Assistant walks you through what is waiting: one item at a time, with a few buttons under it.
There are eight buttons in all. Anything without a button still works when you ask for it in your own
words, in the app or on your phone.

## One screen: the sidebar and the canvas

Taskuary is one screen. The **sidebar** on the left is your work rail; the **canvas** on the right is the conversation,
and whatever part of the app is in use opens inside it.

| Where | What is there |
|---|---|
| Top of the sidebar | **New** (a task, a report or a routine), then **Reports**, **Connections**, **Hub** and **Settings** |
| Under the buttons | **Search** (or Ctrl+K anywhere), then the **filter** - the row's one control, saying what the rail is narrowed to (*All items*, *Email*, one mailbox) - then the day's count and **Sync now** |
| Search | One box over everything, open or closed: tasks, mail, chats, pull requests and issues, Advisor posts, reports and your sources. Each result wears a pill saying what it is; the strip above them narrows to one kind (**Tab** steps through it). **Enter** opens the result - a task on the canvas, a message in full, a source as the rail's filter - and the task number on a message opens the task it is on |
| The rail | **Tasks** (every open task; a ring spins round the icon of one an agent is working), **For later**, **Reports**, **Advisor**, **FYI** - click a heading to walk that section |
| The canvas | The item on the table: a task opens as its full task view - Came from and Agent, the agent's one chat - with **Next** under it |
| The top bar | **Board** - every agent and its session, full screen - and back to the Assistant |

**Reports, Connections, Hub and Settings are browsed in the canvas**, by clicks: a button shows that part's sections, a
section shows its cards, and a card opens with its own controls - **Back** returns to the list. Ask the Assistant about
the card that is open ("why is this failing?", "turn this on") and it knows which one you mean.

An agent's session opens inside the task view, nearly the full height of the canvas; **Expand** gives it all of it. On a
phone the task view is the screen, and **Expand** takes the session full screen with a back arrow to the chat.

## The buttons on each card

![Which buttons each kind of card shows](img/assistant-buttons.svg "Next is on every card. Nothing else is offered unless that card can actually do it.")

| Button | Shown on | What it does | Runs |
|---|---|---|---|
| **Next** | every card | The row directly below on the rail comes up. A report, an idea or an FYI is read and leaves the rail; an open task stays under Tasks, in its place. **Back** is the row directly above, and reads nothing. **Walk me through my tasks** starts at the top | at once |
| **Mark done** | a draft reply, a finished agent, a task | The one close: the task is done, an unsent draft is retired, a live agent is stopped, and it leaves your rail | at once |
| **Send** | a draft reply, one of a task's emails, a question for the sender | Sends it, and only that: the task stays open - on the table with its receipt, Mark done or Next - until you **Mark done** | you confirm |
| **Send and close** | a draft reply on a task (in its chat) | Sends it, then closes the task - kept open, and said why, while an agent works on it or anything else on it waits on you. "Send it" brings up **Send**; "send it and close it" brings up **Send and close**. When the Advisor says to send a draft in a task's chat, it lights **Send and close**; on the phone it is the first choice under the draft, then **Send** | you confirm |
| **Approve and close** | a task's close-out with your reply (in its chat) | What **Approve** does, then the task closes - kept open while an agent works on it. The card puts it first; **Approve** folds into its **▾** when the line is tight | you confirm |
| **Approve** | an agent's proposal, a task's close-out (a pull request to merge, an issue to close) | Runs only that action - on GitHub merges the pull request or closes the issue and posts the reply as its comment. The task stays open until you **Mark done** | you confirm |
| **Reply** | a person's ask, a finished agent with no draft | Writes a draft reply. Nothing is sent | at once |
| **Make a task** | an ask, an fyi, an idea | A task on your own list. No agent starts | you confirm |
| **Send to agent** | an ask, an fyi, an idea, a meeting, a report | A task and an agent on it. The card asks which agent | you confirm |
| **Not for me** | a draft reply, a proposal (not a close-out), an ask, an fyi | Files it. The card asks how far | you confirm |
| **Send back to the agent** | a draft reply on a task (under More actions); a close-out GitHub refuses for merge conflicts (the main button) | Picks the task's own agent back up with your note - or, on a conflict, GitHub's reason - as the first thing it hears. The card comes back when it stops | at once |
| **Stop and save** | an agent waiting on you | Writes up what the session did and stops the agent. The task stays open | at once |
| **Remind me** | any card with an open task behind it | Asks for a day, then puts the task away until that morning: under For later on your rail, with its day. On the phone the days come as choices | you pick the day |
| **Watch it** | any card with an open task behind it | Somebody else is handling it: nothing is sent, the task stays open under Watching, still walked after Tasks, and goes back to Tasks when its thread moves or a quiet week passes | at once |

A handful of fyi comes as one card with its own **All read, next** button. A close-out card for a pull request also
shows **Decline** (close it without merging) - on the card only, never as a chat word or a phone choice - and no
separate Reject: the reply on it is edited or redrafted in place.

## The two buttons that ask one question

![Not for me asks how far; Send to agent asks which agent](img/assistant-questions.svg "The card asks; nothing runs until you confirm.")

| Button | Answer | What happens |
|---|---|---|
| **Not for me** | Just this once | This message is filed. Its task is deleted if nothing was done on it, otherwise marked done |
| | From now on | Triage learns to file everything from this sender. Their mail still arrives and stays readable |
| | A rule in Settings | An exclusion rule: their mail never reaches triage, and what already arrived leaves the rail. Reversible |
| **Send to agent** | A coding agent | A task and a coding agent in a repository. The card asks which repository when it is not clear |
| | A non-coding agent | A task and an agent for reading, checking, drafting or research |

Send to agent starts on the agent triage would pick; the other is one click away on the card.

## Pictures, and your voice

Paste a screenshot, drop an image, or use the paperclip - in the chat line, in **New**, in a task's chat box, and in **Continue**. It
goes with your words: the Assistant looks at the picture itself, and a coding agent is handed the file to open. PNG,
JPEG, GIF and WebP, up to eight at a time. The microphone beside each box dictates into it.

On a coding task, **Continue** opens as a card under the item, not a popup: type or say what to tell the agent as it picks up,
add a picture, or continue as is. Moving on with **Next** puts the card away with the item. A general task has no Continue: what you type in its chat box carries the same conversation on.

## Remind me

Every open task has **Remind me** on its page: tomorrow, next week, in 2 weeks, in a month, or any day
from the calendar. Until that day the task waits under **For later** on your rail, saying when it comes back. That
morning a note goes on the task and it is back under **Tasks**, however long ago it arrived. Ask the
Assistant the same thing — "bring TQ-0123 back in two weeks" — and it brings TQ-0123 up with **Remind me** lit; you pick the day.

Beside it, **Watch it** is for a task that is not yours to do but that you want to see through. Nothing is sent. The task stays
open under **Watching** at the foot of Tasks, and stays on the walk, which reaches it after Tasks. It goes back to Tasks when anybody else writes on it -
with **Mark done** lit when triage reads the new message as handled - or after a quiet week, with **Chase them** and **Let it go**.
Triage puts a task there by itself when it reads a thread as yours to care about and somebody else's to handle; its reason names who.
**Stop watching** on one of those puts it back in Tasks, and triage learns from it.

## Everything the task page can do

Anything you can do on a task's page, you can ask the Assistant for — about the task in front of you, or any
task you name (TQ-0123). It brings that task up with the button for it lit, and says to press it: nothing changes
on your words alone, and there is no card to confirm and nothing to take back - a wrong Mark done is put right with
**Reopen task**. Work - research, writing, code - goes to an agent, never into the chat: "start it", "send this to an
agent" or "have a coding agent fix this" presses **Send to agent** on the task in front of you, and a new job is written
up in **New** with its **Send to agent** pressed there. Anything that leaves the app - a reply, a Share - is still yours
to press. It never guesses which task you mean.

![What you can ask about a task, and what each does](img/assistant-task-tools.svg "One tool per action on the task page.")

| Say, about a task | The button it lights does |
|---|---|
| "make this urgent", "rename it", "I'll take it" | Priority, title or owner changed |
| "this is a general job, not coding" | What kind of work it is changes, and a live session is closed if it no longer fits |
| "this belongs in the ledger repo" | The task moves to that repository |
| "tick off the first item" | That checklist box is ticked — the last box is Mark done |
| "add a note that Erin wants it by Friday" | A note on the task |
| "forward it to Erin" | A hand-off is written for your yes — nothing is sent until you approve it |
| "ask the sender which date range they need" | The question is written for your yes |
| "start the coding agent on TQ-0123" | An agent starts on that task; it asks which repository when it is not clear |
| "continue the agent where it left off" | The agent's own last session picks up again |
| "stop the agent on TQ-0123" | Stop and save on that task's agent |
| "split this in two" / "it's the same job as TQ-0120" | Two tasks, or this one folded into the other |
| "this isn't a task" | Deleted, and triage learns it was not work |
| "it's done" / "reopen TQ-0123" | Mark done, or open again |
| "bring it back in two weeks" | Remind me — away until that morning |
| "send it" / "reject that draft" / "make it shorter" | The draft is sent, rejected, or written again |

## Words that work typed

These have no button. Say them, in the app or on your phone.

| Say | What happens | Runs |
|---|---|---|
| "reply and tell them…" | A draft with that gist in the item's reply box, and **Send** lit | at once - nothing is sent |
| "redraft it shorter" | The draft written again with the change | at once - nothing is sent |
| "yes, go ahead" to a waiting agent | Your answer goes to the agent | at once |
| "tell the agent to use the main branch" to an agent at work | Your next prompt, as **Tell the agent** takes it: typed in when it stops at its prompt, never mid-step | at once |
| "run it again" on a report | **Run it again** lit on the report | you press it |
| "remember that…", "I don't care about X any more" | Kept at once as a line in your memory (LEARNED.md), where triage, reports, the Advisor and agents read it | at once |
| "set up a report that…" | The report's page opens and the Assistant builds it there from your words | at once |
| "turn off sign every email" (over Settings) | The setting's group opens and its switch is turned off - a step in the chat | at once |
| "what's waiting on me?" | Looked up and answered — tasks, reports, mail, calendar, settings | at once |
| "what's in For later?" | The rail read by its own sections - Tasks, For later (with when each comes back), Reports, FYI | at once |

Later and Tomorrow are gone: **Next** is the "not now", and **Remind me** puts a task away until a day.

## It works on the page you ask it about

Ask the chat about what is on the canvas - a task, a connection's card, a report being set up, a settings
group, the Hub, the Board - and the page goes with your words: what is open, its boxes and what they hold, and its
buttons. Only then: a page nobody asked about is never read, and setting a card up by hand never brings the
Assistant in.

It works the page the way you would, through the page's own boxes and buttons, and each thing it does is a
step under its answer in the chat:

- **It fills boxes and presses buttons** - a task's title, a reply draft's words, a card's fields; Save,
  Test, Sync, Mark done, Remind me, a setting's switch. "Turn off sign every email" over Settings opens the
  setting's group and turns its switch off. On the Hub it searches, picks a topic, sorts, opens a post by its
  number, votes and removes; a comment it writes in is yours to **Post**, and "put this on the Hub" brings the
  Hub up with the words for its **Write one**. On the Board it switches Columns, Wall and Live handoffs.
- **It never sends.** A press that would send something out of the app - **Send**, **Approve**, an email, a
  chat message - is lit for you to press instead, whatever asked for it, the words on the page included.
- **It never sees a secret.** A password, a key or a token goes as "empty", "typed" or "saved", never its
  value, and it never types one: it tells you to paste it into its box. The server checks this again.
- **Your hand wins.** A click or a key on the page while it is working stops the rest.

**Set up with AI** - on a report, dashboard, routine or playbook, and on a connection's card - is the Assistant
building it right there on that page, with no chat window and no task: it drafts it, checks it (a report's
preview, a connection's **Test**), fixes what failed and tries again, and saves it. Its steps show on the page,
and so does the one question only you can answer, with a box to answer it. It never types a secret - you paste
it into its own box - and anything that sends something out still waits for your press. **let AI fill this in**
on a report's source card and **Fix with AI** on a routine's failed run open the chat window on that page.

While you are talking to it about a page, it notices what you do there - "I see you pasted the secret -
testing again" - once per change, and never while you are typing to it. With the window shut its answer
waits behind the pill's count; the window does not open by itself. The chat's **×** asks before it ends
the conversation about the page.

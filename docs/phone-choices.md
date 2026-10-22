# The phone's choices

The owner, 2026-09-25: the phone Assistant matches the desktop Assistant exactly; the only differences are
formatting that reads well in WhatsApp, and buttons to tap. On WhatsApp the choices arrive as a poll under
the message; on Telegram as the bot's own buttons under it (2026-09-29 - no poll needed there). A typed number
still answers on both, and only the newest message's choices run: a tap on an older one is answered, never run.

## What a pick does

A number, or a tap in the poll, is the desktop's button. It runs in code on the same road the button uses
(`concierge.propose_direct`, `run_proposal`, `surface`). The model never reads it. Only words the owner
types go to the model.

```mermaid
flowchart LR
  P{"What did the owner send?"}
  P -->|a number or a poll tap| A{"Which choice?"}
  P -->|their own words| M["The model reads them - same tools as the desktop"]
  A -->|Next| N["The desktop's Next - the next item, no summary reprinted"]
  A -->|an action word| D{"Does its card ask a question?"}
  D -->|no| R["Runs now - the receipt, then the next item if the table was settled"]
  D -->|Not ours| H["How far? - once / from now on / a rule in Settings / Cancel"]
  D -->|Send to agent| W["Which agent? - triage's pick / the other one / Cancel"]
  D -->|coding, checkout unclear| C["Which repository? - best guess first / Cancel"]
  H --> R
  W --> R
  C --> R
  A -->|Undo| U["The receipt's undo, run once"]
  A -->|Walk a section| S["Its first row - Next AND every act stay in that section until it is empty, then it says so"]
  A -->|Connections / Reports / Hub / Settings| B["A list - then a section or one entry - with Back; ten at a time with More when it would not fit a poll"]
  R -.->|a section is being walked| S
  A -->|More| O["The rest of the message, then the same choices"]
  R -.->|the receipt offered an undo| U
```

## The rules

| # | Rule | Why |
|---|---|---|
| 1 | A pick runs the desktop's action in code; the model reads only typed words | a pick used to go to the interpreter as words and could come back as a different verb |
| 2 | A card's own question is asked as numbered choices, and nothing runs until it is answered | the phone skipped "how far?" and ran Not ours as just-this-once, and guessed the agent and the checkout |
| 3 | The choice that was already the answer is the confirm; another answer runs at once | one tap, not a second "yes, go ahead" |
| 4 | A list answers one reply; after any reply its numbers are gone | a "2" typed three turns later fired a list nobody was looking at |
| 5 | A receipt that can be undone offers **Undo** as a choice | the undo existed only as the typed word |
| 6 | No typed word is a shortcut: "next", "undo", "set up" go to the model like any other words; the morning message's options are pills | a table of typed words ran the walk, set-up and undo with no model, and had to be kept in step with the vocabulary by hand |
| 7 | Phone approvals (typed "approve" / "reject" on a tagged ping) are gone; a draft is sent by its Close out pill (was "Send the reply") | a bare "yes" approved whichever review had pinged last, and the verdict words were a second vocabulary |
| 8 | On WhatsApp the choices also come as a poll on the last bubble (2 to 12 of them, each cut to 100 characters); only the newest poll in a chat counts | a poll is the one tappable thing WhatsApp lets an account send |
| 9 | A poll vote (the bridge marks it) is the choice it names; the same words typed are words | a poll vote arrives as the choice's own words, but only a tap is a pill |
| 10 | Walking a section, an act moves on inside it exactly as Next does; the section's end is said, then the walk goes on (2026-09-30) | Make a task on the first report put TQ-0001 up in the middle of Walk Reports |
| 11 | No list offers more than twelve choices: ten, then **More (N left)** / **From the top**, then Back (`doorway_browse.paged`) | the bridge cuts a poll at twelve without a word - five Connections sections and Back could not be tapped |
| 12 | Reports and Hub are browsed like Connections and Settings; the phone's morning menu holds the sidebar's four | the phone had no way to see a report's clock or read the Hub |
| 13 | The rail is read to the model by its SECTIONS (`pipe.list`), each row with its lane | grouped by lane, For later - a section, not a lane - was answered "nothing is parked in Later" |
| 14 | The walk's end offers **Walk me through my tasks** first; the new walk shows every open task again from the top (2026-10-22) | the end offered only its Opens, and outside a hand-off nothing started a new walk |
| 15 | Remind me's receipt carries no **Bring it back now** on the phone (2026-10-22) | the undo for one task rode under the next task's card |
| 16 | A card's first line says where it is in its section - "📋 on you · TQ-0004 · 4 of 19"; a section of one says nothing (2026-10-22) | a long walk gave no sense of how far it had come |
| 17 | An FYI - one or a batch - is passed with **Got it** (its read-and-next) and offers no Send to agent; one FYI opened leads with it (2026-10-22) | an FYI led with Put it on my list, and one tap sent a newsletter to an agent |
| 18 | A report card leads with **Next**, then More and Send to agent; Put it on my list is not offered on the phone (2026-10-22) | a report needs nothing, yet its first choice made it a to-do that then offered Reply |
| 19 | The day's opener offers about four picks: **Walk me through my tasks**, the two section walks the rail holds that walkers use most (Reports, FYI, then Ideas, For later), and **More…**, which holds everything else - Set up a report, the other section walks, Connections, Reports, Hub, Settings (2026-10-22) | nine options mixed the walk, section walks and browse areas, and read as the same thing twice |
| 20 | A stranger's held card offers no hand-off to an agent: it leads with **Trust them** (the task page's own vouch, `task.trust`) and **Not ours**; trusted, the card comes back with its ordinary choices and nothing has started (2026-10-22) | one tap started an agent on a new sender's branch |
| 21 | A failed agent leads with **Try again** (one tap, the Continue road) and with the failure's own fix when it is a Connections place (**Connect an AI** opens that list); a finished agent leads with **Mark done**, and its card says finished, never "No agent yet" (2026-10-22, the desk's R2) | the phone offered Stop and save, Next and Remind me under both |
| 22 | **help** / **/help** (and Telegram's **/start**) show what the phone can do in a few lines, with Back to the card, the walk and More… under it; **stop** / **/stop** end the walk - nothing on the table, the next walk from the top, no task changed - or hand a handed-over walk back. Only the bare word: "stop the agent on TQ-0003" is words for the model (2026-10-22) | "/help" and "/stop" went to the model and came back "Ok." |
| 23 | A voice note's answer starts with what was heard - `🎤 Heard: "..."` - before what was done with it, on both channels (2026-10-22) | the owner could not tell what had been transcribed |
| 24 | **Redraft** asks what should change - Shorter, Just rewrite, or the change typed as the next line - and Cancel goes back to the draft (2026-10-22) | it rewrote at once with no instruction |
| 25 | On Telegram a typed number picks only a line the message showed numbered; a bare "2" the buttons never showed runs nothing and says what the choices are, under them (an asking agent on the table still takes it as words) (2026-10-22) | Telegram's buttons have no numbers, yet "2" silently ran button 2 |

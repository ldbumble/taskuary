# The phone's choices

The owner, 2026-09-25: the phone Assistant matches the desktop Assistant exactly; the only differences are
formatting that reads well in WhatsApp, and buttons to tap. A chat has no buttons, so every choice is a
numbered line, and on WhatsApp the same lines also arrive as a poll under the message.

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
| 6 | Typing **next** moves on without reprinting the day's summary; "walk me through my tasks" opens with it | the summary came back on every Next |
| 7 | In the chat the Assistant listens in, a bare "yes" or "approve" is the Assistant's; quoting a review ping or naming `[rvN]` is still a phone approval | a bare "yes" approved whichever review had pinged last |
| 8 | On WhatsApp the choices also come as a poll on the last bubble (2 to 12 of them, each cut to 100 characters); only the newest poll in a chat counts | a poll is the one tappable thing WhatsApp lets an account send |
| 9 | Typed words that match a choice exactly, with the same capitals, count as a pick; anything else is words | a poll vote arrives as the choice's own words |

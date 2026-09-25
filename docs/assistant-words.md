# The Assistant's words

Every button under an Assistant card, what it does, and the words that work typed instead. Decided with
the owner word by word on 2026-09-25: 19 buttons became 8, and anything that lost its button still works
when you ask for it. If you are adding a button to a card, it is one of these or it goes through the same
proposal road (`concierge.PROPOSALS`), and it gets a row here and on the docs site
(`docs/site/assistant.md`).

The code: `concierge.CHIPS` (which buttons a card offers), `CHIP_WORDS` (their labels), `ALTS` (the one
question a card asks), `PROPOSALS` (what each runs), `toolcatalog.PURPOSE` (the tools the model may call).

## Which buttons each card shows

```mermaid
flowchart LR
  C{"What is on the table?"}
  C -->|a draft reply| B1["Send · Mark done · Not ours · Next"]
  C -->|an agent's proposal| B2["Run it · Not ours · Next"]
  C -->|a person's ask| B3["Reply · Make a task · Send to agent · Not ours · Next"]
  C -->|an fyi| B4["Make a task · Send to agent · Not ours · Next"]
  C -->|an agent waiting on you| B5["Save and end session · Next"]
  C -->|an agent that finished| B6["Mark done · Reply · Next"]
  C -->|a task| B7["Mark done · Next"]
  C -->|an idea| B8["Make a task · Send to agent · Next"]
  C -->|a meeting or a report| B9["Send to agent · Next"]
```

## The two buttons that ask one question

```mermaid
flowchart LR
  N["Not ours"] --> NQ{"How far?"}
  NQ -->|just this once| N1["Filed · its task deleted if untouched, else Mark done"]
  NQ -->|from now on| N2["Triage learns to file this sender · their mail still arrives"]
  NQ -->|a rule in Settings| N3["Never reaches triage · reversible"]
  A["Send to agent"] --> AQ{"Which agent? triage's pick is chosen"}
  AQ -->|a coding agent| A1["Task + coding agent · asks which repository if unclear"]
  AQ -->|a non-coding agent| A2["Task + non-coding agent"]
```

## Rules

- **Nothing runs from a sentence alone.** A button or a typed ask becomes a card; the card's button runs it.
  The exceptions run at once because they can be undone from the receipt: Next, Mark done, Save and end
  session, Remind me, and settings, reports and connections changed by name.
- **Next is the only "not now".** Open work you pass with Next comes back after `task_return_minutes`
  (three hours). A date is the task's own **Remind me** (`remind.py`); on that morning a note on the task
  brings it back.
- **Reply on a finished agent** is for the one that left no draft. A pull request's result offers none.
- **Retired words** (`parse_decision` maps the model's old verbs): Archive it is Not ours; Later, Tomorrow,
  "file this kind", and the `setting` verb are gone - a setting is the `setting.set` tool.

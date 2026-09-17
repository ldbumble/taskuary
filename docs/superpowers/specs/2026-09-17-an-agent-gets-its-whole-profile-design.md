# An agent gets the whole profile it was assigned

2026-09-17

## The bug

A worker's rules document is truncated to 1,800 characters on its way into the session.

```python
DOC_CHARS = 1800                    # how much of CODER.md rides along in the prompt
```

Measured against the shipped coding profile:

```
coder.md   raw 4,951  →  flattened 4,884  →  delivered to the agent 1,800
```

**Every coding session runs on 37% of its own rules**, cut mid-sentence, with nothing saying so. The
agent is told these are its rules and has no way to know it holds a fragment.

This is not new and it is not subtle — it is the same bug this codebase already found and fixed for
the message body, in a comment sitting eleven lines below the constant:

> *"The ask travels as ONE command-line argument now, so the old 3000-char squeeze on the message
> body has no delivery reason left - and it was never harmless: a 12,000-character mail reached the
> agent as its first quarter, unmarked, under an instruction that says 'work it from THIS message
> alone'. It read a fragment and believed it had the whole thing."*

`ASK_CHARS` went 3000 → 12000 for exactly that reason. `DOC_CHARS` was left at 1800.

## Why the number exists, and why the reason is gone

1,800 was sized for a delivery constraint that no longer applies. `agents.py`'s own header records
the migration: the prompt goes **over STDIN** because *"argv length limits are real on Windows"*. The
squeeze predates that.

What bounds the prompt now is `SEED_CEILING = 24000`, and it is enforced — `terminal.py:1297` trims
when the whole seed is over, and it already knows what to sacrifice:

> *"If we are over, the ASK is what gives, never the rules that keep an agent inside its checkout,
> and it gives out loud."*

So the rules are already the **protected** component. The only thing making them short is a constant
nobody revisited when its reason expired.

## What triage sees is a different thing, and it is already right

Worth stating because the two are easy to conflate, and conflating them is how a fix goes wrong:

| | what it is | where | today |
|---|---|---|---|
| choosing a worker | one line each: name and purpose | `agents.roster()`, capped 2000 total | correct — a summary is what a chooser needs |
| running as that worker | the worker's whole rules document | `terminal.rules_text()`, capped 1800 | **the bug** |

Triage never sees a profile's rules and should not. This change touches only the second row.

## The change

**`DOC_CHARS = 1800` → `DOC_CHARS = 6000`.**

Sized from the real documents rather than from a guess: the largest shipped profile flattens to 4,884
characters, and 6,000 leaves headroom for an owner who has added their own paragraphs without
inviting a profile to become a manual. Everything above it is still caught by `SEED_CEILING`, which
is the backstop that actually maps to the delivery limit.

The arithmetic holds. The seed's components at their caps:

```
ASK_CHARS        12,000   the message the task is about
BRIEF_CONTEXT     4,000   the conversation behind it
DOC_CHARS         6,000   the worker's rules          ← was 1,800
SEED_CHARS        2,200   the playbook, when there is one
                 ------
                  24,200  against SEED_CEILING 24,000
```

That is 200 over *only when every component is simultaneously at its maximum* — a 12,000-character
message, a 4,000-character thread, a 6,000-character profile and a playbook, all at once. In that
case `SEED_CEILING` does what it already does: trims the ask, out loud, in the order the code already
chose. No new failure mode is introduced; the existing one is simply reached slightly sooner in a
case that is already handled and already logged.

**Truncation stops being silent.** Whatever the number is, a rules document that does not fit should
say so, the way the ask already does. `rules_text` gets the same `_cut` treatment the ask gets, so a
profile that is genuinely too long arrives marked rather than pretending to be whole:

```python
    return _cut(' '.join(' '.join(keep).split()), chars, 'rules')
```

That is the part that matters more than the number. A fragment that announces itself is a
configuration problem; a fragment that does not is a worker confidently following half a rule.

## Files

- `taskuary/terminal.py:35` — the constant, and a comment recording what it is sized against
- `taskuary/terminal.py:1064` — `rules_text` marks its own truncation via `_cut`
- `taskuary/templates/coder.md` — unchanged. It is not too long; it was being cut.

## Tests

- `rules_text` returns the whole of a 4,884-character profile — the shipped `coder.md`, by measurement
  rather than by a literal, so the test still means something after the document is edited
- a profile longer than `DOC_CHARS` comes back marked by `_cut`, not silently short
- a profile shorter than `DOC_CHARS` is returned untouched, with no marker
- the seed for a task with a maximal ask, thread, profile and playbook stays within `SEED_CEILING`,
  and when it does not, the **ask** is what gives — the existing priority, asserted rather than assumed
- `agents.roster()` is unchanged in length and content: this must not widen what triage reads

## Deliberately not doing

- **No per-profile budget.** A second knob for a number that now has one honest global value is
  complexity bought with nothing. If imported skills later make some profiles genuinely large, that
  is the moment to argue for it, from real documents.
- **Not touching `SEED_CEILING`.** 24,000 maps to the delivery limit and is doing its job correctly.
- **Not touching `roster()`.** What triage reads to choose a worker is a summary and is already right.
- **No change to the documents themselves.** `coder.md` was never too long.

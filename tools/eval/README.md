# The agent evaluation framework

One place that says **what** of the agent experience is tested, **how** each part is driven, and **who judges** it - so a swarm hammers
the app against a map, not from memory, and spends the owner's Claude budget only on fixing.

## What: `catalogue.json`

Every part of the agent experience, one row each (44 today, 13 of them gaps nothing exercises yet):

| area | what it covers |
|---|---|
| doors | everything that reaches the agent: New, a line mid-turn, files on a line / in New / on a coding line, Send to agent, Continue, a routine's start, a flood |
| senders | a colleague, a stranger, an automated notice, a mail that tries to steer the AI, a no-reply or list address, the owner's own reply |
| timelines | a draft stands and the sender writes again, a restart mid-turn, someone late, Remind me while working |
| sessions | a silent turn, a CLI that dies, the AI's usage limit, a compacted or resumed session |
| cards | Send / edit / Don't send / twice, one card at a time, bulk, a press that fails, presses while the agent works, Approve on acts, calendar |
| starts | a full house, no AI, nothing connected that can do it |
| status | the working line always true, the turn's head, Stop |
| jobs | real-AI jobs end to end: mail reply, browser sign-ups, coding, research into a sheet |
| reports, rail, roads | a report's re-run in plain words, the Assistant, the same task on every agent road |

A bug the owner reports from the live app is added here first as its shape (`live-*`, invented people), then fixed.

## How: three lenses, one evidence bundle each

1. **Audit lens** (`tests/audit_scenarios.py`) - the scenario through the real server on every agent road (Claude CLI, ACP, API card,
   coding), the agent scripted by the director. Free, ~seconds. Proves: what the agent was told, what it heard once, what left the computer.
2. **Screen lens** (`website/browser/real-*.mjs` on `real-run.mjs`) - the same shape in the real app in Chrome, every frame sampled and
   the screen recorded. Its built-in rules catch, for free: his line drawn once, nothing new above it, the working line under it, no scroll
   jump, a card above his newer line greyed, words naming a button only where that button is lit.
3. **Brain** (`EVAL_BRAIN`): `stand-in` (free, scripted - every mechanic), `gateway` (Taskuary's own agent on the organisation AI card -
   real judgement on the gateway's budget), `cli` (the owner's Claude CLI - only the final confirming walk).

Each run leaves a **bundle**: the scenario's row, the chat as drawn, screenshots, what the agent was told (its prompts), what it read
(its own log), what was sent (the outbox), and the rules it broke.

## Who judges: Opus 5.5 judges, a Fable 5.2 orchestrator

The orchestrator (Fable 5.2) runs the loop below. Each judge is its own Opus 5.5 agent, never the one that made the fix, and reads one
bundle (screenshots included) against one rubric (`judges/<name>.md`), answering a JSON verdict:

- **ui** - flicker, jump, blank beat, stray UPPERCASE / mono / emoji, spacing, a press that does not do what it says, slow
- **truth** - every line the agent or the app says against what happened (outbox, log, store)
- **robust** (on a fix's diff) - a word list or per-case branch, a sleep, a second road beside one that exists, no failing-first test,
  a test that only holds on one machine

The deterministic rules run first; a judge reads only what they cannot decide.

## The loop a swarm runs

1. `run.py` runs the catalogue (or one area) -> bundles -> rules -> judges -> `findings.md`, deduplicated by part.
2. One fixer per finding: a failing test in the nearest test file, the general fix, the scenario run again (before / after bundles).
3. The judges read the after-bundle and the diff; all three pass -> the fix lands; else back with the reason.
4. A gap in the catalogue is closed by writing its scenario first.
5. Done when two full runs find nothing new. Then one confirming walk on the owner's real CLI.

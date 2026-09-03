---
name: soul-interview
description: Conduct a seven-question adaptive interview and turn the answers into Taskuary's SOUL.md. Use when creating or substantially rewriting the owner's operating context, boundaries, priorities, relationships, and communication preferences.
---

# Adaptive SOUL.md interview

Learn how the assistant should work for this particular person. Do not assume their work is
technical, office-based, managerial, or connected to software.

## Interview

- Ask exactly seven user-facing questions, one at a time. Wait for each answer before choosing
  the next question.
- Start broad: ask what the person wants the assistant to understand about them and the world in
  which they work. The first answer establishes the vocabulary and direction for the interview.
- Generate questions 2–7 from the full transcript so far. Refer naturally to useful specifics
  from earlier answers and pursue the highest-value missing detail. A generic fixed sequence is
  not adaptive.
- Ask one clear question per turn. Do not hide several unrelated questions in one sentence.
- Never ask specifically about code, repositories, infrastructure, or software unless the person
  introduced that subject. Use their domain's language instead.
- Respect “skip”, uncertainty, and short answers. Do not manufacture facts or pressure the person.
- Across the seven answers, learn enough to describe the person's context and desired outcomes,
  what deserves attention, what the assistant may handle independently, what always needs human
  judgment, relevant people and relationships, relevant tools or sources of truth, and how the
  person wants communication handled. These are coverage goals, not a questionnaire: combine,
  reorder, or replace them when the conversation makes another follow-up more valuable.
- Do not repeat a fact already answered unless the answer exposed a consequential ambiguity.

When called with `MODE: NEXT_QUESTION`, return JSON only:

```json
{"q":"The one next question?","why":"One short sentence explaining why this follows from what the person said.","placeholder":"A brief example shaped to their context, without presenting it as their fact."}
```

## Write the document

When called with `MODE: WRITE_SOUL`, turn the complete interview into concise Markdown. Preserve
the person's language and uncertainty. Never add a policy, person, responsibility, system, or
preference they did not state or that Taskuary did not supply as known context.

Keep exactly these headings and this order because Taskuary reads them:

1. `# SOUL.md - the operator's document`
2. `## What counts as a task`
3. `## How we respond`
4. `## Escalate (a human decides) when`
5. `## Systems and repositories`
6. `## People`

Under the title, briefly identify the owner and the assistant's purpose. Include the standing
promise that nothing sends or ships without the owner's approval. Use short, concrete bullets.
Treat “Systems and repositories” broadly as relevant tools, places, records, and sources of truth;
mention code repositories only when they are actually part of this person's work. If an area was
not answered, use one conservative line that says it is not yet specified rather than guessing.
Return Markdown only, without a preamble or code fence.

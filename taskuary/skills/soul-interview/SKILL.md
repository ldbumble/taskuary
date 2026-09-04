---
name: soul-interview
description: Conduct a seven-question adaptive interview and turn the answers into Taskuary's SOUL.md. Use when creating or substantially rewriting the owner's operating context, boundaries, priorities, relationships, and communication preferences.
---

# Adaptive SOUL.md interview

Learn how the assistant should work for this particular person. Do not assume their work is
technical, office-based, managerial, or connected to software.

## Fixed product boundaries are not interview topics

Taskuary's approval gate is a system rule, not a preference SOUL.md can grant or relax. Nothing
is sent, posted, published, shipped, or otherwise put in front of another person without the
owner's explicit approval. Never ask the owner which outbound actions may bypass approval, never
offer examples of exceptions, and never turn an interview answer into such permission. The
interview may ask what research, organization, analysis, or drafting would be useful before the
owner decides; it must not ask what Taskuary may send or ship on its own.

Do not ask broad permission questions such as "what may I change or commit without asking?" The
agent and playbook rules govern execution. SOUL.md should instead explain what matters, what the
assistant should notice, how it should communicate, and which ambiguities deserve the owner's
judgment.

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
  what matters most and what deserves attention, how the assistant should communicate and
  summarize, which ambiguities need the person's judgment, the person's organizational
  relationships, and the tools or sources of truth that shape the work. These are coverage goals,
  not a questionnaire: combine, reorder, or replace them when the conversation makes another
  follow-up more valuable.
- Do not repeat a fact already answered unless the answer exposed a consequential ambiguity.

### Keep the two kinds of people context separate

- `People` means the human working map: who the owner answers to, who answers to or depends on the
  owner, close collaborators, customers or leaders who change the communication context, and how
  the owner wants their requests understood. Message frequency is context, not proof that somebody
  is important or has authority. Names listed only as frequent correspondents in Taskuary's known
  context must not be presented as already important. When this area is missing, ask a
  relationship-first question rather than "who else is important?"
- `Project relationships` is separate structured memory maintained by Taskuary. It learns which
  people and channels belong to which project/repository only from the owner's explicit routing
  choices. Do not ask the owner to recreate that map in this interview, do not infer repository
  ownership from an interview answer, and do not write a `## Project relationships` section. The
  application restores that generated section after the interview without overwriting it.

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
promise that nothing sends or ships without the owner's explicit approval. That sentence is
mandatory even if an interview answer appears to disagree; SOUL.md cannot create an exception.
Use short, concrete bullets.
Treat “Systems and repositories” broadly as relevant tools, places, records, and sources of truth;
mention code repositories only when they are actually part of this person's work. If an area was
not answered, use one conservative line that says it is not yet specified rather than guessing.
In `People`, capture direction and relationship (reports to, reports to the owner, peer, customer,
leader, dependent) when stated; never convert mere correspondence frequency into importance.
Do not author or summarize the application-managed Connected systems, Project relationships, or
Repository map sections; Taskuary preserves and regenerates those separately.
Return Markdown only, without a preamble or code fence.

<!-- TRIAGE.md - the triage brain's instructions, shipped as a sensible default and yours
to edit. Two things to know before changing it: the JSON contract line must survive (a
reply the code cannot parse falls back to dumb keyword heuristics), and you do not need to
mention yourself or your rules here - SOUL.md, LEARNED.md and your standing notes are
appended after this text automatically on every call. Comments like this one are stripped
before the model sees the prompt. Blank the document entirely and the shipped default is
used again. -->
Classify one inbound work message. Answer JSON only: {"intent": "task|reply_only|fyi", "why": "<8 words max>"}.

task = someone must DO something beyond writing back: change a system, fix or build something, produce or chase something. This starts a coding agent on a repository, so choose it only when work has to happen.

reply_only = answering IS the work - a question, a status check, a scheduling note, anything you can settle in a message, even one needing a quick lookup. The reply is drafted for the owner to approve, so nothing is dropped by choosing this.

fyi = informational only: automated notices, reports, newsletters, thanks, threads the owner is merely copied on.

Torn between task and reply_only? Choose reply_only. The owner can turn a reply into a task in one click, and a wrongly-started agent costs far more than a draft.

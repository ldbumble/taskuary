# Tasks, agent sessions, and replies

A task has three related but independent lifecycles. The task page presents them as one numbered
workflow—**1 Task → 2 Agent work → 3 Reply**—and each stage owns its one state badge. The same
states are not repeated in the page header. This keeps a word such as “done” from carrying three
meanings.

The expanded workflow is the idle-state view. While a coding terminal or non-coding assistant
chat is running, the task collapses to a one-line context strip and the live workspace takes most
of the page. Full task controls, saved results, and restart choices return after the agent stops.
The task summary is shown in **Task**, so it is not repeated at the bottom. Original messages and
the audit notes are retained together in one collapsed **Context & history** section.

| Part | What it records | Main controls | What it never does by itself |
|---|---|---|---|
| Task | The durable job and who owns it | owner, kind, priority, status, Reopen, Mark task done | Starting or ending an agent does not complete an owner-controlled task |
| Agent work | One or more attempts by coding harnesses or non-coding agents, plus their saved result | harness/model, new prompt, start, prompt, pause, finish run, stop | Stopping does not mark the task done or send a reply |
| Reply | Communication with the person who sent the incoming item | write, generate, edit, approve and send | Sending an update does not complete an owner-controlled task |

## Task completion policy

The way work entered Taskuary determines who may complete it:

- **Triaged work is automatic.** When triage creates and dispatches a coding task, the agent may
  declare the work finished. Taskuary closes that task, saves the result, and prepares a reply.
  If the agent needs information, it raises its hand or prepares a clarification instead.
- **Owner-controlled work stays open.** A task created manually, promoted with **This one is
  mine**, split manually, opened as a non-coding discussion, or explicitly started/restarted by
  the owner carries the durable `stay:open` policy. Agent runs can finish and replies can be sent
  many times; only **Mark task done** completes the task.

Reopening a completed task creates a new task lifecycle without pretending an old terminal is
still alive. The Agent work section can then start a fresh session.

## Agent-work controls

When an agent has already finished, its latest saved result appears first in **Agent work**.
Harness, model, and prompt controls stay collapsed until **Run another agent** is selected. This
keeps the outcome prominent while still allowing a different harness or a new instruction for
the next attempt.

- **Start coding session** starts the selected harness and model. It receives the task summary,
  incoming messages, attachments, saved result and optional new prompt.
- **Start new coding session** can select a different harness after an earlier run stopped or
  hit a limit. The previous checkout and task history are retained.
- **Give new prompt** queues another instruction for the current live session.
- **Pause & save** ends the session after writing a handoff note for the next one.
- **Finish agent run** ends the session and writes its result, but does not complete an
  owner-controlled task.
- **Stop session** ends only the process. It deliberately changes neither task nor reply state.

Marking the task done is stronger: it completes the task and also ends any live agent session,
because a finished task should not leave an orphan process running.

## Reply controls

The Reply section exists whenever the task has an incoming sender. It shows whether no reply has
been drafted, a draft is ready, or a reply was sent. **Open in Review** is the only sending road;
the operator may type their own response or generate one, edit it, and approve it.

A clarification is special: after it is sent, the active agent is stopped and the task moves to
waiting because an external answer is required. A normal reply sent from an owner-controlled
task is simply an update; it leaves both task status and any useful agent session alone.

## Timeline and task-list badges

Timeline keeps its prominent action state—such as `agent working`, `agent waving`, or `reply
ready`—and adds the task's raw lifecycle badge beside it. The Tasks list does the same. This
makes combinations explicit rather than contradictory: `task · waiting` plus `agent waving`, or
`task · in progress` plus `reply sent`.

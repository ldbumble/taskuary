"""What the owner asked for, remembered as tasks and said back at the door they asked from
(docs/superpowers/specs/2026-10-05-assistant-remembers-asks-design.md).

The assistant is deliberately light - it hands work to tasks and keeps nothing of its own - so it forgot: "where's the tab
check?" had no answer, and finished work was silent. An ask IS a task, marked with where it was asked (`AskedVia`); its
state is its rail lane in the rail's own words; a move into a lane that needs the owner, or its end, is said once. No
memory store, no model call.
"""


def door() -> str:
    """Where the owner is asking from right now: the phone chat speaking this turn, else the desktop."""
    from . import remote_assistant
    at = remote_assistant.asking()
    return f"{at['channel']}:{at['chat']}" if at and at.get('channel') and at.get('chat') else 'desktop'


def of(task) -> str | None:
    """The door a task was asked from, or None for work the owner did not ask for (triage, reports, ...)."""
    return (task or {}).get('AskedVia') or None

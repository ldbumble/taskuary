"""Reconnect saved conversations and surface unfinished work using records we already keep."""
import hashlib
import json
import os
import re
from .timewords import plural


def context_key(store, pick, model):
    """A native conversation belongs to one provider configuration and working directory."""
    from .config import home
    from .agents import agent_row
    row = agent_row(store, pick[4:]) if pick.startswith('cli:') else None
    config = json.loads((row or {}).get('Config') or '{}')
    # The general assistant's CLI runs in Taskuary scratch, not the coding profile's checkout.
    config = {k: v for k, v in config.items() if k not in ('cwd', 'cwd_map')}
    scope = [pick, model, config, str((home() / 'scratch').resolve()),
             os.environ.get('CODEX_HOME', ''), os.environ.get('CLAUDE_CONFIG_DIR', '')]
    return hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()


def can_resume(store, pick):
    if not pick.startswith('cli:'): return False
    from .agents import agent_row, resume_argv
    prof = json.loads((agent_row(store, pick[4:]) or {}).get('Config') or '{}')
    # over ACP the id is the protocol's own (session/new) and session/load is how it is picked back up:
    # devin has no argv resume flag and still reloads its sessions, yet the id it returned was dropped
    # on the floor and the row saved NativeId '' (measured 2026-09-20)
    return bool(resume_argv(prof, 'x')) or bool(prof.get('acp'))


def previous_work(store, limit=5):
    from . import general, terminal
    reviews = {r['TaskId']: r for r in reversed(store.list_reviews('pending')) if r.get('TaskId')}
    live = {s.task_id: s for s in list(terminal.SESSIONS.values()) if s.alive}
    result = []
    for row in store.previous_work():
        tid = row['TaskId']
        if general.is_dock(row): continue
        session = live.get(tid)
        if tid in general.OPENING or (session and (getattr(session, 'mode', '') != 'assistant' or session.busy)): continue
        review = reviews.get(tid)
        if row['Status'] == 'done' and not review: continue
        recap = re.sub(r'^(HANDOVER NOTE|AGENT REPORT|CODER REPORT)\s*', '', row.get('Recap') or '').strip()
        recap = recap or 'A saved session is available. Continue from its existing work and handover.'
        result.append({'taskId': tid, 'title': row['Title'], 'recap': recap[:600],
                       'lastWorkedAt': row['LastWorkedAt'], 'action': 'review' if review else 'resume',
                       'reviewId': review['ReviewId'] if review else None})
        if len(result) >= limit: break
    return result


RESUME_PROMPT = (
    'The owner chose Resume for this task. Use the saved conversation and handover to pick up where '
    'work stopped. Briefly say what is already done, then continue the next unfinished step. '
    'Verify the current state before repeating any action. If you were waiting for an answer or '
    'approval, restate that one question and wait; do not invent the answer or treat Resume as approval '
    'to send, publish, or execute a pending action. If the result is ready, point the owner to it for review.'
)


# ── what came in after the agent's last turn ─────────────────────────────────────────────────────────────────────────
# A task an agent finished can be REOPENED by a new mail on its thread (ingest._reopen). Its saved conversation is still
# there, so the rail drew it as a paused agent - "this conversation paused when Taskuary stopped" - and the Advisor said
# Continue, while Continue itself only said "pick up where work stopped": the agent woke at "reply sent, task closed",
# never told that two people had since written asking for something new (the owner, 2026-10-14, a reopened ask). One
# reading of it, for the card, the walk's line, the Advisor and the Continue prompt.

def last_agent_turn(store, tid) -> str:
    """When the agent last spoke on this task: its newest reply or report, or the saved conversation's own stamp."""
    said = [c['CreatedAt'] for c in store.list_comments(tid) if c.get('CreatedAt') and (c.get('ActorType') == 'assistant_agent'
            or str(c.get('Body') or '').startswith(('AGENT REPORT', 'CODER REPORT', 'HANDOVER NOTE')))]
    saved = (store.saved_session(tid) or {}).get('UpdatedAt')
    return max([s for s in [*said, saved] if s] or [''])


def mail_since(store, tid, at: str = None) -> list:
    """The mail that reached this task's thread after the agent's last turn - by when it reached US (CreatedAt): one sent
    earlier but read in later is still news to an agent that never saw it. Our own replies and filed context are not."""
    at = last_agent_turn(store, tid) if at is None else at
    if not at: return []
    return store._rows("SELECT * FROM message WHERE TaskId=? AND CreatedAt>? AND IFNULL(Direction,'in')<>'out' "
                       "AND Status NOT IN ('context','history','skipped') AND IFNULL(Channel,'')<>'report' "
                       'ORDER BY CreatedAt, MessageId', (tid, at))


def _day(at: str) -> str:
    from datetime import datetime
    try: d = datetime.strptime(str(at)[:16], '%Y-%m-%d %H:%M')
    except ValueError: return str(at)[:10]
    return d.strftime('%b ') + str(d.day)


def who_wrote(mail: list) -> str:
    names = list(dict.fromkeys(str(m.get('FromName') or m.get('FromEmail') or 'someone').strip() for m in mail))
    return names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' and ' + names[-1]


def since_line(store, tid, agent: str = 'the agent') -> str:
    """The card's one sentence for a saved conversation: whose it is, from when, and - when the thread moved after it - that
    it is from BEFORE that mail. '' with no saved turn to speak of."""
    at = last_agent_turn(store, tid)
    if not at: return ''
    mail = mail_since(store, tid, at)
    if not mail: return f"{agent}'s conversation from {_day(at)} is saved; it can pick up where it left off"
    return f"{who_wrote(mail)} wrote again after {agent}'s conversation of {_day(at)} - continue it and it reads the new mail first"


def news_block(store, tid) -> str:
    """What a Continue tells the agent before anything else, when the thread moved after its last turn. '' when it did not."""
    at = last_agent_turn(store, tid)
    mail = mail_since(store, tid, at) if at else []
    if not mail: return ''
    def one(m):
        body = ' '.join(str(m.get('BodyText') or '').split())[:1500]
        return f"- {m.get('FromName') or ''} <{m.get('FromEmail') or ''}> at {m.get('SentAt') or m.get('CreatedAt')}: {m.get('Subject') or ''}\n  {body}"
    return (f"NEW SINCE YOUR LAST TURN ({at}): {plural(len(mail), 'message')} came in on this task's thread after "
            "the conversation you remember - it is from BEFORE them, and the task was reopened because of them. Read them first; "
            "what they ask is the work now, not what you finished last time.\n" + '\n'.join(one(m) for m in mail[-5:]))

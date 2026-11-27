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
    try: return bool(resume_argv(prof, 'x', store)) or bool(prof.get('acp'))
    except ValueError: return False          # agents.NoAI: nothing runs it, so nothing resumes


def previous_work(store, limit=5):
    from . import general, terminal
    reviews = {r['TaskId']: r for r in reversed(store.waiting_reviews()) if r.get('TaskId')}
    live = {s.task_id: s for s in list(terminal.SESSIONS.values()) if s.alive}
    result = []
    for row in store.previous_work():
        tid = row['TaskId']
        if general.is_dock(row): continue
        session = live.get(tid)
        if tid in general.OPENING or (session and (getattr(session, 'mode', '') != 'assistant' or session.busy)): continue
        review = reviews.get(tid)
        if row['Status'] == 'done' and not review: continue
        recap = re.sub(r'^(HANDOVER NOTE|AGENT REPORT)\s*', '', row.get('Recap') or '').strip()
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
    'to send, publish, or execute a pending action. If the result is ready, point the owner to it for review. '
    # ...WHAT IT FINDS IS ITS OWN CONTEXT, NOT NEWS (the recorded walks, 2026-11-11: "Nothing was awaiting approval, so the next step is...",
    # "Nothing was saved from before the pause", "Nothing had been done before this resume" - each check it was asked to make, read back)
    'All of that is for you: tell the owner only what is done, what you are doing and what you need from them - never that something '
    'was absent (nothing saved, nothing pending, nothing awaiting approval).'
)


# ── what came in after the agent's last turn ─────────────────────────────────────────────────────────────────────────
# A task an agent finished can be REOPENED by a new mail on its thread (ingest._reopen). Its saved conversation is still
# there, so the rail drew it as a paused agent - "this conversation paused when Taskuary stopped" - and the Advisor said
# Continue, while Continue itself only said "pick up where work stopped": the agent woke at "reply sent, task closed",
# never told that two people had since written asking for something new (the owner, 2026-10-14, a reopened ask). One
# reading of it, for the card, the walk's line, the Advisor and the Continue prompt.

def last_agent_turn(store, tid) -> str:
    """When the agent last spoke on this task: its newest reply or report, or the saved conversation's own stamp."""
    said = [c['CreatedAt'] for c in store.list_comments(tid, internal=True) if c.get('CreatedAt') and (c.get('ActorType') == 'assistant_agent'
            or str(c.get('Body') or '').startswith(('AGENT REPORT', 'HANDOVER NOTE')))]
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


# ── a reply that already went ────────────────────────────────────────────────────────────────────────────────────────
# The agent drafted the reply, the owner sent it, the owner pressed Continue - and the agent, remembering only "I saved a reply
# for approval", saved ANOTHER one to the same sender, though nothing had come from them since (the owner, 2026-10-20: "I replied
# with what the agent created, then reran the agent and it recreated some reply???"). Its conversation is from before the send;
# nothing told it the send happened. One reading of it, for every door that wakes an agent up again.

def clock(at) -> str:
    """'5:33 PM' (timewords.clock), with the day when it is not today."""
    from datetime import datetime
    from .timewords import clock as said
    try: d = datetime.strptime(str(at)[:16], '%Y-%m-%d %H:%M')
    except ValueError: return str(at or '')
    return said(d) + ('' if d.date() == datetime.now().date() else f' on {_day(at)}')


def sent_since(store, tid) -> tuple:
    """(the newest reply that went out on this task, the mail that reached the thread after it) - (None, []) when none went."""
    rv = store.sent_reply(task_id=tid)
    return (rv, mail_since(store, tid, str(rv.get('DecidedAt') or rv.get('CreatedAt') or ''))) if rv else (None, [])


def _env_to(store, rv) -> list:
    "Where its words go (outbound.review_envelope - the one answer the card sends by): the To addresses."
    from .outbound import review_envelope
    to = review_envelope(store, rv or {}).get('to')
    return [str(x) for x in (to if isinstance(to, (list, tuple)) else [to]) if x] if to else []


def answers(rv):
    "The message a reply answers - its own column where the thread moved on past it (C2), else the one it was written on."
    return (rv or {}).get('AnswersMid') or (rv or {}).get('MessageId')


def addressees(store, rv) -> set:
    "The addresses a reply or an email goes to, lower-cased - sent_to's, as addresses: where the card sends it, else the sender of the message it answers."
    to = _env_to(store, rv) or [(store.get_message(answers(rv)) or {}).get('FromEmail') or '']
    return {x.strip().lower() for x in to if x and x.strip()}


def sent_to(store, rv, none: str = 'them') -> str:
    """Whom a reply or an email goes to: where the card sends it (outbound.review_envelope - a Reply-To honoured), else who wrote the message
    it answers. The envelope first (2026-11-17): a message the owner started answers his own ask, and the agent read its draft as going "to You"."""
    to = _env_to(store, rv)
    m = store.get_message(answers(rv)) or {}
    # ...each address by the person it is where the message answered says so - "Gail Moreno", never her address (CI, 2026-11-17)
    named = {str(m.get('FromEmail') or '').lower(): str(m.get('FromName') or '').strip()} if m.get('FromName') else {}
    if to: return ', '.join(named.get(x.lower()) or x for x in to)
    return str(m.get('FromName') or m.get('FromEmail') or none).strip()


def sent_block(store, tid, quote: int = 300, cmd: str = '') -> str:
    """The line a woken agent hears when its reply already went and nobody wrote since: it is sent, not pending. '' otherwise.
    `quote` caps the sent words (a terminal's seed is a ~1 KB command line, so it quotes less); `cmd` names the follow-up road."""
    rv, mail = sent_since(store, tid)
    if not rv or mail: return ''
    said = ' '.join(str(rv.get('FinalText') or rv.get('DraftText') or '').split())
    said = f' ("{said[:quote]}{"..." if len(said) > quote else ""}")' if quote and said else ''
    return (f'YOUR REPLY WENT OUT: the reply to {sent_to(store, rv)} was SENT at {clock(rv.get("DecidedAt"))}{said}, and nothing new '
            'has come from them since - it is not waiting on anyone. Do not draft another reply unless the owner asks you for one'
            + (f' (then: {cmd})' if cmd else '') + '.')


NEWS_SHOWN = 5            # how many of the messages since its last turn news_block says in their words
def news_block(store, tid) -> str:
    """What a Continue tells the agent before anything else, when the thread moved after its last turn - or, when it did not, that
    the reply it remembers drafting already went. '' when neither."""
    at = last_agent_turn(store, tid)
    mail = mail_since(store, tid, at) if at else []
    if not mail: return sent_block(store, tid)
    def one(m):
        body = ' '.join(str(m.get('BodyText') or '').split())[:1500]
        return f"- {m.get('FromName') or ''} <{m.get('FromEmail') or ''}> at {m.get('SentAt') or m.get('CreatedAt')}: {m.get('Subject') or ''}\n  {body}"
    return (f"NEW SINCE YOUR LAST TURN ({at}): {plural(len(mail), 'message')} came in on this task's thread after "
            "the conversation you remember - it is from BEFORE them, and the task was reopened because of them. Read them first; "
            "what they ask is the work now, not what you finished last time.\n" + '\n'.join(one(m) for m in mail[-NEWS_SHOWN:])
            + (f'\n{s}' if (s := sent_block(store, tid)) else ''))     # ...unless the owner already answered them

# ...AND IN A CONVERSATION SAID AFRESH ITS MAIL IS SAID ONCE (the CI fixer, 2026-11-24): that prompt's SOURCE MATERIAL carries every message, fenced
# and by its id, and the brief's block quoted each new one again above it, unfenced. There the block keeps each mail's head line, never its words
_NEWS = re.compile(r'^NEW SINCE YOUR LAST TURN \(.*?(?=\n\n|\Z)', re.S | re.M)
def unquoted(text: str) -> str:
    "A brief as a prompt said afresh says it: news_block without the words of the mail its SOURCE MATERIAL already holds."
    return _NEWS.sub(lambda m: re.sub(r'\n  .*', '', m.group(0)), str(text or ''))

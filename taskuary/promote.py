"""RULE PROMOTION: a learned pattern clear-cut enough to be a deterministic rule, raised by the rail's Advisor as ONE question.

LEARNED.md and the verdict notes are evidence the model weighs on every mail; a rule (policy.py) is the hard edge that runs BEFORE
the model and costs nothing. When the owner's own presses already draw that edge - every mail from one sender put down and none
acted on, every task from one sender marked urgent - the Advisor asks once whether to make it a rule (the owner, 2026-10-20). Yes
writes the policy through the one create path (policy.save), tagged as promoted from learning; No is the idea's own dismiss, and
it is asked again only when the evidence has grown GROW-fold since.

Everything here is a COUNT, never a word match or a model's reading. The thresholds are conservative on purpose: a wrong ignore
rule silences the very corrections that would revoke it (learned.md's "Proposed rules" says the same of hiding rules).
  - ignore a sender:   IGNORE_AT threads from them the owner put down (Not ours, Not a task, Ignore this sender) and none taken up
  - skip a sender:     the same at SKIP_AT, and only for mail the headers call automated or bulk - skip hides it from the timeline
  - a whole domain:    DOMAIN_SENDERS automated senders on it, DOMAIN_AT put-downs between them, none taken up by anyone there
  - escalate a sender: ESCALATE_AT tasks from them the owner marked urgent by hand, and none of theirs ever put down
NEVER for a colleague (the owner's own or team domains) or anyone the owner has written to - so never a skip for someone ever
replied to. Never when an active rule already covers them. One rule question open at a time, the strongest first."""
import json, re
from datetime import datetime, timedelta
from loguru import logger

from .timewords import plural

IGNORE_AT, SKIP_AT, ESCALATE_AT = 8, 20, 5
DOMAIN_SENDERS, DOMAIN_AT = 3, 12
GROW = 3                   # a refused question comes back only once the evidence is this many times what it was refused at
DAYS = 90                  # how far back the evidence is read
DOWN = ('not_ours', 'not_ours_sender', 'block_sender')                 # presses that put an item down
NEUTRAL = ('next', 'close', 'defer', 'not_ours_kind', 'later', '')     # presses that say nothing about the sender
DOWN_NOTE = re.compile(r' - (NOT A TASK|NOT OURS|FILE IT)\b')
UP_NOTE = re.compile(r" - (MADE A TASK|REPLY ONLY|CODING TASK|THE OWNER'S OWN TASK|A CONVERSATION)\b")
FROM_NOTE = re.compile(r' from (\S+@\S+?)(?= - |\s|$)')
NOTE_SUBJ = re.compile(r'^\d{4}-\d\d-\d\d: "(.*?)"')
AUTOMATED = ('automated', 'bulk')
URGENT_ACTION = 'priority'  # the audit row server.update_task writes when the owner changes a task's priority


def _since(days=DAYS): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
def _dom(em: str) -> str: return em.rsplit('@', 1)[-1] if '@' in em else ''


def _who(store) -> tuple:
    """(the owner's own and team domains, the owner's own addresses)."""
    from .senders import own_domains, own_addresses
    from .categories import team_domains_of
    return own_domains(store) | team_domains_of(store.get_settings()), own_addresses(store)


def written_to(store, em: str) -> bool:
    """Has the owner ever written to them - a reply in a thread they wrote in, or a mail addressed to them?"""
    q = ("SELECT 1 FROM message i JOIN message o ON o.ConversationId=i.ConversationId WHERE lower(i.FromEmail)=? "
         "AND (o.Direction='out' OR o.Status='context') LIMIT 1")
    if store._one(q, (em,)): return True
    return bool(store._one("SELECT 1 FROM message WHERE (Direction='out' OR Status='context') AND lower(IFNULL(RecipientsJson,'')) LIKE ? LIMIT 1",
                           (f'%{em}%',)))


def evidence(store, days: int = DAYS) -> dict:
    """{sender: {'down': {thread}, 'up': {thread}, 'urgent': {task}, 'threads': {thread}, 'auto': bool}} - what the owner did,
    per sender and per THREAD (three replies on one thread are one episode), from the route log, the press log, the verdict notes
    and the audit trail."""
    since, out = _since(days), {}
    def row(em): return out.setdefault(em, {'down': set(), 'up': set(), 'urgent': set(), 'threads': set(), 'auto': None})
    for m in store._rows("SELECT lower(FromEmail) em, ConversationId cid, MessageId, SenderClass FROM message WHERE IFNULL(Direction,'in')<>'out' "
                         "AND Status<>'context' AND FromEmail LIKE '%_@_%' AND Channel NOT IN ('report','assistant','own') AND IFNULL(SentAt,CreatedAt)>=?", (since,)):
        r = row(m['em']); r['threads'].add(m['cid'] or f"m{m['MessageId']}")
        r['auto'] = r['auto'] is not False and str(m.get('SenderClass') or '').lower() in AUTOMATED   # every one of theirs a machine's
    # the owner's own put-downs: Not ours and Not a task both write an owner `ignore` route (server.not_mine, file_message)
    for m in store._rows("SELECT lower(m.FromEmail) em, m.ConversationId cid, m.MessageId FROM route r JOIN message m ON m.MessageId=r.MessageId "
                         "WHERE r.RoutedBy='owner' AND r.Decision='ignore' AND m.FromEmail LIKE '%_@_%' AND r.CreatedAt>=?", (since,)):
        row(m['em'])['down'].add(m['cid'] or f"m{m['MessageId']}")
    try: presses = store._rows("SELECT lower(Sender) em, Thread, Pressed, Id FROM advice_press WHERE Sender LIKE '%_@_%' AND CreatedAt>=?", (since,))
    except Exception: presses = []
    for p in presses:
        k = p['Thread'] or f"pr{p['Id']}"
        if p['Pressed'] in DOWN: row(p['em'])['down'].add(k)
        elif p['Pressed'] not in NEUTRAL: row(p['em'])['up'].add(k)
    # the verdict notes (LEARNED.md's evidence block): one per mail, matched to its thread so a note and its route are one episode
    for n in store.list_memories():
        if n.get('Source') != 'verdict' or str(n.get('CreatedAt') or '') < since: continue
        note = str(n.get('Note') or ''); f = FROM_NOTE.search(note)
        em = (f.group(1) if f else (n.get('ScopeKey') if n.get('Scope') == 'sender' else '') or '').lower()
        if '@' not in em: continue
        subj = (NOTE_SUBJ.match(note) or [None, None])[1]
        hit = store._one("SELECT ConversationId FROM message WHERE lower(FromEmail)=? AND substr(IFNULL(Subject,''),1,90)=? ORDER BY MessageId DESC LIMIT 1",
                         (em, subj)) if subj is not None else None
        k = (hit or {}).get('ConversationId') or f"mem{n['MemoryId']}"
        if DOWN_NOTE.search(note): row(em)['down'].add(k)
        elif UP_NOTE.search(note): row(em)['up'].add(k)
    # taken up: the owner wrote back on the thread, sent a reply from a task on it, or closed a task of theirs as done work
    for em, r in out.items():
        for t in store._rows("SELECT DISTINCT i.ConversationId cid FROM message i JOIN message o ON o.ConversationId=i.ConversationId "
                             "WHERE lower(i.FromEmail)=? AND (o.Direction='out' OR o.Status='context')", (em,)): r['up'].add(t['cid'])
        for t in store._rows("SELECT DISTINCT m.ConversationId cid FROM message m JOIN review v ON v.TaskId=m.TaskId WHERE lower(m.FromEmail)=? "
                             "AND v.Status IN ('approved','sent')", (em,)): r['up'].add(t['cid'])
        for t in store._rows("SELECT DISTINCT m.ConversationId cid FROM message m JOIN task t ON t.TaskId=m.TaskId WHERE lower(m.FromEmail)=? "
                             "AND t.Status='done' AND t.UpdatedBy='owner'", (em,)):
            if t['cid'] not in r['down']: r['up'].add(t['cid'])
    # escalated by hand: the owner set a task of theirs urgent (server.update_task's audit row)
    for a in store._rows('SELECT EntityId, Detail FROM audit WHERE EntityType=? AND Action=? AND Actor=? AND CreatedAt>=?',
                         ('task', URGENT_ACTION, 'owner', since)):
        try: to = (json.loads(a.get('Detail') or '{}') or {}).get('to')
        except ValueError: to = None
        if to != 'urgent': continue
        m = store._one("SELECT lower(FromEmail) em FROM message WHERE TaskId=? AND IFNULL(Direction,'in')<>'out' AND FromEmail LIKE '%_@_%' "
                       'ORDER BY MessageId LIMIT 1', (a['EntityId'],))
        if m: row(m['em'])['urgent'].add(a['EntityId'])
    return out


def covered(store, em: str, actions=('skip', 'ignore', 'escalate')) -> bool:
    """An active rule on the envelope already decides this sender - asking for another would be the toil card's old mistake."""
    from .policy import BODYLESS, matches
    return any(p.get('Active', 1) and p['Kind'] in BODYLESS and p['Action'] in actions and matches(p, {'from_email': em})
               for p in store.list_policies(active_only=True))


def _cand(kind, pattern, action, n, text, why, policy_reason) -> dict:
    name = {'skip': 'Skip', 'ignore': 'Ignore', 'escalate': 'Escalate'}[action]
    return {'key': f'rule:{kind}:{pattern}', 'kind': 'rule', 'sig': str(n), 'text': text, 'facts': why, 'why': why,
            'action': {'type': 'rule', 'count': n, 'whose': 'yours - a yes or a no', 'why': why,
                       'policy': {'Name': f'{name} {pattern} (learned)', 'Kind': kind, 'Pattern': pattern, 'Action': action,
                                  'Reason': f'promoted from learning: {policy_reason}', 'Active': 1}}}


def _asked(state: dict, key: str, n: int) -> bool:
    """Said before and not to be said now: open or put away still, done (the rule exists), or refused at evidence that has not
    grown GROW-fold since."""
    i = state.get(key)
    if not i: return False
    if i.get('Status') != 'dismissed': return True
    try: was = int(str(i.get('Sig') or '0').split('|')[0])
    except ValueError: was = 0
    return n < GROW * max(1, was)


def candidates(store, state: dict = None, days: int = DAYS) -> list:
    """Every rule the evidence earns, strongest first - before the one-at-a-time cut (ideas)."""
    state = state if state is not None else {i['Key']: i for i in store.list_ideas()}
    mine, me = _who(store)
    ev, out = evidence(store, days), []
    ok = {em: r for em, r in ev.items() if _dom(em) and _dom(em) not in mine and em not in me and not written_to(store, em)}
    for em, r in ok.items():
        down, up, urgent = len(r['down'] - r['up']), len(r['up']), len(r['urgent'])
        if up == 0 and down >= IGNORE_AT and not covered(store, em, ('skip', 'ignore')):
            act = 'skip' if r['auto'] and down >= SKIP_AT else 'ignore'
            seen = len(r['threads'])
            lead = f"all {plural(down, 'mail')}" if seen <= down else f"{down} of the {plural(seen, 'mail')}"
            what = ('never reach you' if act == 'skip' else 'are filed without reaching you - still on your Timeline, never a task')
            out.append(_cand('sender', em, act, down,
                             f"You've put down {lead} from {em} and acted on none. Make it a rule so they {what}? (Rules run before the AI.)",
                             f"{plural(down, 'thread')} from {em} put down by you (Not ours / Not a task) in {days} days, none answered or taken up; "
                             f"you have never written to them",
                             f'the owner put down {down} of their mails and took up none'))
        if not r['down'] and urgent >= ESCALATE_AT and not covered(store, em, ('escalate',)):
            out.append(_cand('sender', em, 'escalate', urgent,
                             f"You've marked urgent all {plural(urgent, 'task')} from {em}. Make it a rule so their mail lands urgent? (Rules run before the AI.)",
                             f"{plural(urgent, 'task')} from {em} marked urgent by you in {days} days, none of their mail ever put down",
                             f'the owner marked {urgent} of their tasks urgent by hand'))
    # a whole domain only when every sender on it is a machine: a domain of people (a free-mail one above all) never gets a rule
    doms = {}
    for em, r in ev.items(): doms.setdefault(_dom(em), []).append((em, r))
    for d, rows in doms.items():
        if not d or d in mine or any(em in me or not r['auto'] or r['up'] or written_to(store, em) for em, r in rows): continue
        hit = [(em, r) for em, r in rows if r['down']]
        n = sum(len(r['down']) for _, r in hit)
        if len(hit) < DOMAIN_SENDERS or n < DOMAIN_AT or covered(store, f'x@{d}', ('skip', 'ignore')): continue
        out.append(_cand('sender_domain', d, 'ignore', n,
                         f"You've put down all {plural(n, 'mail')} from {len(hit)} automated senders at {d} and acted on none. "
                         f"Make it a rule for the whole domain, so they are filed without reaching you? (Rules run before the AI.)",
                         f"{plural(n, 'thread')} from {', '.join(sorted(em for em, _ in hit)[:5])} put down by you in {days} days, none taken up",
                         f'the owner put down {n} mails from {len(hit)} automated senders there'))
    # a domain question says what the per-sender ones would, once - and the strongest evidence leads
    doms_asked = {c['action']['policy']['Pattern'] for c in out if c['action']['policy']['Kind'] == 'sender_domain'}
    out = [c for c in out if not (c['action']['policy']['Kind'] == 'sender' and _dom(c['action']['policy']['Pattern']) in doms_asked)]
    out = [c for c in out if not _asked(state, c['key'], c['action']['count'])]
    return sorted(out, key=lambda c: -c['action']['count'])


def ideas(store, state: dict = None, days: int = DAYS) -> list:
    """The ONE rule question to raise now, or none - none while another is still open on the rail."""
    state = state if state is not None else {i['Key']: i for i in store.list_ideas()}
    if any(i.get('Kind') == 'rule' and i.get('Status') in ('open', 'snoozed') for i in state.values()): return []
    # "No more ideas like this" on a rule question means no more rule questions
    from .assistant import verdicts
    if any(str(v.get('key') or '').startswith('rule:') and v.get('verdict') == 'dismiss_kind' for v in verdicts(store)): return []
    try: return candidates(store, state, days)[:1]
    except Exception as e:
        logger.warning(f'rules: the promotion check was skipped - {e}'); return []


def accept(store, idea: dict, action: dict, actor: str = 'owner') -> dict:
    """Yes: the rule the question proposed, through the one create path, tagged as promoted from learning."""
    from . import policy
    p = dict((action or {}).get('policy') or {})
    if not (p.get('Kind') in ('sender', 'sender_domain') and p.get('Pattern') and p.get('Action') in policy.PRECEDENCE):
        raise ValueError('this idea carries no rule to make')
    out = policy.save(store, p, actor, via='advisor-rule', promoted_from='learning', idea=idea.get('IdeaId'), evidence=(action or {}).get('count'))
    if p['Action'] in ('skip', 'ignore') and p['Kind'] == 'sender':
        from . import outcomes          # the ledger: regret if their mail becomes work anyway
        outcomes.record(store, 'sender.ignored', 'policy', out['policyId'], actor, facts={'from': p['Pattern'], 'rule': p['Action']})
    return out

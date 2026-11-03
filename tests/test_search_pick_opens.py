"""A SEARCH PICK OPENS WHAT WAS PICKED (a colleague, 2026-11-03: a hit clicked, the canvas showed "…" and then nothing, and the chat
said "I can't find that one - it may be older than what I keep" three times over). Search lists every message whatever became of it -
skipped at the first sync, filed, ignored, answered, sent, on a closed task - and the pick opens it by its id through railwalk.open,
which only knew the rows a rail would show. Every hit Search lists opens as itself, and never says it cannot be found."""
from datetime import datetime, timedelta
import pytest
from taskuary import concierge, funnel, general, railwalk, search, terminal
from taskuary.store import MemoryStore

def ago(**k): return (datetime.now() - timedelta(**k)).strftime('%Y-%m-%d %H:%M:%S')
GAIL = 'gail@northwind.example'

@pytest.fixture
def s(monkeypatch):
    s = MemoryStore(); s.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    funnel.invalidate(); yield s; funnel.invalidate(); s.close()

def mail(s, subj, **f):
    return s.add_message({'Channel': 'email', 'Subject': f'Lanyard {subj}', 'BodyText': f'About the lanyard order ({subj}).', 'FromName': 'Gail Moreno',
                          'FromEmail': GAIL, 'SourceName': 'alex@northwind.example', 'SentAt': ago(days=3), 'Direction': 'in',
                          'ConversationId': f'c-{subj}', 'ExternalId': f'x-{subj}', **f})

def shapes(s):
    tid = s.create_task({'Title': 'Lanyard order for the open day', 'Kind': 'general'}, 'owner')
    shut = s.create_task({'Title': 'Old badge reprint', 'Kind': 'general', 'Status': 'done'}, 'owner')
    src = s.save_source({'Channel': 'report', 'Address': 'Lanyard stock', 'Active': 1, 'ConfigJson': '{"title": "Lanyard stock"}'}, 't')
    m = {'fyi': mail(s, 'fyi', Status='filed'), 'read': mail(s, 'read', Status='filed'),
         'skipped': mail(s, 'skipped', Status='skipped', SentAt=ago(days=200)), 'history': mail(s, 'history', Status='history'),
         'ignored': mail(s, 'ignored', Status='ignored'),
         'sent': mail(s, 'sent', Status='context', Direction='out', FromName='Alex Doyle', FromEmail='alex@northwind.example'),
         'sent2': mail(s, 'sent2', Status='sent', Direction='out', FromName='Alex Doyle', FromEmail='alex@northwind.example'),
         'closed': mail(s, 'closed', Status='routed', TaskId=shut),
         'report': s.add_message({'Channel': 'report', 'Subject': 'Lanyard stock - 40 left', 'BodyText': 'Lanyard stock is low.', 'Status': 'feed',
                                  'SourceName': f'report:{src}', 'ConversationId': f'report:{src}', 'SentAt': ago(hours=2), 'ExternalId': 'r1'})}
    funnel.settle(s, f"msg:{m['read']}", 'surfaced', 'owner', read=True)
    return tid, m

def chat(s): return [l for l in concierge.history(s, general.dock_task(s, 'owner')[0]['TaskId']) if l.get('role') == 'assistant']


def test_every_hit_search_lists_opens_as_itself(s):
    tid, m = shapes(s)
    hits = search.everything(s, 'lanyard')['hits']
    by = {h['mid']: h for h in hits if h.get('mid')}
    assert set(m.values()) <= set(by), 'Search lists every shape'
    task = next(h for h in hits if h.get('type') == 'task' and h['tid'] == tid)
    out = railwalk.open(s, f"task:{task['tid']}")
    assert out['item'] and out['item'].get('tid') == tid
    bad = {}
    for name, mid in m.items():
        out = railwalk.open(s, f'msg:{mid}')                      # the key the page sends for a message hit (keyForRow)
        if (out.get('item') or {}).get('mid') != mid: bad[name] = (out.get('item') or {}).get('key') or out.get('say')
    assert not bad, f'picks that did not open what was picked: {bad}'
    assert not any("can't find" in (l.get('text') or l.get('content') or '') for l in chat(s))


def test_a_message_that_is_gone_says_so_once_and_never_as_cant_find(s):
    """A hit whose message was deleted between the search and the pick: one plain line, never the "older than what I keep" guess."""
    out = railwalk.open(s, 'msg:987654')
    assert out['item'] is None and "can't find" not in out['say'] and 'older than what I keep' not in out['say']
    railwalk.open(s, 'msg:987654')
    assert sum(out['say'] in (l.get('text') or l.get('content') or '') for l in chat(s)) == 1

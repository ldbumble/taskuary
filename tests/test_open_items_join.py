"""Different tasks from different sources can be joined (the owner, 2026-11-04: "I thought we went through this already"). A follow-up
from a THIRD party - another thread, another sender, no shared number - was never put in front of triage beside the task it belongs to:
only structure tied an arrival to open work, and matching by meaning needs an embedder the install may not have. Now every arrival is
shown a compact list of the owner's open tasks and Watching items (context.open_items) and the model joins by meaning, or does not."""
import json, re, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import batch, context, ingest
from taskuary.store import MemoryStore
from tests import fake_embed

ALEX, GAIL, PORTAL, ONBOARD = 'alex@northwind.example', 'gail@northwind.example', 'support@vendor.example', 'welcome@payworth.example'


def brain(seen, topic):
    "Stands in for the model: names a task about `topic` - only one the prompt listed, so a join needs the list to have shown it."
    def llm(system, user, **k):
        seen.append(user)
        j, out = json.loads(user), {'intent': 'watch', 'why': 'someone else handles it', 'title': 'Vendor portal', 'summary': 'About the portal.'}
        hit = [int(m) for l in j.get('open_items') or [] if topic in l.lower() for m in re.findall(r'\(tid (\d+)\)', l)]
        if hit: out['same_as'] = hit[0]
        return json.dumps(out)
    return llm


def arrive(s, llm, ext, conv, frm, name, to, subject, body):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': frm, 'from_name': name, 'to': to, 'cc': [],
                                         'conversation_id': conv, 'subject': subject, 'body': body, 'sent_at': '2026-11-04 10:28:00'}, llm=llm)


class OpenItemsJoinTests(unittest.TestCase):
    def setUp(self):
        cm = fake_embed.no_embedder(); cm.__enter__(); self.addCleanup(cm.__exit__, None, None, None)
        self.s = MemoryStore(); self.s.set_setting('owner_email', ALEX, 't')
        self.tid = arrive(self.s, brain([], 'portal'), 'r', 'thread-A', GAIL, 'Gail Moreno', [PORTAL, ALEX], 'Access to the vendor portal',
                          'Hi, could you set me up with a login to the vendor portal so I can download the invoices? Thanks, Gail')['task_id']
        self.assertTrue(self.tid)

    def test_a_third_partys_follow_up_on_a_new_thread_joins_the_watched_item(self):
        seen = []
        r = arrive(self.s, brain(seen, 'portal'), 'c', 'thread-B', ONBOARD, 'Payworth Onboarding', [ALEX], 'Welcome aboard',
                   'Good news: the portal account you requested for your team is now active. Sign in from the welcome page.')
        items = json.loads(seen[-1]).get('open_items') or []
        self.assertTrue(any(f'(tid {self.tid})' in l for l in items), 'the watched item is in front of triage')
        self.assertNotIn('open_work', json.loads(seen[-1]), 'nothing structural tied them - the list is the only evidence')
        self.assertEqual(r['task_id'], self.tid)
        self.assertEqual(len(self.s.list_tasks()), 1)

    def test_a_different_matter_is_shown_the_list_and_still_not_joined(self):
        seen = []
        r = arrive(self.s, brain(seen, 'lunch'), 'l', 'thread-C', 'ray@northwind.example', 'Ray Colton', [ALEX], 'Friday',
                   'Lunch on Friday with the auditors? Ray')
        self.assertTrue(any(f'(tid {self.tid})' in l for l in json.loads(seen[-1]).get('open_items') or []))
        self.assertNotEqual(r['task_id'], self.tid)
        self.assertEqual(len(self.s.list_tasks()), 2)


class OpenItemsBoundTests(unittest.TestCase):
    def test_bounded_newest_first_and_no_closed_work(self):
        s = MemoryStore()
        tids = [s.create_task({'Title': f'Task number {i} about something', 'Summary': f'what task {i} asks'}, 'owner') for i in range(context.OPEN_ITEMS + 10)]
        for t, st in zip(tids[-2:], ('done', 'dropped')): s._exec('UPDATE task SET Status=? WHERE TaskId=?', (st, t))
        got = context.open_items(s, skip={tids[-3]})
        shown = [int(re.search(r'\(tid (\d+)\)', l)[1]) for l in got]
        self.assertEqual(len(got), context.OPEN_ITEMS)
        self.assertFalse({*tids[-3:]} & {*shown}, 'skipped, done and dropped are left out')
        self.assertTrue(all(len(l) <= context.OPEN_ITEM_CHARS for l in got))



def finder(seen, topic, intent='task'):
    "Stands in for the model: names a task about `topic` only from what the owner's search found and showed it."
    def llm(system, user, **k):
        seen.append(user)
        j, out = json.loads(user), {'intent': intent, 'why': 'new work on it', 'title': 'Trainly licence seats', 'summary': 'About the Trainly seats.', 'kind': 'task'}
        hit = [int(m) for l in j.get('found_by_search') or [] if topic in l.lower() for m in re.findall(r'\(tid (\d+)\)', l)]
        if hit: out['same_as'] = hit[0]
        return json.dumps(out)
    return llm


class ClosedTaskFoundTests(unittest.TestCase):
    "A task closed last week is past recent_closures' days and shares no thread, sender or number with the follow-up: search finds it."
    def setUp(self):
        cm = fake_embed.no_embedder(); cm.__enter__(); self.addCleanup(cm.__exit__, None, None, None)
        self.s = MemoryStore(); self.s.set_setting('owner_email', ALEX, 't')
        self.tid = arrive(self.s, finder([], 'trainly'), 'q', 'thread-T', GAIL, 'Gail Moreno', [ALEX], 'Trainly licence seats for finance',
                          'Can we add three Trainly licence seats for the finance team before the quarter starts?')['task_id']
        self.s.update_task(self.tid, {'Status': 'done'}, 'owner')
        ago = lambda d: (datetime.now() - timedelta(days=d, hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        self.s._exec('UPDATE task SET ClosedAt=?, UpdatedAt=?, CreatedAt=? WHERE TaskId=?', (ago(7), ago(7), ago(9), self.tid))

    def test_a_follow_up_from_a_new_sender_finds_joins_and_reopens_it(self):
        seen = []
        r = arrive(self.s, finder(seen, 'trainly'), 'f', 'thread-U', 'billing@trainly.example', 'Trainly Billing', [ALEX], 'Your Trainly renewal',
                   'The renewal for your Trainly licence seats is due. Please confirm the seat count so we can issue the invoice.')
        found = json.loads(seen[-1]).get('found_by_search') or []
        self.assertTrue(any(f'(tid {self.tid})' in l and 'closed 7d ago' in l for l in found), found)
        self.assertNotIn('recently_closed', json.loads(seen[-1]), 'nothing but the search put it in front of triage')
        self.assertEqual(r['task_id'], self.tid)
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'open', 'new work owed on it brings it back')

    def test_nothing_owed_keeps_it_closed(self):
        r = arrive(self.s, finder([], 'trainly', 'fyi'), 'g', 'thread-V', 'billing@trainly.example', 'Trainly Billing', [ALEX], 'Trainly receipt',
                   'Receipt for your Trainly licence seats - nothing to do.')
        self.assertEqual(r['task_id'], self.tid)
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')

    def test_an_unrelated_mail_is_not_joined(self):
        seen = []
        r = arrive(self.s, finder(seen, 'trainly'), 'h', 'thread-W', 'ray@northwind.example', 'Ray Colton', [ALEX], 'Parking',
                   'The garage is closed on Monday for repairs, park on the street.')
        self.assertFalse(any(f'(tid {self.tid})' in l for l in json.loads(seen[-1]).get('found_by_search') or []))
        self.assertNotEqual(r['task_id'], self.tid)
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')


def shown(j) -> list:
    "Every task the prompt put in front of triage, as (tid, what it says) - from the one-line lists and the structured ones alike."
    out = [(int(m), l) for k in ('open_items', 'found_by_search') for l in j.get(k) or [] for m in re.findall(r'\(tid (\d+)\)', l)[:1]]
    ws = [w for k in ('open_work', 'room_tasks', 'open_goals') for w in j.get(k) or [] if isinstance(w, dict) and w.get('tid')]
    if (j.get('thread_task') or {}).get('tid'): ws.append(j['thread_task'])
    return out + [(int(w['tid']), json.dumps(w)) for w in ws]


def reader(seen, topic):
    "Stands in for the model: joins the task whose shown words carry `topic`, else opens its own."
    def llm(system, user, **k):
        seen.append(user)
        j = json.loads(user)
        out = {'intent': 'task', 'kind': 'task', 'why': 'work on the portal', 'title': 'Portal chat', 'summary': 'About the portal.'}
        hit = [t for t, txt in shown(j) if topic in txt.lower()]
        room = {int(w['tid']) for w in j.get('room_tasks') or [] if isinstance(w, dict) and w.get('tid')}
        # the room's own task is joined as its ask (same_problem); another source's by same_as - as triage is told to
        if hit and hit[0] in room: out.update(relationship='continues', existing_task_id=hit[0], same_problem=True)
        elif hit: out['same_as'] = hit[0]
        return json.dumps(out)
    return llm


def gh_pr(s, repo, n, title):
    return s.add_message({'ExternalId': f'gh:{repo}#{n}@r1', 'ConversationId': f'gh:{repo}#{n}', 'Channel': 'github', 'SourceName': repo,
                          'Subject': f'{repo}#{n} {title}', 'FromName': 'outside-dev', 'SentAt': '2026-11-04 09:50:00',
                          'BodyText': f'[pull request by outside-dev - association: FIRST_TIMER]\n{title}.', 'Status': 'triaging',
                          'SourceLink': f'https://github.com/{repo}/pull/{n}'})


def chat(s, llm, ext, body, at):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'whatsapp', 'conversation_id': 'whatsapp:1203630001@g.us',
                                         'source_name': 'Portal team', 'from_email': 'whatsapp:15550001', 'from_name': 'Erin Blake',
                                         'subject': '', 'body': body, 'sent_at': at}, llm=llm)


class BatchJoinsChatTests(unittest.TestCase):
    """A pull request lets in as a batch ("1 pull request on <repo>"), then a chat links it, then the same chat writes on the same
    fix: one matter from two sources in three polls (2026-11-04). The batch's title and summary say only how many it holds, and
    open_items read it as the owner's own, so the chat line could not be seen to be about it and opened a second task."""
    def setUp(self):
        cm = fake_embed.no_embedder(); cm.__enter__(); self.addCleanup(cm.__exit__, None, None, None)
        self.s = MemoryStore(); self.s.set_setting('owner_email', ALEX, 't')
        mid = gh_pr(self.s, 'northwind/portal', 41, 'Fix chat message loss on the first delivery')
        self.tid = batch.create(self.s, 'github', 'northwind/portal', [self.s.get_message(mid)])

    def test_the_batch_is_shown_by_what_it_holds_and_where_it_came_from(self):
        line = next(l for l in context.open_items(self.s) if f'(tid {self.tid})' in l)
        self.assertIn('#41 Fix chat message loss', line)
        self.assertNotIn('yours', line, "a stranger sent it - it is not the owner's own")
        self.assertIn('outside-dev', line)

    def test_a_chat_link_to_the_pr_and_a_later_line_on_the_fix_join_the_batch(self):
        seen = []
        r1 = chat(self.s, reader(seen, '#41'), 'w1', 'https://github.com/northwind/portal/pull/41 says it is fixed', '2026-11-04 09:53:00')
        self.assertEqual(r1['task_id'], self.tid, seen and json.loads(seen[-1]).get('open_items'))
        r2 = chat(self.s, reader(seen, 'message loss'), 'w2', 'still losing the first message after the update', '2026-11-04 09:56:00')
        self.assertEqual(r2['task_id'], self.tid)
        self.assertEqual(len(self.s.list_tasks()), 1)


if __name__ == '__main__': unittest.main()

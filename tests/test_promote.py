"""RULE PROMOTION (promote.py): a learned pattern clear-cut enough to be a rule is asked ONCE, as a yes/no on the rail's Advisor row -
yes makes the rule through the one create path, tagged as learned; no is remembered until the evidence grows GROW-fold. Never for
a colleague, never for anyone the owner has written to, never when a rule already covers them. Invented people only."""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import assistant, policy, promote, server
from taskuary.store import MemoryStore

NEWS, ALERTS = 'newsletter@vendor.example', 'alerts@vendor.example'


def _store():
    s = MemoryStore()
    s.set_setting('owner_email', 'alex@northwind.example', 'test'); s.set_setting('calendar_enabled', '0', 'test')
    return s


def mails(s, em, n, down=0, cls='automated', start=0):
    """n threads from `em`, the first `down` of them put down by the owner (Not ours writes an owner ignore route)."""
    mids = []
    for i in range(start, start + n):
        mid = s.add_message({'ConversationId': f'email:{em}:{i}', 'Channel': 'email', 'Subject': f'Issue {i}', 'FromEmail': em,
                             'FromName': em.split('@')[0], 'BodyText': 'news', 'Status': 'filed', 'SenderClass': cls})
        if i - start < down:
            s.set_message_status(mid, 'ignored'); s.add_route(mid, None, 'ignore', None, 'not ours - their newsletter', [], 'owner')
        mids.append(mid)
    return mids


def urgent(s, em, n):
    for i in range(n):
        t = s.create_task({'Title': f'Disk alert {i}', 'Status': 'open'}, 'triage')
        s.add_message({'ConversationId': f'email:alert:{i}', 'Channel': 'email', 'Subject': f'Disk alert {i}', 'FromEmail': em,
                       'BodyText': 'disk at 95%', 'Status': 'routed', 'TaskId': t, 'SenderClass': 'automated'})
        s.audit('task', t, 'priority', 'owner', detail={'from': 'normal', 'to': 'urgent'})


class Promotion(unittest.TestCase):
    def test_every_mail_put_down_is_one_question_with_a_rule_behind_it(self):
        s = _store(); mails(s, NEWS, 12, down=12)
        got = promote.ideas(s)
        self.assertEqual(len(got), 1)
        c = got[0]
        self.assertEqual((c['key'], c['kind']), (f'rule:sender:{NEWS}', 'rule'))
        self.assertIn(f"You've put down all 12 mails from {NEWS} and acted on none", c['text'])
        self.assertTrue(c['text'].rstrip().endswith('(Rules run before the AI.)') and '?' in c['text'], 'a question, not a task')
        p = c['action']['policy']
        self.assertEqual((p['Kind'], p['Pattern'], p['Action']), ('sender', NEWS, 'ignore'))     # 12 < SKIP_AT: filed, still visible
        self.assertIn('(learned)', p['Name']); self.assertTrue(p['Reason'].startswith('promoted from learning'))

    def test_under_the_threshold_nothing_is_asked(self):
        s = _store(); mails(s, NEWS, 12, down=promote.IGNORE_AT - 1)
        self.assertEqual(promote.ideas(s), [])

    def test_one_mail_taken_up_means_no_rule(self):
        s = _store(); mids = mails(s, NEWS, 12, down=11)
        s.add_memory({'Scope': 'sender', 'ScopeKey': NEWS, 'Source': 'verdict', 'Active': 1, 'CreatedBy': 'owner',
                      'Note': f'2026-10-01: "Issue 11" from {NEWS} - MADE A TASK: triage filed it, but the owner promoted it as real work'})
        self.assertEqual(promote.ideas(s), [], f'{mids[-1]} was taken up')

    def test_never_for_a_colleague(self):
        s = _store(); mails(s, 'erin@northwind.example', 12, down=12, cls='person')
        self.assertEqual(promote.ideas(s), [])
        s.set_setting('team_domains', 'northwind-labs.example', 'test'); mails(s, 'ray@northwind-labs.example', 12, down=12, cls='person')
        self.assertEqual(promote.ideas(s), [])

    def test_never_for_anyone_the_owner_has_written_to(self):
        s = _store(); mails(s, 'gail@vendor.example', 30, down=30, cls='person')
        s.add_message({'ConversationId': 'email:gail@vendor.example:3', 'Channel': 'email', 'Subject': 'Re: Issue 3', 'FromEmail': 'alex@northwind.example',
                       'BodyText': 'thanks Gail', 'Status': 'context', 'Direction': 'out'})
        self.assertEqual(promote.ideas(s), [], 'replied once is never a rule - and never a skip')

    def test_skip_only_for_an_automated_flood(self):
        s = _store(); mails(s, NEWS, 25, down=25)
        self.assertEqual(promote.ideas(s)[0]['action']['policy']['Action'], 'skip')
        self.assertIn('never reach you', promote.ideas(s)[0]['text'])
        s2 = _store(); mails(s2, 'paula@vendor.example', 25, down=25, cls='person')
        self.assertEqual(promote.ideas(s2)[0]['action']['policy']['Action'], 'ignore', 'a person is filed, never hidden')

    def test_a_rule_already_covering_them_asks_nothing(self):
        s = _store(); mails(s, NEWS, 12, down=12)
        s.save_policy({'Name': 'vendor', 'Kind': 'sender_domain', 'Pattern': 'vendor.example', 'Action': 'ignore', 'Reason': 'x', 'Active': 1}, 'owner')
        self.assertEqual(promote.ideas(s), [])

    def test_escalated_by_hand_every_time(self):
        s = _store(); urgent(s, ALERTS, promote.ESCALATE_AT)
        c = promote.ideas(s)[0]
        self.assertEqual(c['action']['policy']['Action'], 'escalate')
        self.assertIn(f"You've marked urgent all 5 tasks from {ALERTS}", c['text'])
        s2 = _store(); urgent(s2, ALERTS, promote.ESCALATE_AT); mails(s2, ALERTS, 1, down=1, start=99)
        self.assertEqual(promote.ideas(s2), [], 'one of theirs put down: not always urgent')

    def test_a_domain_of_machines_is_one_question(self):
        s = _store()
        for em in ('billing@mail.vendor.example', 'promo@mail.vendor.example', 'news@mail.vendor.example'): mails(s, em, 4, down=4)
        got = promote.candidates(s)
        self.assertEqual([c['key'] for c in got], ['rule:sender_domain:mail.vendor.example'])
        mails(s, 'omar@mail.vendor.example', 1, cls='person')
        self.assertEqual(promote.candidates(s), [], 'a person on the domain: no domain rule')

    def test_no_is_remembered_until_the_evidence_triples(self):
        s = _store(); mails(s, NEWS, 12, down=12)
        c = promote.ideas(s)[0]
        i = s.upsert_idea(c, '2026-10-20 08:00:00')
        assistant.act(s, i['IdeaId'], 'dismiss')
        mails(s, NEWS, 20, down=20, start=12)                 # 32 < 3 x 12
        self.assertEqual(promote.ideas(s), [])
        mails(s, NEWS, 4, down=4, start=32)                   # 36 = 3 x 12
        self.assertEqual(promote.ideas(s)[0]['sig'], '36')

    def test_one_question_open_at_a_time(self):
        s = _store(); mails(s, NEWS, 12, down=12); mails(s, 'promo@other.example', 9, down=9)
        s.upsert_idea(promote.ideas(s)[0], '2026-10-20 08:00:00')
        self.assertEqual(promote.ideas(s), [])

    def test_no_more_ideas_like_this_stops_rule_questions(self):
        s = _store(); mails(s, NEWS, 12, down=12); mails(s, 'promo@other.example', 9, down=9)
        i = s.upsert_idea(promote.ideas(s)[0], '2026-10-20 08:00:00')
        assistant.act(s, i['IdeaId'], 'dismiss_kind')
        self.assertEqual(promote.ideas(s), [])

    def test_yes_makes_the_rule_through_the_one_path_tagged_learned(self):
        s = _store(); mails(s, NEWS, 12, down=12)
        i = s.upsert_idea(promote.ideas(s)[0], '2026-10-20 08:00:00')
        out = assistant.act(s, i['IdeaId'], 'rule')
        p = next(x for x in s.list_policies() if x['PolicyId'] == out['policyId'])
        self.assertEqual((p['Kind'], p['Pattern'], p['Action'], p['CreatedBy']), ('sender', NEWS, 'ignore', 'owner'))
        a = s._one("SELECT Detail FROM audit WHERE EntityType='policy' AND Action='create'")
        d = json.loads(a['Detail'])
        self.assertEqual((d['via'], d['promoted_from'], d['idea']), ('advisor-rule', 'learning', i['IdeaId']))
        self.assertEqual(s.get_idea(i['IdeaId'])['Status'], 'done')
        self.assertEqual(policy.evaluate({'from_email': NEWS}, s.list_policies())['action'], 'ignore')
        self.assertEqual(promote.ideas(s), [], 'covered now')

    def test_the_post_raises_it_without_a_model_and_triage_never_opens_work_for_it(self):
        s = _store(); mails(s, NEWS, 12, down=12)
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            out = assistant.run(s, llm=None, force=True)
        rule = [l for l in out.get('lines') or [] if l['kind'] == 'rule']
        self.assertEqual(len(rule), 1, out.get('lines'))
        i = s.get_idea(rule[0]['id'])
        tri = json.loads(i['ActionJson'])['triage']
        self.assertEqual(tri['intent'], 'fyi'); self.assertFalse(tri.get('pending'))
        self.assertFalse([t for t in s.list_tasks() if 'rule' in str(t.get('Title') or '').lower()])

    def test_the_endpoint_says_yes_and_the_owners_urgent_mark_is_audited(self):
        s = _store(); mails(s, NEWS, 12, down=12)
        i = s.upsert_idea(promote.ideas(s)[0], '2026-10-20 08:00:00')
        t = s.create_task({'Title': 'Disk alert', 'Status': 'open'}, 'triage')
        with mock.patch.object(server, 'store', s):
            c = TestClient(server.app)
            self.assertTrue(c.post(f"/api/assistant/ideas/{i['IdeaId']}/rule", json={}).json()['policyId'])
            c.patch(f'/api/tasks/{t}', json={'Priority': 'urgent'})
        a = s._one("SELECT Detail FROM audit WHERE EntityType='task' AND Action='priority'")
        self.assertEqual(json.loads(a['Detail'])['to'], 'urgent')


if __name__ == '__main__': unittest.main()

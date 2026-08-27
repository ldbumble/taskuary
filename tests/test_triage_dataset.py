"""Triage, replayed against what really happened.

tests/data/triage_seed.jsonl is a hand-written set in the shape evalset.build produces; the
owner's own set (taskuary --evalset share -> tests/data/triage_cases.jsonl, people and prose
removed) is replayed too whenever it is on the machine. Every case is one inbound item with
the thread as it stood, the To/Cc relationship where known, and the owner's eventual verdict.

Each case is pushed through ingest_message with an ORACLE classifier - one that answers with
the owner's label. That takes the model out of the picture and tests everything around it,
which is where "always wrong even after memory" actually lived:
  - the deterministic layers must not overrule the verdict: no keyword short-circuit filing a
    real ask, no standing verdict eating something the owner later called work
  - the classifier must be TOLD the facts the case carries - a colleague already replied, the
    owner was in cc, thirty people were on it - because a model cannot weigh what it never saw
  - a verdict the owner already gave on the conversation must decide before a model is asked

The model's own accuracy over the full-text local cases is `taskuary --evalset evaluate`.
"""
import json, unittest
from pathlib import Path

from taskuary import evalset, ingest
from taskuary.store import MemoryStore

DATA = Path(__file__).parent / 'data'
OWNER = 'me@corp.example'


def cases():
    return evalset.read(DATA / 'triage_seed.jsonl') + [c for c in evalset.read(DATA / 'triage_cases.jsonl') if not c.get('weak')]


def stand_in_body(sig: dict) -> str:
    """A body that trips the same keyword checks the real one did - the shared set carries the
    signals, not the prose (evalset.body_signals)."""
    parts = ['Following up on the item below.']
    if sig.get('fyi_marker'): parts.append('This is an automated message.')
    if sig.get('act'): parts.append('Please add it to the system.')
    if sig.get('ask'): parts.append('Can you take a look')
    text = ' '.join(parts)
    return text.rstrip('.') + '?' if sig.get('question') else text


def replay(case: dict):
    """The case, arriving: the thread as it stood, the owner's mailbox known, any prior ruling
    on the conversation in place - then ingest_message with the oracle. Returns the store, the
    outcome, and what (if anything) the classifier was shown."""
    s = evalset.thread_store(case)
    s.save_source({'Channel': 'email', 'Address': OWNER, 'Owner': 'me', 'Active': 1}, 'test')
    for p in case.get('thread_before') or []:
        if p.get('from_kind') == 'owner' and p.get('from'):
            s.save_source({'Channel': 'email', 'Address': p['from'], 'Owner': 'me', 'Active': 1}, 'test')
    for n in case.get('notes_before') or []:
        s.add_memory({'Scope': n['scope'], 'ScopeKey': n.get('key'), 'Note': n['note'], 'Source': n.get('source', 'verdict'),
                      'Active': 1, 'CreatedBy': 'owner'})
    msg = evalset.as_message(case)
    if not msg['body']: msg['body'] = stand_in_body(case.get('body_signals') or {})
    if case.get('owner_ruled_thread_before'):
        # a chat ruling covers the SAME SENDER'S episode (store.owner_verdict_on_thread), so the
        # ruled line is this sender's own earlier one - a room-wide ruling was the 2026-08-27 bug
        prior = s.thread_messages(msg['conversation_id'])
        me = {(msg.get('from_email') or '').lower(), (msg.get('from_name') or '').lower()} - {''}
        mine = [p for p in prior if {(p.get('FromEmail') or '').lower(), (p.get('FromName') or '').lower()} & me]
        ruled = (mine or prior)[-1] if (mine or (prior and not str(msg['conversation_id']).startswith(('teams:', 'slack:', 'telegram:', 'whatsapp:')))) else None
        mid = ruled['MessageId'] if ruled else s.add_message({'ExternalId': f"{case['id']}-ruled", 'ConversationId': msg['conversation_id'],
                                                              'Channel': msg['channel'], 'Subject': msg['subject'], 'FromEmail': msg.get('from_email'),
                                                              'FromName': msg.get('from_name'), 'Status': 'ignored'})
        s.add_route(mid, None, 'ignore', None, 'nothing to do - filed by the owner, nothing learned', [], 'owner')
    seen = {}
    def oracle(sys_, usr_, **kw):
        seen['user'] = json.loads(usr_); seen['system'] = sys_
        return json.dumps({'intent': case['label'], 'why': 'oracle'})
    out = ingest.ingest_message(s, msg, llm=oracle)
    return s, out, seen


def _ident(p: dict) -> str: return (p.get('from') or p.get('from_name') or '').strip().lower()   # chats have names, not addresses


def colleagues_before(case: dict) -> list:
    return [p for p in case.get('thread_before') or [] if p.get('from_kind') != 'owner' and _ident(p) and _ident(p) != _ident(case)]


class ReplayTests(unittest.TestCase):
    def test_the_seed_is_present_and_well_formed(self):
        cs = evalset.read(DATA / 'triage_seed.jsonl')
        self.assertGreaterEqual(len(cs), 10)
        for c in cs:
            self.assertIn(c['label'], evalset.LABELS, c['id'])
            self.assertEqual(c['body_signals'] if 'body_signals' in c else evalset.body_signals(c['body']),
                             evalset.body_signals(c['body']), c['id'])

    def test_the_outcome_follows_the_owners_verdict_when_the_model_agrees(self):
        """With the model answering as the owner did, everything else in the funnel has to get
        out of the way - or file exactly what the owner filed."""
        for c in cases():
            if c.get('from_kind') == 'owner': continue                       # the owner's own mail is not triaged here
            if c['label'] != 'fyi' and (c.get('owner_ruled_thread_before') or c.get('notes_before')): continue   # a reversal: not this test's question
            with self.subTest(c['id'], label=c['label'], source=c['label_source']):
                s, out, seen = replay(c)
                if c['label'] == 'fyi':
                    self.assertIn(out['status'], ('filed', 'ignored', 'skipped'), f"{c['id']}: {out}")
                else:
                    self.assertEqual(out['status'], 'created',
                                     f"{c['id']}: the owner called this {c['label']} but the funnel {out['status']} it before/without the model "
                                     f"(model asked: {'user' in seen})")
                    kind = s.get_task(out['task_id'])['Kind']
                    if c['label'] == 'reply_only': self.assertEqual(kind, 'reply', c['id'])
                    else: self.assertNotEqual(kind, 'reply', c['id'])

    def test_the_classifier_is_told_who_already_spoke(self):
        """The signal lives in the messages AROUND the item. Whenever somebody other than the
        owner and the sender had already written on the thread, the prompt says so - and when
        nobody had, it does not invent it."""
        for c in cases():
            if c.get('from_kind') == 'owner': continue
            with self.subTest(c['id']):
                _, out, seen = replay(c)
                if 'user' not in seen: continue                                # decided before a model was needed
                if colleagues_before(c):
                    self.assertTrue(seen['user'].get('others_replied'), f"{c['id']}: a colleague spoke and the prompt did not say")
                    last = (c['thread_before'] or [])[-1]
                    self.assertEqual(seen['user'].get('last_on_thread_is_you'), last.get('from_kind') == 'owner', c['id'])
                else:
                    self.assertNotIn('others_replied', seen['user'], c['id'])

    def test_the_classifier_is_told_where_the_owner_stood_on_the_mail(self):
        for c in cases():
            if not c.get('addressed_to_you') or c.get('from_kind') == 'owner': continue
            with self.subTest(c['id']):
                _, out, seen = replay(c)
                if 'user' not in seen: continue
                self.assertEqual(seen['user'].get('addressed_to_you'), c['addressed_to_you'], c['id'])
                self.assertEqual(seen['user'].get('recipients'), c['recipients'], c['id'])

    def test_a_ruled_conversation_decides_without_a_model(self):
        for c in cases():
            if c['label'] != 'fyi' or not c.get('owner_ruled_thread_before'): continue
            with self.subTest(c['id']):
                _, out, seen = replay(c)
                self.assertEqual(out['status'], 'filed', c['id'])
                self.assertNotIn('user', seen, f"{c['id']}: the owner had already decided this, and a model was still asked")

    def test_a_standing_verdict_is_shown_to_the_model_as_evidence(self):
        """Verdicts about a topic or a sender no longer decide on their own (owner's call,
        2026-08-27): the model is asked, and told what the owner said on similar mail."""
        for c in cases():
            if not c.get('notes_before') or c.get('owner_ruled_thread_before'): continue
            with self.subTest(c['id']):
                _, out, seen = replay(c)
                self.assertIn('user', seen, f"{c['id']}: the model was not asked")
                self.assertIn('EVIDENCE', seen['system'], c['id'])
                for n in c['notes_before']: self.assertIn(n['note'][:40], seen['system'], c['id'])


class DatasetTests(unittest.TestCase):
    """The set is built from the owner's verdicts, and what leaves the machine carries no one."""
    def _store(self):
        s = MemoryStore()
        s.save_source({'Channel': 'email', 'Address': OWNER, 'Owner': 'me', 'Active': 1}, 'test')
        add = lambda i, **f: s.add_message({'ExternalId': f'e{i}', 'Channel': 'email', 'Status': 'filed', 'SentAt': f'2026-08-0{i} 09:00:00', **f})
        a = add(1, ConversationId='conv-a', Subject='Resident Refund Request - Doe, Jane', FromEmail='bo@facility.example',
                FromName='Bo Facility', BodyText='Attached is the refund request for Jane Doe.')
        s.add_route(a, None, 'create', 0.1, 'triage: reply_only - asks about a refund · new task', [], 'router')
        s.add_route(a, None, 'ignore', None, 'not ours - Priya handles refunds', [], 'owner')
        b = add(2, ConversationId='conv-a', Subject='Re: Resident Refund Request - Doe, Jane', FromEmail='priya@corp.example',
                FromName='Priya Colleague', BodyText='Processed, thanks.')
        s.add_route(b, None, 'file', None, 'triage: fyi - a colleague answered', [], 'triage')
        c_ = add(3, ConversationId='conv-c', Subject='Vendor Create', FromEmail='reports@vendor.example', FromName='Reports',
                 BodyText='FAILED: 3 rows', RecipientsJson=json.dumps({'to': [OWNER], 'cc': []}))
        tid = s.create_task({'Title': 'Vendor Create', 'Kind': 'coding'}, 'owner')
        s.add_route(c_, tid, 'create', None, 'promoted by the owner', [], 'owner')
        d = add(4, ConversationId='conv-d', Subject='PTO file', FromEmail='gw@corp.example', FromName='Gwen', BodyText='Do you have it?')
        rid = s.add_review({'TaskId': tid, 'MessageId': d, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'needs a reply'})
        s.decide_review(rid, 'approved', 'Yes, attached.', 'owner')
        e = add(5, ConversationId='conv-e', Subject='T&E system', FromEmail='fin@corp.example', FromName='Fin', BodyText='FYI only.')
        rid2 = s.add_review({'TaskId': tid, 'MessageId': e, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'needs a reply'})
        s.decide_review(rid2, 'no_reply', None, 'owner')
        # a Teams ask the owner dismissed the draft for - and then answered in the chat himself
        g = s.add_message({'ExternalId': 'e6', 'Channel': 'teams', 'Status': 'filed', 'SentAt': '2026-08-06 09:00:00', 'ConversationId': 'teams:19:dm',
                           'Subject': 'Teams chat with Priya', 'FromName': 'Priya Colleague', 'BodyText': 'Can you fix my timesheet?'})
        s.add_message({'ExternalId': 'e6-you', 'Channel': 'teams', 'Status': 'context', 'SentAt': '2026-08-06 09:40:00', 'ConversationId': 'teams:19:dm',
                       'Subject': 'Teams chat with Priya', 'FromName': 'You', 'BodyText': 'Done.'})
        rid3 = s.add_review({'TaskId': tid, 'MessageId': g, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'needs a reply'})
        s.decide_review(rid3, 'no_reply', None, 'owner')
        return s

    def test_labels_follow_the_owners_verdicts(self):
        cs = {c['id']: c for c in evalset.build(self._store())}
        self.assertEqual((cs['m1']['label'], cs['m1']['label_source']), ('fyi', 'owner:not_ours'))
        self.assertEqual((cs['m3']['label'], cs['m3']['label_source']), ('task', 'owner:promoted'))
        self.assertEqual((cs['m4']['label'], cs['m4']['label_source']), ('reply_only', 'review:approved'))
        self.assertEqual((cs['m5']['label'], cs['m5']['label_source']), ('fyi', 'review:no_reply'))
        self.assertEqual((cs['m6']['label'], cs['m6']['label_source']), ('reply_only', 'review:no_reply_answered_in_channel'))
        self.assertNotIn('m2', cs)                                            # untouched and fresh: no label yet
        self.assertEqual(cs['m3']['addressed_to_you'], 'to')
        self.assertEqual(cs['m1']['triage'], {'decision': 'create', 'intent': 'reply_only', 'by': 'router'})
        self.assertEqual(cs['m1']['from_kind'], 'external'); self.assertEqual(cs['m4']['from_kind'], 'internal')

    def test_the_thread_is_recorded_as_it_stood_and_a_ruling_on_it_is_known(self):
        s = self._store()
        f = s.add_message({'ExternalId': 'e9', 'Channel': 'email', 'Status': 'filed', 'SentAt': '2026-08-09 09:00:00', 'ConversationId': 'conv-a',
                           'Subject': 'Re: Resident Refund Request - Doe, Jane', 'FromEmail': 'bo@facility.example', 'FromName': 'Bo Facility'})
        s.add_route(f, None, 'ignore', None, 'nothing to do - filed by the owner, nothing learned', [], 'owner')
        c = next(x for x in evalset.build(s) if x['id'] == f'm{f}')
        self.assertEqual([p['from_kind'] for p in c['thread_before']], ['external', 'internal'])
        self.assertTrue(c['owner_ruled_thread_before'])

    def test_what_leaves_the_machine_carries_no_people_and_no_prose(self):
        s = self._store()
        raw = json.dumps(evalset.anonymise(evalset.build(s)), ensure_ascii=False).lower()
        for secret in ('bo@facility.example', 'priya@corp.example', 'gw@corp.example', 'facility', 'priya', 'gwen', 'jane', 'doe',
                       'attached is the refund', 'processed, thanks', 'do you have it'):
            self.assertNotIn(secret, raw, secret)
        for c in evalset.anonymise(evalset.build(s)):
            self.assertIsNone(c['body']); self.assertIsNone(c['to']); self.assertIsNone(c['cc'])
            self.assertTrue(c['from'] is None or c['from'].endswith('.example'))
            self.assertEqual(c['body_signals'], evalset.body_signals(next(x for x in evalset.build(s) if x['id'] == c['id'])['body']))

    def test_the_shared_set_if_present_is_anonymous(self):
        """The file the owner may commit: every address a pseudonym, every body gone."""
        for c in evalset.read(DATA / 'triage_cases.jsonl'):
            self.assertIsNone(c.get('body'), c['id'])
            for p in [c] + list(c.get('thread_before') or []):
                self.assertTrue(not p.get('from') or p['from'].endswith('.example'), (c['id'], p.get('from')))


if __name__ == '__main__':
    unittest.main()

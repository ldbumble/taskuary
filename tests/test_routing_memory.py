"""The funnel's loop, closed: a verdict is kept, the owner's correction is learned against it,
and the next message like it is judged with that in hand.

TQ-0501 is the case these guard. "Can you clock me out at 3:40 Thursday?" arrived on Teams, triage
judged it coding, an analyst opened a session in a bank-feeds checkout, and the owner reclassified
it with the kind control - the one door out of three that taught nothing. Every correction now
lands the same way whichever control it came through, and a stated fact never quietly grows to
cover a whole company.
"""
import unittest
from unittest import mock

from taskuary import ingest, routingmemory as rmem
from taskuary.store import MemoryStore


def store():
    s = MemoryStore()
    for k in ('coder_auto_enabled', 'learn_enabled'): s.set_setting(k, '0', 't')
    return s


def arrived(s, email='mgorelick@mfa.net', channel='teams', subject='Teams chat with Mindy Gorelick',
            kind='coding', title='Clock out Mindy at 3:40 Thursday'):
    """A task as triage left it, with the message it was judged from."""
    tid = s.create_task({'Title': title, 'Kind': kind, 'Source': channel}, 'router')
    s.add_message({'TaskId': tid, 'Channel': channel, 'FromEmail': email, 'Subject': subject,
                   'BodyText': 'can you clock me out at 3:40? thanks!', 'Direction': 'in'})
    return tid


class VerdictIsKept(unittest.TestCase):
    def test_a_created_task_keeps_what_triage_answered(self):
        s = store(); tid = arrived(s)
        s.add_route(1, tid, 'create', None, 'triage: task', [], 'triage',
                    verdict={'intent': 'task', 'kind': 'coding', 'repository': 'mfaVita/FanApp',
                             'profile': 'analyst', 'why': 'a system change beyond replying'})
        self.assertEqual(s.task_verdict(tid)['kind'], 'coding')
        self.assertEqual(s.task_verdict(tid)['repository'], 'mfaVita/FanApp')

    def test_a_task_routed_before_the_column_existed_has_none(self):
        s = store(); tid = arrived(s)
        s.add_route(1, tid, 'create', None, 'triage: task', [], 'triage')
        self.assertIsNone(s.task_verdict(tid))

    def test_the_newest_verdict_wins(self):
        s = store(); tid = arrived(s)
        s.add_route(1, tid, 'create', None, 'r', [], 'triage', verdict={'kind': 'coding'})
        s.add_route(2, tid, 'create', None, 'r', [], 'triage', verdict={'kind': 'general'})
        self.assertEqual(s.task_verdict(tid)['kind'], 'general')

    def test_a_broken_answer_still_reaches_the_diagnostic_panel_alone(self):
        # RawOutput raises the Timeline's "what did triage answer" box, so a SUCCESSFUL verdict
        # must never land there or every task wears an error face.
        s = store(); tid = arrived(s)
        s.add_route(1, tid, 'create', None, 'r', [], 'triage', verdict={'kind': 'coding'})
        self.assertIsNone(s.list_routes(tid)[0]['RawOutput'])


class ACorrectionIsLearned(unittest.TestCase):
    def test_one_correction_is_a_hypothesis_and_two_may_route(self):
        s = store()
        rmem.learn_correction(s, arrived(s), 'kind', 'task', 'owner')
        one = s.routing_facts('kind', [('sender', 'mgorelick@mfa.net')])[0]
        self.assertAlmostEqual(one['Confidence'], .72, places=2)
        rmem.learn_correction(s, arrived(s), 'kind', 'task', 'owner')
        two = s.routing_facts('kind', [('sender', 'mgorelick@mfa.net')])[0]
        self.assertAlmostEqual(two['Confidence'], .86, places=2)

    def test_pressing_the_same_button_twice_does_not_make_it_surer(self):
        s = store(); tid = arrived(s)
        self.assertTrue(rmem.learn_correction(s, tid, 'kind', 'task', 'owner'))
        self.assertEqual(rmem.learn_correction(s, tid, 'kind', 'task', 'owner'), 0)
        self.assertAlmostEqual(s.routing_facts('kind')[0]['Confidence'], .72, places=2)

    def test_the_owners_typed_answer_is_their_word_not_a_guess(self):
        s = store()
        rmem.learn_correction(s, arrived(s), 'system', 'ADP', 'owner')
        self.assertTrue(s.routing_facts('system')[0]['Confirmed'])

    def test_a_chat_room_is_never_the_key(self):
        # "Teams chat with Mindy Gorelick" is the ROOM. Keyed on it, the lesson would not fire on
        # the same ask from anyone else, and would damp a real bug she reports tomorrow.
        s = store()
        rmem.learn_correction(s, arrived(s), 'kind', 'task', 'owner')
        self.assertEqual({f['Signal'] for f in s.routing_facts('kind')}, {'sender', 'sender_domain'})

    def test_a_real_subject_is_a_key(self):
        s = store()
        rmem.learn_correction(s, arrived(s, email='r@hrtgcs.com', channel='email',
                                         subject='RE: Resident Refund Request - Henkin'), 'kind', 'task', 'owner')
        self.assertIn('subject', {f['Signal'] for f in s.routing_facts('kind')})

    def test_only_routing_fields_are_learnable(self):
        # title/summary/checklist corrections teach STYLE, which is LEARNED.md's job.
        with self.assertRaises(ValueError):
            rmem.learn_correction(store(), 1, 'summary', 'shorter please', 'owner')


class WhatTheNextVerdictIsTold(unittest.TestCase):
    def setUp(self):
        self.s = store()
        rmem.learn_correction(self.s, arrived(self.s), 'kind', 'task', 'owner')
        rmem.learn_correction(self.s, arrived(self.s), 'system', 'ADP', 'owner')
        self.her = {'FromEmail': 'mgorelick@mfa.net', 'Channel': 'teams', 'Subject': 'Teams chat with Mindy Gorelick'}
        self.colleague = {'FromEmail': 'someone@mfa.net', 'Channel': 'email', 'Subject': 'Budget question'}

    def test_the_sender_it_was_learned_from_is_told(self):
        got = {r['field']: r for r in rmem.facts_for(self.s, self.her)}
        self.assertEqual(got['kind']['value'], 'task')
        self.assertEqual(got['system']['value'], 'ADP')

    def test_one_correction_is_offered_as_tentative(self):
        self.assertTrue({r['field']: r for r in rmem.facts_for(self.s, self.her)}['kind']['tentative'])

    def test_a_colleague_is_not_covered_by_one_persons_correction(self):
        self.assertEqual(rmem.facts_for(self.s, self.colleague), [])

    def test_a_stated_fact_does_not_grow_to_cover_a_company(self):
        # "clocking in is ADP" being the owner's own words says nothing about whether everyone
        # at their company writes about clocking in.
        self.assertNotIn('system', {r['field'] for r in rmem.facts_for(self.s, self.colleague)})

    def test_a_company_earns_its_scope_from_repetition(self):
        for who in ('a@mfa.net', 'b@mfa.net'):
            rmem.learn_correction(self.s, arrived(self.s, email=who), 'kind', 'task', 'owner')
        got = {r['field']: r for r in rmem.facts_for(self.s, self.colleague)}
        self.assertEqual(got['kind']['seen_on'], 'sender_domain')
        self.assertFalse(got['kind']['tentative'])

    def test_a_stranger_is_told_nothing(self):
        self.assertEqual(rmem.facts_for(self.s, {'FromEmail': 'x@other.com', 'Channel': 'email', 'Subject': 'Hi'}), [])

    def test_the_more_specific_signal_answers_the_field(self):
        # a sender fact and a domain fact for the same field must not both be offered
        for who in ('a@mfa.net', 'b@mfa.net'):
            rmem.learn_correction(self.s, arrived(self.s, email=who), 'kind', 'general', 'owner')
        kinds = [r for r in rmem.facts_for(self.s, self.her) if r['field'] == 'kind']
        self.assertEqual(len(kinds), 1)
        self.assertEqual(kinds[0]['seen_on'], 'sender')


class EveryDoorTeaches(unittest.TestCase):
    def test_the_assistants_put_it_on_my_list_reclassifies_an_existing_task(self):
        # it used to return the task untouched: "already-routed messages keep the task they are on"
        s = store(); tid = arrived(s)
        mid = s.list_messages(tid)[0]['MessageId']
        self.assertEqual(ingest.task_from_message(s, mid, 'owner', kind='task'), tid)
        self.assertEqual(s.get_task(tid)['Kind'], 'task')
        self.assertEqual(s.routing_facts('kind')[0]['Value'], 'task')

    def test_a_closed_task_is_left_alone(self):
        s = store(); tid = arrived(s)
        s.update_task(tid, {'Status': 'done'}, 'owner')
        mid = s.list_messages(tid)[0]['MessageId']
        ingest.task_from_message(s, mid, 'owner', kind='task')
        self.assertEqual(s.get_task(tid)['Kind'], 'coding')


class TheKindControlTeaches(unittest.TestCase):
    """The door the owner actually reached for. It set the field and nothing else, while the tray
    button beside it reached the identical end state AND wrote the lesson (TQ-0501, 2026-09-11)."""

    def setUp(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        self.c, self.s = TestClient(server.app), server.store
        self.tid = arrived(self.s)

    def facts(self, field):
        return [f for f in self.s.routing_facts(field) if f['SignalKey'] == 'mgorelick@mfa.net']

    def test_changing_the_kind_to_task_is_a_verdict(self):
        self.assertEqual(self.c.patch(f'/api/tasks/{self.tid}', json={'Kind': 'task'}).status_code, 200)
        self.assertEqual([f['Value'] for f in self.facts('kind')], ['task'])

    def wrote(self, go):
        """Everything one door leaves behind, so "they teach the same thing" is checked against
        all of it and not just the half I happened to remember (routing evidence alone passed
        while the selector was still writing no memory line and no learned lesson at all)."""
        tid = arrived(self.s)
        mem = len(self.s.list_memories())
        facts = (self.facts('kind') or [{}])[0].get('EvidenceCount') or 0
        go(tid)
        return {'kind': self.s.get_task(tid)['Kind'],
                'memory': len(self.s.list_memories()) - mem,
                'operations': len(self.s.operations_for(tid) or []),
                'routing': ((self.facts('kind') or [{}])[0].get('EvidenceCount') or 0) - facts}

    def test_the_button_and_the_control_teach_the_same_thing(self):
        button = self.wrote(lambda tid: self.c.post(f'/api/tasks/{tid}/not-coding', json={'learn': True}))
        control = self.wrote(lambda tid: self.c.patch(f'/api/tasks/{tid}', json={'Kind': 'task'}))
        self.assertEqual(button, control)
        self.assertEqual(button['kind'], 'task')
        for what in ('memory', 'operations', 'routing'):
            self.assertGreater(button[what], 0, f'the verdict wrote no {what}')

    def test_moving_it_to_another_agent_is_a_weaker_signal(self):
        # general/coding is still agent work: the routing fact, not the not-for-the-agent verdict
        moved = self.wrote(lambda tid: self.c.patch(f'/api/tasks/{tid}', json={'Kind': 'general'}))
        self.assertEqual(moved['memory'], 0)

    def test_the_button_can_say_where_it_belongs(self):
        self.c.post(f'/api/tasks/{self.tid}/not-coding', json={'learn': True, 'belongs_to': 'ADP'})
        said = self.facts('system')
        self.assertEqual([f['Value'] for f in said], ['ADP'])
        self.assertTrue(said[0]['Confirmed'])

    def test_reassigning_the_worker_is_a_verdict_too(self):
        self.c.patch(f'/api/tasks/{self.tid}', json={'Assignee': 'agent:coder'})
        self.assertEqual([f['Value'] for f in self.facts('profile')], ['coder'])

    def test_an_unchanged_kind_teaches_nothing(self):
        self.c.patch(f'/api/tasks/{self.tid}', json={'Kind': 'coding', 'Priority': 'high'})
        self.assertEqual(self.facts('kind'), [])

    def test_a_failure_to_learn_never_fails_the_owners_change(self):
        with mock.patch('taskuary.routingmemory.learn_correction', side_effect=RuntimeError('boom')):
            self.assertEqual(self.c.patch(f'/api/tasks/{self.tid}', json={'Kind': 'task'}).status_code, 200)
        self.assertEqual(self.s.get_task(self.tid)['Kind'], 'task')


if __name__ == '__main__':
    unittest.main()


class OnlyTheLessonsReachThePrompt(unittest.TestCase):
    """LEARNED.md is two documents in one file: what triage should know, and what its human reader
    should. Only the first belongs in a prompt, and the second had been quietly crowding it out -
    900 characters of preamble plus a section header describing content that was stripped, against
    a 1500-character budget, so the learned rules were what got cut to make room."""

    DOC = ('# LEARNED.md - what the system has learned about {{owner_first}}\n\n'
           '_Taskuary writes this document itself, from your verdicts. Machine-written lines carry\n'
           'a `[s:N | ev: ... ]` tag. Edit anything; **SOUL.md always outranks this file.**_\n\n'
           '## What becomes a task\n'
           '- {{owner_first}} avoids tasks owned by other teams. [s:20 | ev: mem1 | seen: 2026-09-02]\n\n'
           '## Verdicts - the evidence\n'
           '_(every verdict you give, dated, with the sender and subject it was given on.)_\n'
           '<!-- verdicts:start -->\n- resident refunds are not ours [mem3]\n<!-- verdicts:end -->\n')

    def setUp(self):
        from taskuary import learn
        self.out = learn.injectable(self.DOC)

    def test_the_learned_rule_survives(self):
        self.assertIn('avoids tasks owned by other teams', self.out)

    def test_the_note_to_the_reader_does_not(self):
        self.assertNotIn('Taskuary writes this document itself', self.out)
        self.assertNotIn('SOUL.md always outranks', self.out)

    def test_the_title_is_kept(self):
        self.assertTrue(self.out.startswith('# LEARNED.md'))

    def test_a_gated_section_takes_its_explainer_with_it(self):
        # the header and its prose used to survive, describing a block that had been stripped
        self.assertNotIn('every verdict you give', self.out)
        self.assertNotIn('Verdicts - the evidence', self.out)
        self.assertNotIn('resident refunds are not ours', self.out)

    def test_a_document_with_no_preamble_is_left_alone(self):
        from taskuary import learn
        plain = '# LEARNED.md\n\n## What becomes a task\n- a rule [s:2 | ev: mem1 | seen: x]\n'
        self.assertIn('- a rule', learn.injectable(plain))
        self.assertTrue(learn.injectable(plain).startswith('# LEARNED.md'))

    def test_nothing_at_all_is_still_nothing(self):
        from taskuary import learn
        self.assertEqual(learn.injectable(''), '')


class LearnedSeesEveryCorrection(unittest.TestCase):
    """Five routing corrections; LEARNED.md used to hear about one of them, vaguely. The verdict
    being on file is what lets a lesson say what was overturned instead of naming a field."""

    def setUp(self):
        self.s = store(); self.tid = arrived(self.s)
        self.s.add_route(1, self.tid, 'create', None, 'r', [], 'triage',
                         verdict={'intent': 'task', 'kind': 'coding', 'profile': 'analyst',
                                  'repository': 'mfaVita/FanApp'})

    def said(self, field, value, belongs_to=None, ev=None):
        return rmem.lesson(self.s, self.tid, field, value, belongs_to, ev)

    def test_it_names_what_triage_had_answered(self):
        self.assertIn('triage said coding', self.said('kind', 'task'))
        self.assertIn('triage said analyst', self.said('profile', 'coder'))
        self.assertIn('mfaVita/FanApp', self.said('repository', 'mfaVita/TopE'))

    def test_a_kind_says_what_the_kind_MEANS(self):
        # "kind: coding -> task" is a diff; only a sentence about who works it is a lesson
        self.assertIn("owner's own list", self.said('kind', 'task'))
        self.assertIn('assistant', self.said('kind', 'general'))

    def test_where_it_belongs_rides_along(self):
        self.assertIn('it belongs to ADP', self.said('kind', 'task', 'ADP'))

    def test_the_system_lesson_says_it_is_not_a_repository(self):
        self.assertIn('not a repository here', self.said('system', 'ADP'))

    def test_the_evidence_key_points_at_a_readable_line(self):
        # LEARNED.md tags lessons [ev: mem7]; learn._resolve only understands mem/rv/task ids
        self.assertTrue(self.said('kind', 'task', None, 'mem7').startswith('mem7:'))
        self.assertTrue(self.said('kind', 'task').startswith(f'task{self.tid}:'))

    def test_a_task_with_no_verdict_still_reads_as_a_sentence(self):
        bare = self.s.create_task({'Title': 'Investigate T&E setup', 'Kind': 'coding'}, 'router')
        said = rmem.lesson(self.s, bare, 'kind', 'task')
        self.assertIn('the owner made it task', said)
        self.assertNotIn('triage and', said)
        self.assertNotIn('triage said  ', said)


class TheAssistantCanTeachToo(unittest.TestCase):
    """What the chat can already set, and what it writes when it reclassifies something."""

    def test_a_fact_the_owner_tells_the_assistant_reaches_triage(self):
        from taskuary import concierge
        s = store()
        concierge.remember_fact(s, 'Clocking in and out is ADP - we hold no code for it, so timesheet asks are never coding')
        notes = ingest.notes_for(s, {'from_email': 'anyone@example.com', 'subject': 'my timesheet', 'body': 'fix my hours'})
        self.assertTrue(any('ADP' in str(n) for n in notes), 'a global fact must reach every verdict')

    def test_reclassifying_from_the_chat_writes_both_memories(self):
        from unittest import mock
        s = store(); tid = arrived(s)
        mid = s.list_messages(tid)[0]['MessageId']
        with mock.patch('taskuary.ingest._spawn') as spawned:
            ingest.task_from_message(s, mid, 'owner', kind='task')
        self.assertEqual(s.routing_facts('kind')[0]['Value'], 'task')          # the precise one
        said = spawned.call_args[0][2] if spawned.call_args else ''
        self.assertIn('the owner made it task', said)                          # ...and the general one

    def test_it_teaches_once_not_on_every_repeat(self):
        from unittest import mock
        s = store(); tid = arrived(s)
        mid = s.list_messages(tid)[0]['MessageId']
        ingest.task_from_message(s, mid, 'owner', kind='task')
        with mock.patch('taskuary.ingest._spawn') as spawned:
            ingest.task_from_message(s, mid, 'owner', kind='task')
        self.assertFalse(spawned.called, 'a repeat must not spend an AI call restating a known lesson')

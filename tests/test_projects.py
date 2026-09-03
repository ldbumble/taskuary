"""Project relationships: explicit repo choices teach; guesses only consume the evidence."""
import json
import unittest

from taskuary import docsync, projects, terminal
from taskuary.ingest import judge
from taskuary.store import MemoryStore


class ProjectRelationshipTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.s.save_doc('soul', '# SOUL.md\n\nOwner prose.\n\n## Repository map\n'
                                     '- **noble/app**: Noble customer operations\n'
                                     '- **other/payroll**: payroll and timesheets\n', 'owner')

    def task(self, sender='rene@noble.example', name='Rene Gomez', channel='email', body='Please fix Noble', repo=None):
        tid = self.s.create_task({'Title': body, 'Summary': body, 'Kind': 'coding',
                                  **({'Tags': f'repo:{repo}'} if repo else {})}, 'owner')
        self.s.add_message({'TaskId': tid, 'ExternalId': f'{channel}:{tid}', 'Channel': channel,
                            'FromName': name, 'FromEmail': sender, 'Subject': body,
                            'ConversationId': f'{channel}:{sender}', 'BodyText': body})
        return tid

    def test_two_explicit_choices_promote_a_sender_relationship(self):
        first = self.task(repo='noble/app')
        projects.learn_task_repository(self.s, first, 'noble/app')
        future = self.task(body='A fresh request with no repository words')
        self.assertEqual(projects.repositories_for_task(self.s, future)[0], [])

        second = self.task(repo='noble/app')
        projects.learn_task_repository(self.s, second, 'noble/app')
        repos, why = projects.repositories_for_task(self.s, future)
        self.assertEqual(repos, ['noble/app'])
        self.assertIn('2 owner repository choices', why)

    def test_repository_picker_is_the_learning_door(self):
        from taskuary import server
        original = server.store
        server.store = self.s
        try:
            for _ in range(2):
                tid = self.task()
                server.set_task_repo(tid, server.RepoBody(repo='noble/app'))
            future = self.task(body='Please check the latest problem')
            self.assertEqual(projects.repositories_for_task(self.s, future)[0], ['noble/app'])
            self.assertIn('Rene Gomez (email)', self.s.get_doc('soul'))
        finally:
            server.store = original

    def test_startup_history_is_idempotent(self):
        self.task(repo='noble/app'); self.task(repo='noble/app')
        self.assertEqual(projects.backfill(self.s), 2)
        self.assertEqual(projects.backfill(self.s), 0)
        identity = next(x for x in self.s.project_links(kind='email') if x['Value'] == 'rene@noble.example')
        self.assertEqual(identity['EvidenceCount'], 2)

    def test_a_correction_replaces_what_the_task_taught(self):
        tid = self.task(repo='noble/app')
        projects.learn_task_repository(self.s, tid, 'noble/app')
        self.s.clear_project_evidence(tid)
        projects.learn_task_repository(self.s, tid, 'other/payroll')
        links = [(x['ProjectName'], x['Value']) for x in self.s.project_links(kind='email')]
        self.assertEqual(links, [('other/payroll', 'rene@noble.example')])

    def test_relationship_beats_unrelated_word_similarity_when_it_is_mature(self):
        for _ in range(2):
            tid = self.task(body='Noble request', repo='noble/app')
            projects.learn_task_repository(self.s, tid, 'noble/app')
        incoming = self.task(body='Payroll timesheet failure')
        profile = {'cwd_map': {'noble/app': 'C:/src/noble', 'other/payroll': 'C:/src/payroll'}}
        self.assertEqual(terminal.guess_repo(self.s, incoming, profile),
                         ('noble/app', 'learned from 2 owner repository choices for Rene Gomez'))

    def test_triage_receives_only_the_matching_project_context(self):
        for _ in range(2):
            tid = self.task(repo='noble/app')
            projects.learn_task_repository(self.s, tid, 'noble/app')
        seen = {}
        msg = {'channel': 'email', 'from_name': 'Rene Gomez', 'from_email': 'rene@noble.example',
               'subject': 'Question', 'body': 'Can you check the latest item?'}
        def brain(system, user, **_kwargs):
            seen.update(system=system, user=json.loads(user))
            return '{"intent":"task","kind":"coding","why":"requires a check"}'
        out, _ = judge(self.s, msg, brain)
        self.assertEqual(out['intent'], 'task')
        self.assertEqual(seen['user']['project_context']['project'], 'noble/app')
        self.assertEqual(seen['user']['project_context']['repositories'], ['noble/app'])
        self.assertIn('PROJECT RELATIONSHIP CONTEXT', seen['system'])

    def test_soul_lists_people_and_channels_but_not_private_identifiers(self):
        for i in range(2):
            tid = self.task(repo='noble/app')
            self.s.add_message({'TaskId': tid, 'ExternalId': f'wa:{i}', 'Channel': 'whatsapp',
                                'FromName': 'Rene Gomez', 'FromEmail': '15551234567@s.whatsapp.net',
                                'ConversationId': 'whatsapp:15551234567@s.whatsapp.net', 'BodyText': 'Noble update'})
            projects.learn_task_repository(self.s, tid, 'noble/app')
        docsync.sync_projects(self.s)
        soul = self.s.get_doc('soul')
        self.assertIn('**noble/app**', soul)
        self.assertIn('Rene Gomez (email, whatsapp)', soul)
        self.assertIn('learned from 2 owner-routed tasks', soul)
        self.assertNotIn('rene@noble.example', soul)
        self.assertNotIn('15551234567', soul)
        self.assertIn('Owner prose.', soul)

    def test_same_name_on_a_new_channel_is_context_not_an_automatic_route(self):
        for _ in range(2):
            tid = self.task(repo='noble/app')
            projects.learn_task_repository(self.s, tid, 'noble/app')
        wa = {'Channel': 'whatsapp', 'FromName': 'Rene Gomez',
              'FromEmail': '15550001111@s.whatsapp.net', 'BodyText': 'hello'}
        ctx = projects.context_for_message(self.s, wa)
        self.assertEqual(ctx['relationship'], 'possible cross-channel identity')
        tid = self.task(sender='15550001111@s.whatsapp.net', channel='whatsapp', body='hello')
        self.assertEqual(projects.repositories_for_task(self.s, tid)[0], [])

    def test_a_learned_company_domain_connects_another_colleague(self):
        for _ in range(2):
            tid = self.task(repo='noble/app')
            projects.learn_task_repository(self.s, tid, 'noble/app')
        colleague = self.task(sender='maria@noble.example', name='Maria Chen', body='A new Noble request')
        repos, why = projects.repositories_for_task(self.s, colleague)
        self.assertEqual(repos, ['noble/app'])
        self.assertIn('owner repository choices', why)

    def test_public_email_domains_never_become_project_relationships(self):
        tid = self.task(sender='rene@gmail.com', repo='noble/app')
        projects.learn_task_repository(self.s, tid, 'noble/app')
        self.assertEqual(self.s.project_links(kind='email_domain'), [])

    def test_whatsapp_identity_uses_the_sender_not_a_group_room(self):
        identity = projects.identity_of({'Channel': 'whatsapp', 'FromName': 'Rene',
                                         'FromEmail': '15551234567:4@s.whatsapp.net',
                                         'ConversationId': 'whatsapp:group@g.us'})
        self.assertEqual(identity, ('whatsapp', '15551234567', 'Rene'))


if __name__ == '__main__':
    unittest.main()

"""A tracker item that CHANGES is a new arrival.

Eleven tracker channels keyed their ExternalId on the item's name (jira:OPS-12,
gh:owner/repo#42), so every later version was dropped as a duplicate: an issue
rewritten after you first saw it reached nobody, and comments were never fetched
at all. See docs/superpowers/specs/2026-09-15-tracker-revisions-design.md.
"""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import channels, github, pm
from taskuary.store import MemoryStore


def conn(s, typ, cfg=None):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1,
                      **({'ConfigJson': json.dumps(cfg)} if cfg else {})}, 't')
    return s.get_connector(cid, with_secret=True)


def jira_issue(desc='it double-books', status='To Do', priority='High', comments=None,
               category='indeterminate', key='OPS-12'):
    return {'key': key, 'fields': {
        'summary': 'Fix the sync', 'description': desc, 'updated': '2026-08-23T09:00:00.000+0000',
        'status': {'name': status, 'statusCategory': {'key': category}},
        'priority': {'name': priority}, 'reporter': {'displayName': 'Rina'},
        'comment': {'comments': comments or [], 'total': len(comments or [])}}}


def jira_comment(cid, body, account='acct-rina', name='Rina', typ='atlassian'):
    return {'id': str(cid), 'body': body, 'created': '2026-08-23T10:00:00.000+0000',
            'author': {'accountId': account, 'displayName': name, 'accountType': typ}}


class JiraRevisionTests(unittest.TestCase):
    def poll(self, s, c, issue):
        """One poll returning exactly this issue."""
        real, pm._jira_get = pm._jira_get, lambda c_, p, **kw: {'issues': [issue]}
        try: return pm.poll_jira(s, c, datetime.now() - timedelta(hours=1))
        finally: pm._jira_get = real

    def test_a_rewritten_description_lands_as_a_second_arrival(self):
        s = MemoryStore()
        c = conn(s, 'jira', {'base_url': 'https://team.atlassian.net', 'email': 'me@x.com'})
        self.assertEqual(self.poll(s, c, jira_issue()), 1)
        n = self.poll(s, c, jira_issue('it double-books when two people accept at once'))
        self.assertEqual(n, 1, 'an edited description is new words and must reach triage')
        self.assertEqual(len(s.feed()), 2)

    def test_a_row_stored_under_the_old_bare_id_stays_silent(self):
        """Upgrade day. Rows ingested before this shipped are keyed `jira:OPS-12` with no
        hash; re-hashing the STORED words must recognise them, or the first poll after an
        update re-triages the owner's whole board."""
        s = MemoryStore()
        c = conn(s, 'jira', {'base_url': 'https://team.atlassian.net', 'email': 'me@x.com'})
        issue = jira_issue()
        head = '[Jira OPS-12 - status To Do · priority High · assigned to you]'
        s.add_message({'ExternalId': 'jira:OPS-12', 'Channel': 'jira', 'Status': 'filed',
                       'ConversationId': 'jira:OPS-12', 'Subject': 'OPS-12 Fix the sync',
                       'BodyText': head + '\n' + issue['fields']['description'],
                       'SentAt': '2026-08-23 09:00:00'})
        self.assertEqual(self.poll(s, c, issue), 0, 'the same words under the old key are not new')
        self.assertEqual(len(s.feed()), 1)

    def test_a_status_flip_is_a_revision(self):
        s = MemoryStore()
        c = conn(s, 'jira', {'base_url': 'https://team.atlassian.net', 'email': 'me@x.com'})
        self.assertEqual(self.poll(s, c, jira_issue()), 1)
        n = self.poll(s, c, jira_issue(status='Blocked'))
        self.assertEqual(n, 1, 'Blocked is the signal a tracker exists to carry')

    def test_a_revision_keeps_the_item_conversation_so_it_joins_the_same_task(self):
        s = MemoryStore()
        c = conn(s, 'jira', {'base_url': 'https://team.atlassian.net', 'email': 'me@x.com'})
        self.poll(s, c, jira_issue())
        self.poll(s, c, jira_issue('now with a repro'))
        convs = {r['ConversationId'] for r in s.feed()}
        self.assertEqual(convs, {'jira:OPS-12'}, 'the hash belongs in the id, never the conversation')
        ids = {s.get_message(r['MessageId'])['ExternalId'] for r in s.feed()}
        self.assertEqual(len(ids), 2, 'each version is its own row')
        self.assertTrue(all(i.startswith('jira:OPS-12@') for i in ids))


class JiraCommentTests(unittest.TestCase):
    """Jira hands its comments back inside the search the poll already makes (fields=comment),
    so the conversation costs no extra call."""

    def poll(self, s, c, issue):
        real, pm._jira_get = pm._jira_get, lambda c_, p, **kw: (
            {'accountId': 'acct-us', 'displayName': 'Taskuary'} if p.endswith('/myself') else {'issues': [issue]})
        try: return pm.poll_jira(s, c, datetime.now() - timedelta(hours=1))
        finally: pm._jira_get = real

    def card(self, s):
        return conn(s, 'jira', {'base_url': 'https://team.atlassian.net', 'email': 'me@x.com'})

    def test_the_search_asks_for_comments_in_the_same_call(self):
        s, seen = MemoryStore(), {}
        c = self.card(s)
        def spy(c_, p, **kw):
            seen[p] = kw
            return {'accountId': 'acct-us'} if p.endswith('/myself') else {'issues': []}
        real, pm._jira_get = pm._jira_get, spy
        try: pm.poll_jira(s, c, datetime.now() - timedelta(hours=1))
        finally: pm._jira_get = real
        self.assertIn('comment', seen['/rest/api/2/search']['fields'],
                      'comments must ride the search - a call per issue is the expensive way')

    def test_a_comment_joins_its_issue(self):
        s = MemoryStore()
        c = self.card(s)
        self.poll(s, c, jira_issue())
        n = self.poll(s, c, jira_issue(comments=[jira_comment(7, 'is this still happening?')]))
        self.assertEqual(n, 1)
        self.assertEqual({r['ConversationId'] for r in s.feed()}, {'jira:OPS-12'})

    def test_our_own_comment_is_history_not_work(self):
        s = MemoryStore()
        c = self.card(s)
        self.poll(s, c, jira_issue())
        self.poll(s, c, jira_issue(comments=[jira_comment(8, 'Picked this up.', account='acct-us')]))
        row = s.message_by_external('jira:OPS-12:c8')
        self.assertIsNotNone(row, 'kept so the thread reads correctly')
        self.assertEqual(row['Status'], 'context')

    def test_an_app_comment_is_history_not_work(self):
        """Jira marks automation and add-ons accountType=app - a release bot is not a person."""
        s = MemoryStore()
        c = self.card(s)
        self.poll(s, c, jira_issue())
        self.poll(s, c, jira_issue(comments=[jira_comment(9, 'Build 412 deployed.', account='acct-bot', typ='app')]))
        row = s.message_by_external('jira:OPS-12:c9')
        self.assertIsNotNone(row)
        self.assertEqual(row['Status'], 'context')


class EveryTrackerTests(unittest.TestCase):
    """The freeze was never a GitHub bug - eleven channels had it. A connector written later
    must not quietly reintroduce it, so the rule is checked on the source, not per vendor."""

    # notion and sentry already suffix a vendor stamp and are deliberately left alone (see the
    # spec); discord is a chat channel, not a tracker, and joins by room like the other chats.
    ALREADY_VERSIONED = {'poll_notion', 'poll_sentry', 'poll_discord'}

    def test_no_tracker_poll_ingests_without_hashing_its_words(self):
        import inspect
        from taskuary import devtools, pm
        offenders = []
        for mod in (pm, devtools):
            for name in sorted(n for n in dir(mod) if n.startswith('poll_')):
                if name in self.ALREADY_VERSIONED: continue
                body = inspect.getsource(getattr(mod, name))
                if 'ingest_tracker(' not in body and 'ingest_message(' in body:
                    offenders.append(f'{mod.__name__}.{name}')
        self.assertEqual(offenders, [], 'these still key on the item, so an edit is dropped as a duplicate')


class OtherTrackerRevisionTests(unittest.TestCase):
    def test_gitlab_edit_lands_again(self):
        from taskuary import devtools
        s = MemoryStore()
        c = conn(s, 'gitlab', {'base_url': 'https://gitlab.com'})
        def rows(desc):
            return lambda c_, path, **kw: ([{'id': 5, 'iid': 5, 'title': 'Export breaks', 'description': desc,
                                             'state': 'opened', 'updated_at': '2026-08-23T09:00:00Z',
                                             'web_url': 'https://gitlab.com/o/r/-/issues/5',
                                             'author': {'name': 'Rina'}}] if path == '/issues' else [])
        def poll(desc):
            real, devtools._gitlab = devtools._gitlab, rows(desc)
            try: return devtools.poll_gitlab(s, c, datetime.now() - timedelta(hours=1))
            finally: devtools._gitlab = real
        self.assertEqual(poll('it breaks'), 1)
        self.assertEqual(poll('it breaks on rows over 10k'), 1, 'an edited GitLab issue is new words')

    def test_asana_edit_lands_again(self):
        s = MemoryStore()
        c = conn(s, 'asana', {'workspace_gid': '99'})
        def poll(notes):
            rows = [{'gid': '1', 'name': 'Chase the invoice', 'notes': notes,
                     'modified_at': '2099-01-01T08:00:00.000Z'}]
            real, pm._asana_get = pm._asana_get, lambda c_, p, **kw: rows
            try: return pm.poll_asana(s, c, datetime.now())
            finally: pm._asana_get = real
        self.assertEqual(poll('ping them'), 1)
        self.assertEqual(poll('ping them - they replied, need the PO number'), 1)


def gh_item(body='login is slow', number=42, user='rina', assoc='MEMBER', typ='User', state='open'):
    return {'number': number, 'title': 'Login is slow', 'body': body, 'state': state,
            'user': {'login': user, 'type': typ}, 'author_association': assoc,
            'updated_at': '2026-08-23T09:00:00Z', 'html_url': f'https://github.com/o/r/issues/{number}'}


def gh_comment(cid, body, login='rina', typ='User'):
    return {'id': cid, 'body': body, 'user': {'login': login, 'type': typ},
            'created_at': '2026-08-23T10:00:00Z', 'updated_at': '2026-08-23T10:00:00Z',
            'html_url': f'https://github.com/o/r/issues/42#issuecomment-{cid}'}


class GithubRevisionTests(unittest.TestCase):
    SRC = {'Address': 'o/r', 'ConfigJson': json.dumps({'issues': 'tasks'})}

    def poll(self, s, items, comments=None, closer='ray'):
        with mock.patch.object(github, 'list_items', return_value=items), \
             mock.patch.object(github, 'body_images', return_value=[]), \
             mock.patch.object(github, 'closed_by', return_value=closer), \
             mock.patch.object(github, 'issue_comments', return_value=comments or [], create=True):
            return channels.ingest_github_issues(s, self.SRC, 'tok', datetime.now() - timedelta(hours=1))

    def test_a_rewritten_issue_body_lands_as_a_second_arrival(self):
        s = MemoryStore()
        self.assertEqual(self.poll(s, [gh_item()]), 1)
        n = self.poll(s, [gh_item('login drops the session after 30s, here is the repro')])
        self.assertEqual(n, 1, 'the rewritten report is what the coder must read')
        self.assertEqual(len(s.feed()), 2)

    def test_a_comment_lands_on_the_same_conversation_as_its_issue(self):
        s = MemoryStore()
        self.poll(s, [gh_item()])
        n = self.poll(s, [gh_item()], comments=[gh_comment(900, 'any chance this lands this week?')])
        self.assertEqual(n, 1, 'a comment is a person asking - it must reach the funnel')
        convs = {r['ConversationId'] for r in s.feed()}
        self.assertEqual(convs, {'gh:o/r#42'}, 'a comment joins the issue it was written on')

    def test_our_own_comment_is_history_not_work(self):
        """Taskuary comments on issues itself (outbound.comment_issue). Without this it reads
        its own reply next poll and can answer itself."""
        s = MemoryStore()
        s.set_setting('github_login', 'taskuary-bot', 'test')
        self.poll(s, [gh_item()])
        self.poll(s, [gh_item()], comments=[gh_comment(901, 'On it - opened a PR.', login='taskuary-bot')])
        row = s.message_by_external('gh:o/r#42:c901')
        self.assertIsNotNone(row, 'it is kept - the thread has to read correctly')
        self.assertEqual(row['Status'], 'context', 'kept as history, never as a new ask')
        self.assertNotIn('opened a PR', ' '.join(str(r.get('Preview')) for r in s.feed(days=99)))

    def test_a_bot_comment_is_history_not_work(self):
        s = MemoryStore()
        self.poll(s, [gh_item()])
        self.poll(s, [gh_item()], comments=[gh_comment(902, 'Coverage dropped 0.1%', login='codecov', typ='Bot')])
        row = s.message_by_external('gh:o/r#42:c902')
        self.assertIsNotNone(row)
        self.assertEqual(row['Status'], 'context', 'a coverage bot is not a person asking')
        self.assertNotIn('Coverage', ' '.join(str(r.get('Preview')) for r in s.feed(days=99)))

    def test_a_bot_comment_keeps_the_bot_s_name(self):
        """It is filed as history, not as something YOU said - ingest_own_message stamps
        FromName 'You', which would put the owner's name on a coverage bot's line."""
        s = MemoryStore()
        self.poll(s, [gh_item()])
        self.poll(s, [gh_item()], comments=[gh_comment(903, 'Coverage dropped 0.1%', login='codecov', typ='Bot')])
        self.assertEqual(s.message_by_external('gh:o/r#42:c903')['FromName'], 'codecov')


class UpstreamEndingTests(unittest.TestCase):
    """A closure is not an edit: nothing ARRIVES. The item simply stops being returned, so the
    task sat in the work list forever (the owner, 2026-09-15, on TQ-0550)."""
    SRC = {'Address': 'o/r', 'ConfigJson': json.dumps({'issues': 'tasks'})}

    def poll(self, s, items, comments=None, closer='ray'):
        with mock.patch.object(github, 'list_items', return_value=items), \
             mock.patch.object(github, 'body_images', return_value=[]), \
             mock.patch.object(github, 'closed_by', return_value=closer), \
             mock.patch.object(github, 'issue_comments', return_value=comments or [], create=True):
            return channels.ingest_github_issues(s, self.SRC, 'tok', datetime.now() - timedelta(hours=1))

    def open_task_on(self, s, conv):
        """The task the item's conversation belongs to. Triage is what normally opens one, and it
        needs an AI connector these tests deliberately do not have, so it is made here directly."""
        row = next(r for r in s.feed(days=99) if r['ConversationId'] == conv)
        tid = s.create_task({'Title': 'Login is slow', 'Kind': 'coding', 'Status': 'open'}, 'test')
        s.attach_message(row['MessageId'], tid)
        return tid

    def test_the_poll_asks_for_closed_items_too(self):
        """With state=open a closure is silence. Asking for all is what makes the ending arrive."""
        s = MemoryStore()
        with mock.patch.object(github, 'list_items', return_value=[]) as li, \
             mock.patch.object(github, 'issue_comments', return_value=[], create=True):
            channels.ingest_github_issues(s, self.SRC, 'tok', datetime.now() - timedelta(hours=1))
        self.assertEqual(li.call_args.kwargs.get('state'), 'all')

    def test_a_closed_item_closes_its_task_and_says_why(self):
        s = MemoryStore()
        self.poll(s, [gh_item()])
        tid = self.open_task_on(s, 'gh:o/r#42')
        self.poll(s, [gh_item(state='closed')])
        self.assertEqual(s.get_task(tid)['Status'], 'done', 'the work is moot - it must leave the work list')
        said = ' '.join(str(c.get('Body')) for c in s.list_comments(tid))
        self.assertIn('closed', said.lower(), 'a task that closes itself has to say what closed it')

    def test_your_own_merge_is_your_close_not_a_result_to_read(self):
        """You merged the pull request yourself; the startup catch-up then closed its task as a result "Its pull
        request" finished, unread on the rail and in the greeting though you had just done it (TQ-0754)."""
        from taskuary.processing_unread import finish_evidence
        s = MemoryStore(); s.set_setting('owner_github', 'alex', 'test')
        self.poll(s, [gh_item()])
        tid = self.open_task_on(s, 'gh:o/r#42')
        self.poll(s, [gh_item(state='closed')], closer='Alex')
        self.assertEqual((s.get_task(tid)['Status'], s.get_task(tid)['UpdatedBy']), ('done', 'owner'))
        self.assertIn('You closed this issue on GitHub', ' '.join(str(c.get('Body')) for c in s.list_comments(tid)))
        self.assertIsNone(finish_evidence(s, tid))

    def test_somebody_else_ending_it_is_still_news(self):
        from taskuary.processing_unread import finish_evidence
        s = MemoryStore(); s.set_setting('owner_github', 'alex', 'test')
        self.poll(s, [gh_item()])
        tid = self.open_task_on(s, 'gh:o/r#42')
        self.poll(s, [gh_item(state='closed')], closer='ray')
        self.assertEqual(finish_evidence(s, tid)['who'], 'Its issue')

    def test_closing_goes_through_the_normal_ending_with_the_last_message(self):
        """Not a bare status flip: the same wrap every other ending gets, so the report is
        written, proposals become reviews, the sender gets their reply - and the cause is
        recorded as the LAST MESSAGE rather than vanishing into a status change."""
        from taskuary import coder
        s = MemoryStore()
        self.poll(s, [gh_item()])
        tid = self.open_task_on(s, 'gh:o/r#42')
        with mock.patch.object(coder, 'wrap', return_value={'wrap': 'done'}) as w:
            self.poll(s, [gh_item(state='closed')])
        self.assertEqual(w.call_args.kwargs.get('close'), True)
        self.assertIn('closed', w.call_args.kwargs.get('final_message', '').lower())
        self.assertIn('#42', w.call_args.kwargs.get('final_message', ''))

    def test_a_task_with_no_session_still_closes(self):
        """wrap refuses a task that never had a transcript ('nothing to wrap up'). TQ-0550 was
        exactly that, so the refusal must not leave the dead task in the work list."""
        s = MemoryStore()
        self.poll(s, [gh_item()])
        tid = self.open_task_on(s, 'gh:o/r#42')
        self.poll(s, [gh_item(state='closed')])       # no session was ever opened on it
        self.assertEqual(s.get_task(tid)['Status'], 'done')

    def test_an_item_that_was_already_closed_never_becomes_work(self):
        """Backfill reaches items closed long before Taskuary saw them - history, not a new job."""
        s = MemoryStore()
        n = self.poll(s, [gh_item(number=7, state='closed')])
        self.assertEqual(n, 0)
        self.assertEqual([r for r in s.feed(days=99) if r['ConversationId'] == 'gh:o/r#7'], [])

    def test_a_resolved_jira_issue_closes_its_task(self):
        """Jira has no open/closed flag - resolution is statusCategory 'done', whatever the
        workflow calls that column (Done, Shipped, Won't Fix)."""
        s = MemoryStore()
        c = conn(s, 'jira', {'base_url': 'https://team.atlassian.net', 'email': 'me@x.com'})
        def poll(issue):
            real, pm._jira_get = pm._jira_get, lambda c_, p, **kw: (
                {'accountId': 'acct-us'} if p.endswith('/myself') else {'issues': [issue]})
            try: return pm.poll_jira(s, c, datetime.now() - timedelta(hours=1))
            finally: pm._jira_get = real
        poll(jira_issue())
        row = next(r for r in s.feed(days=99) if r['ConversationId'] == 'jira:OPS-12')
        tid = s.create_task({'Title': 'Fix the sync', 'Kind': 'coding', 'Status': 'open'}, 'test')
        s.attach_message(row['MessageId'], tid)
        poll(jira_issue(status='Done', category='done'))
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        self.assertIn('done', ' '.join(str(x.get('Body')) for x in s.list_comments(tid)).lower())

    def test_a_jira_issue_already_resolved_never_becomes_work(self):
        s = MemoryStore()
        c = conn(s, 'jira', {'base_url': 'https://team.atlassian.net', 'email': 'me@x.com'})
        real, pm._jira_get = pm._jira_get, lambda c_, p, **kw: (
            {'accountId': 'acct-us'} if p.endswith('/myself')
            else {'issues': [jira_issue(key='OPS-99', status='Done', category='done')]})
        try: pm.poll_jira(s, c, datetime.now() - timedelta(hours=1))
        finally: pm._jira_get = real
        self.assertEqual([r for r in s.feed(days=99) if r['ConversationId'] == 'jira:OPS-99'], [])

    def test_a_bot_s_own_pull_request_is_history_not_work(self):
        """TQ-0550: github-actions[bot] refreshing the download chart opened a task and waited."""
        s = MemoryStore()
        self.poll(s, [gh_item(number=46, user='github-actions[bot]', typ='Bot',
                              body='Refresh the PyPI download history.')])
        row = s.message_by_external('gh:o/r#46')
        self.assertEqual(row['Status'], 'context',
                         'a robot filing its own chore is not somebody asking you for something')
        self.assertEqual(row['FromName'], 'github-actions[bot]', 'under its own name, not yours')
        self.assertEqual([r for r in s.feed(days=99) if r['ConversationId'] == 'gh:o/r#46'], [],
                         'and it never reaches the timeline as work')
        self.assertIsNone(s.task_for_conversation('gh:o/r#46'), 'nor opens a task to sit in the work list')

"""Telegram chat approval, per-source agent prompts, and the PM connectors (Jira/Asana/Monday)."""
import json, unittest
from datetime import datetime, timedelta

from taskuary import messengers, pm
from taskuary.ingest import source_rules, PR_RULES, ISSUE_RULES
from taskuary.store import MemoryStore


def conn(s, typ, cfg=None):
    """The seeded connector row of this type, armed with a token (Type is UNIQUE - update it)."""
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1,
                      **({'ConfigJson': json.dumps(cfg)} if cfg else {})}, 't')
    return s.get_connector(cid, with_secret=True)


class TelegramApprovalTests(unittest.TestCase):
    def fake_tg(self, updates):
        def _tg(tok, method, **kw):
            if method == 'getUpdates': return updates
            return {}
        return _tg

    def test_unknown_chat_registers_off_and_never_ingests(self):
        s = MemoryStore()
        c = conn(s, "telegram")
        real, messengers.tg = messengers.tg, self.fake_tg([{'update_id': 7, 'message': {
            'message_id': 1, 'date': 1755900000, 'text': 'buy my crypto course',
            'chat': {'id': 555, 'title': None}, 'from': {'first_name': 'Spam', 'last_name': 'Mer'}}}])
        try: n = messengers.poll_telegram(s, c, [])
        finally: messengers.tg = real
        self.assertEqual(n, 0)
        src = next(x for x in s.list_sources(active_only=False) if x['Channel'] == 'telegram')
        self.assertEqual((src['Address'], src['Active']), ('555', 0))
        self.assertIn('Spam Mer', src['Owner'])
        self.assertEqual(s.feed(), [])                       # not a message anywhere, not even filed

    def test_approved_chat_flows_in(self):
        s = MemoryStore()
        c = conn(s, "telegram")
        s.save_source({'Channel': 'telegram', 'Address': '555', 'ConnectorId': c['ConnectorId'], 'Active': 1}, 't')
        real, messengers.tg = messengers.tg, self.fake_tg([{'update_id': 8, 'message': {
            'message_id': 2, 'date': 1755900000, 'text': 'please fix the export',
            'chat': {'id': 555}, 'from': {'first_name': 'Uri'}}}])
        try: n = messengers.poll_telegram(s, c, [])
        finally: messengers.tg = real
        self.assertEqual(n, 1)
        self.assertEqual(len(s.feed()), 1)


class SourceRulesTests(unittest.TestCase):
    def msg(self, ch, body='', source=''):
        return {'Channel': ch, 'BodyText': body, 'SourceName': source}

    def test_github_pr_and_issue_defaults(self):
        s = MemoryStore()
        pr = self.msg('github', '[pull request by drive-by - association: NONE]\nAdds CSV import')
        self.assertEqual(source_rules(s, pr), PR_RULES)
        self.assertEqual(source_rules(s, self.msg('github', '[issue by someone - association: OWNER]\nIt broke')), ISSUE_RULES)

    def test_github_card_prompt_overrides(self):
        s = MemoryStore()
        c = s.get_connector_by_type('github')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'ConfigJson': json.dumps({'prompt_pr': 'house PR rules'})}, 't')
        self.assertEqual(source_rules(s, self.msg('github', '[pull request by x - association: NONE]')), 'house PR rules')

    def test_connector_task_prompt_and_email_silence(self):
        s = MemoryStore()
        c = s.get_connector_by_type('telegram')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'ConfigJson': json.dumps({'task_prompt': 'chat asks are urgent'})}, 't')
        self.assertEqual(source_rules(s, self.msg('telegram')), 'chat asks are urgent')
        self.assertEqual(source_rules(s, self.msg('email')), '')          # the mail IS the prompt
        self.assertEqual(source_rules(s, self.msg('report')), '')




class PmPollTests(unittest.TestCase):
    def test_jira_assigned_issue_lands_once(self):
        s = MemoryStore()
        c = conn(s, 'jira', {'base_url': 'https://team.atlassian.net', 'email': 'me@x.com'})
        real, pm._jira_get = pm._jira_get, lambda c_, p, **kw: {'issues': [{'key': 'OPS-12', 'fields': {
            'summary': 'Fix the sync', 'description': 'it double-books', 'updated': '2026-08-23T09:00:00.000+0000',
            'status': {'name': 'To Do'}, 'priority': {'name': 'High'}, 'reporter': {'displayName': 'Rina'}}}]}
        try:
            n1 = pm.poll_jira(s, c, datetime.now() - timedelta(hours=1))
            n2 = pm.poll_jira(s, c, datetime.now() - timedelta(hours=1))
        finally: pm._jira_get = real
        self.assertEqual((n1, n2), (1, 0))                    # dedupe by issue key
        row = s.feed()[0]
        self.assertEqual(row['Channel'], 'jira')
        self.assertIn('OPS-12', row['Subject'])

    def test_asana_since_filter(self):
        s = MemoryStore()
        c = conn(s, 'asana', {'workspace_gid': '99'})
        rows = [{'gid': '1', 'name': 'Old one', 'notes': '', 'modified_at': '2026-08-20T08:00:00.000Z'},
                {'gid': '2', 'name': 'Fresh one', 'notes': 'do it', 'modified_at': '2099-01-01T08:00:00.000Z'}]
        real, pm._asana_get = pm._asana_get, lambda c_, p, **kw: rows
        try: n = pm.poll_asana(s, c, datetime.now())
        finally: pm._asana_get = real
        self.assertEqual(n, 1)
        self.assertIn('Fresh one', s.feed()[0]['Subject'])

    def test_monday_keeps_only_items_naming_me(self):
        s = MemoryStore()
        c = conn(s, 'monday', {'me_id': '42'})
        data = {'boards': [{'name': 'Ops', 'items_page': {'items': [
            {'id': '10', 'name': 'Mine', 'updated_at': '2099-01-01T00:00:00Z', 'url': 'u', 'creator': {'name': 'Boss'},
             'column_values': [{'type': 'people', 'text': 'Uri', 'persons_and_teams': [{'id': 42, 'kind': 'person'}]}]},
            {'id': '11', 'name': 'Not mine', 'updated_at': '2099-01-01T00:00:00Z', 'url': 'u', 'creator': None,
             'column_values': [{'type': 'people', 'text': 'Someone', 'persons_and_teams': [{'id': 7, 'kind': 'person'}]}]},
        ]}}]}
        real, pm._monday = pm._monday, lambda c_, q: data
        try: n = pm.poll_monday(s, c, datetime.now())
        finally: pm._monday = real
        self.assertEqual(n, 1)
        self.assertEqual(s.feed()[0]['Subject'], 'Mine')


if __name__ == '__main__':
    unittest.main()

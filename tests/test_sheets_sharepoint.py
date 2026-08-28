"""SharePoint and Google Sheets: report sources whose cards borrow - the Outlook tenant app, the
Gmail card's Google client - and only when there is something to borrow."""
import json, unittest
from unittest import mock
from taskuary import channels, compose, reports, sharepoint, sheets
from taskuary.store import MemoryStore


class R:
    def __init__(self, code, body=None, content=b''): self.status_code, self._b, self.content, self.text = code, body, content, json.dumps(body or {})
    def json(self): return self._b


def _set(s, typ, cfg=None, secret=None, active=1):
    c = s.get_connector_by_type(typ)
    s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': active, **({'ConfigJson': json.dumps(cfg)} if cfg is not None else {}),
                      **({'Secret': secret} if secret else {})}, 't')
    return s.get_connector_by_type(typ, with_secret=True)


class BorrowTests(unittest.TestCase):
    def test_sharepoint_borrows_the_outlook_tenant_app_but_never_a_personal_sign_in(self):
        s = MemoryStore()
        self.assertFalse(sharepoint.can_borrow_outlook(s))
        _set(s, 'outlook', {'tenant_id': 'T', 'client_id': 'C'}, secret='S')
        self.assertTrue(sharepoint.can_borrow_outlook(s))
        cfg = sharepoint.sharepoint_connection(s)
        self.assertEqual((cfg['tenant_id'], cfg['client_id'], cfg['client_secret'], cfg['borrowed']), ('T', 'C', 'S', 'outlook'))
        _set(s, 'sharepoint', {'tenant_id': 'T2', 'client_id': 'C2'}, secret='S2')      # its own app wins
        cfg = sharepoint.sharepoint_connection(s)
        self.assertEqual((cfg['client_id'], cfg['client_secret']), ('C2', 'S2')); self.assertNotIn('borrowed', cfg)
        s2 = MemoryStore()
        _set(s2, 'outlook', {'auth': 'user', 'client_id': 'pub', 'account': 'me@x.com'}, secret='RT')   # mail scopes only
        self.assertFalse(sharepoint.can_borrow_outlook(s2))
        self.assertNotIn('client_secret', sharepoint.sharepoint_connection(s2))

    def test_sheets_borrows_the_gmail_google_client_never_its_token(self):
        s = MemoryStore()
        self.assertFalse(sheets.can_borrow_gmail(s))
        _set(s, 'gmail', {'address': 'me@gmail.com', 'google_client_id': 'GID', 'google_client_secret': 'GSEC', 'google_refresh_token': 'CAL-RT'}, secret='apppw')
        self.assertTrue(sheets.can_borrow_gmail(s))
        cfg = sheets.google_sheets_connection(s)
        self.assertEqual((cfg['google_client_id'], cfg['google_client_secret'], cfg['borrowed']), ('GID', 'GSEC', 'gmail'))
        self.assertNotIn('google_refresh_token', cfg)                                          # the calendar token does not cover sheets
        _set(s, 'google_sheets', {}, secret='SHEETS-RT')
        self.assertEqual(sheets.google_sheets_connection(s)['google_refresh_token'], 'SHEETS-RT')


class RunTests(unittest.TestCase):
    def test_a_sharepoint_list_becomes_rows(self):
        calls = []
        def get(url, headers=None, params=None, timeout=None, allow_redirects=None):
            calls.append(url)
            if url.endswith('/sites/contoso.sharepoint.com:/sites/Ops'): return R(200, {'id': 'SITE1'})
            if '/lists/Requests/items' in url:
                return R(200, {'value': [{'fields': {'@odata.etag': 'x', 'id': '1', 'Title': 'Fix door', 'Status': 'Open', 'ContentType': 'Item'}},
                                         {'fields': {'Title': 'Order chairs', 'Status': 'Done'}}]})
            return R(404, {})
        with mock.patch.object(sharepoint, '_token', return_value='TOK'), mock.patch.object(sharepoint.requests, 'get', side_effect=get):
            head, body = sharepoint.run_sharepoint_list({'site': 'https://contoso.sharepoint.com/sites/Ops', 'list': 'Requests'})
        self.assertIn('2 items in Requests', head)
        rows = [json.loads(l) for l in body.splitlines()]
        self.assertEqual(rows[0], {'Title': 'Fix door', 'Status': 'Open'})                    # odata and housekeeping columns dropped
        self.assertTrue(calls[0].endswith('/sites/contoso.sharepoint.com:/sites/Ops'))

    def test_a_csv_in_a_library_becomes_rows_and_a_folder_lists(self):
        def get(url, headers=None, params=None, timeout=None, allow_redirects=None):
            if url.endswith(':/sites/Ops'): return R(200, {'id': 'SITE1'})
            if url.endswith('latest.csv:/content'): return R(200, content=b'name,beds\nElkton,120\nGuilford,88\n')
            if url.endswith('Reports:/children'): return R(200, {'value': [{'name': 'a.csv', 'size': 10, 'lastModifiedDateTime': '2026-08-27T09:00:00Z'},
                                                                        {'name': 'b.csv', 'size': 12, 'lastModifiedDateTime': '2026-08-28T09:00:00Z'}]})
            return R(404, {})
        with mock.patch.object(sharepoint, '_token', return_value='TOK'), mock.patch.object(sharepoint.requests, 'get', side_effect=get):
            head, body = sharepoint.run_sharepoint_file({'site': 'contoso.sharepoint.com/sites/Ops', 'path': 'Shared Documents/Reports/latest.csv'})
            self.assertIn('2 rows from latest.csv', head); self.assertEqual(json.loads(body.splitlines()[1]), {'name': 'Guilford', 'beds': '88'})
            head, body = sharepoint.run_sharepoint_file({'site': 'contoso.sharepoint.com/sites/Ops', 'path': 'Shared Documents/Reports/'})
            self.assertIn('2 items in Reports', head); self.assertEqual(json.loads(body.splitlines()[0])['name'], 'b.csv')   # newest first

    def test_a_google_sheet_becomes_rows_with_the_first_row_as_headers(self):
        def get(url, headers=None, params=None, timeout=None):
            if url.endswith('/values/Sheet1!A:C'): return R(200, {'values': [['name', 'beds', ''], ['Elkton', 120], ['Guilford', 88, 'note']]})
            return R(404, {})
        with mock.patch.object(sheets, '_token', return_value='TOK'), mock.patch.object(sheets.requests, 'get', side_effect=get):
            head, body = sheets.run_google_sheets({'spreadsheet': 'https://docs.google.com/spreadsheets/d/ABC123/edit#gid=0', 'range': 'Sheet1!A:C'})
        self.assertIn('2 rows from Sheet1!A:C', head)
        rows = [json.loads(l) for l in body.splitlines()]
        self.assertEqual(rows[0], {'name': 'Elkton', 'beds': 120, 'col2': ''}); self.assertEqual(rows[1]['col2'], 'note')
        self.assertEqual(sheets.spreadsheet_id('https://docs.google.com/spreadsheets/d/ABC123/edit'), 'ABC123'); self.assertEqual(sheets.spreadsheet_id('XYZ'), 'XYZ')

    def test_the_token_road_and_its_refusals_speak_plainly(self):
        with self.assertRaises(RuntimeError) as e: sheets._token({})
        self.assertIn('client id', str(e.exception))
        with self.assertRaises(RuntimeError) as e: sheets._token({'google_client_id': 'a', 'google_client_secret': 'b'})
        self.assertIn('refresh token', str(e.exception))
        with mock.patch.object(sheets.requests, 'post', return_value=R(200, {'access_token': 'AT', 'expires_in': 3600})):
            self.assertEqual(sheets._token({'google_client_id': 'a', 'google_client_secret': 'b', 'google_refresh_token': 'fresh-rt'}), 'AT')
        with self.assertRaises(RuntimeError) as e: sharepoint._token({})
        self.assertIn('Sites.Read.All', str(e.exception))


class WiringTests(unittest.TestCase):
    def test_the_types_are_real_report_types_owned_by_their_cards(self):
        for t in ('google_sheets', 'sharepoint_list', 'sharepoint_file'):
            self.assertIn(t, reports.REGISTRY); self.assertNotIn(t, reports.PLANNED); self.assertIn(t, reports.CONNECTION_OF)
        self.assertEqual((reports.card_of('sharepoint_list'), reports.card_of('sharepoint_file'), reports.card_of('google_sheets')),
                         ('sharepoint', 'sharepoint', 'google_sheets'))
        s = MemoryStore()
        rows = {r['type']: r for r in compose.catalog(s)}
        self.assertIn('spreadsheet', rows['google_sheets']['takes']); self.assertIn('list', rows['sharepoint_list']['takes'])   # the composer sees the real docstrings
        self.assertEqual(rows['sharepoint_list']['connection'], 'sharepoint'); self.assertFalse(rows['sharepoint_list']['ready'])
        self.assertTrue(s.get_connector_by_type('sharepoint')); self.assertTrue(s.get_connector_by_type('google_sheets'))   # seeded cards

    def test_the_cards_test_through_their_modules(self):
        s = MemoryStore()
        with mock.patch.object(sharepoint, 'test', return_value='reaches SharePoint') as t:
            out = channels.test_connector(s, s.get_connector_by_type('sharepoint')['ConnectorId'])
        self.assertTrue(out['ok']); self.assertEqual(out['detail'], 'reaches SharePoint'); t.assert_called_once()
        with mock.patch.object(sheets, 'test', return_value='Google accepted the token') as t:
            out = channels.test_connector(s, s.get_connector_by_type('google_sheets')['ConnectorId'])
        self.assertTrue(out['ok']); t.assert_called_once()

"""Sage Intacct over the XML gateway.

The protocol has three habits worth pinning down, because each one fails quietly:
a 200 response can carry <status>failure</status>, paging is driven by an attribute that some
objects omit, and the endpoint that gets the credentials on every later call is one the LOGIN
RESPONSE names rather than one we chose.
"""
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

from taskuary import intacct

CFG = {'sender_id': 'snd', 'sender_password': 'sp', 'user_id': 'ws_user',
       'user_password': 'up', 'company_id': 'ACME'}

LOGIN_OK = b"""<response><operation><result><status>success</status>
<data><api><sessionid>SESS-123</sessionid>
<endpoint>https://api.intacct.com/ia/xml/xmlgw.phtml</endpoint></api></data>
</result></operation></response>"""


def _data(records, remaining=0, tag='data'):
    inner = ''.join(f'<glentry>{r}</glentry>' for r in records)
    return (f'<response><operation><result><status>success</status>'
            f'<{tag} numremaining="{remaining}" totalcount="{len(records)}">{inner}</{tag}>'
            f'</result></operation></response>').encode()


class _Resp:
    def __init__(self, body): self.content, self.status_code = body, 200
    def raise_for_status(self): pass


def _posts(*bodies):
    """Patch requests.post and hand back the list it records, so a test can read the XML that
    actually went out rather than trusting that it was built."""
    sent = []
    it = iter(bodies)
    def fake(url, data=None, headers=None, timeout=None):
        sent.append((url, ET.fromstring(data)))
        return _Resp(next(it))
    return sent, fake


class LoginTests(unittest.TestCase):
    def setUp(self): intacct._sessions.clear()

    def test_the_five_credentials_all_reach_the_wire(self):
        sent, fake = _posts(LOGIN_OK)
        with mock.patch('taskuary.intacct.requests.post', fake):
            sid, end = intacct.login(dict(CFG))
        self.assertEqual(sid, 'SESS-123')
        doc = sent[0][1]
        self.assertEqual(doc.findtext('.//control/senderid'), 'snd')
        self.assertEqual(doc.findtext('.//control/password'), 'sp')
        self.assertEqual(doc.findtext('.//login/userid'), 'ws_user')
        self.assertEqual(doc.findtext('.//login/password'), 'up')
        self.assertEqual(doc.findtext('.//login/companyid'), 'ACME')

    def test_the_session_is_reused(self):
        """One login per company, not one per report row."""
        sent, fake = _posts(LOGIN_OK)
        with mock.patch('taskuary.intacct.requests.post', fake):
            intacct.login(dict(CFG)); intacct.login(dict(CFG))
        self.assertEqual(len(sent), 1)

    def test_a_missing_credential_is_named(self):
        with self.assertRaises(intacct.IntacctError) as e:
            intacct.login({**CFG, 'company_id': ''})
        self.assertIn('company id', str(e.exception))

    def test_an_entity_scopes_the_session(self):
        sent, fake = _posts(LOGIN_OK)
        with mock.patch('taskuary.intacct.requests.post', fake):
            intacct.login({**CFG, 'entity_id': 'FAC-2'})
        self.assertEqual(sent[0][1].findtext('.//login/locationid'), 'FAC-2')


class FailureIsNotAnHttpErrorTests(unittest.TestCase):
    def setUp(self): intacct._sessions.clear()

    def test_a_200_saying_failure_raises_with_the_reason(self):
        """The one that matters operationally: a role with permission on nothing answers 200."""
        bad = (b'<response><operation><result><status>failure</status><errormessage>'
               b'<error><description>x</description>'
               b'<description2>You do not have permission to view this object</description2>'
               b'</error></errormessage></result></operation></response>')
        _, fake = _posts(bad)
        with mock.patch('taskuary.intacct.requests.post', fake):
            with self.assertRaises(intacct.IntacctError) as e: intacct.login(dict(CFG))
        self.assertIn('do not have permission', str(e.exception))


class QueryTests(unittest.TestCase):
    def setUp(self): intacct._sessions.clear()

    def test_fields_and_filters_become_the_query(self):
        sent, fake = _posts(LOGIN_OK, _data(['<AMOUNT>10</AMOUNT>']))
        with mock.patch('taskuary.intacct.requests.post', fake):
            rows = intacct.query(dict(CFG), 'GLENTRY', ['AMOUNT'],
                                 [['BATCH_DATE', '>=', '08/01/2026'], ['STATE', '=', 'Posted']])
        self.assertEqual(rows, [{'AMOUNT': '10'}])
        q = sent[1][1].find('.//query')
        self.assertEqual(q.findtext('object'), 'GLENTRY')
        self.assertEqual([f.text for f in q.findall('select/field')], ['AMOUNT'])
        # two conditions are wrapped in <and>; the operators are the gateway's names
        conds = q.find('filter/and')
        self.assertEqual([c.tag for c in conds], ['greaterthanorequalto', 'equalto'])
        self.assertEqual(conds[0].findtext('field'), 'BATCH_DATE')
        self.assertEqual(conds[0].findtext('value'), '08/01/2026')

    def test_one_condition_needs_no_and_wrapper(self):
        """Intacct rejects an <and> with a single child, so the single case is spelled apart."""
        sent, fake = _posts(LOGIN_OK, _data([]))
        with mock.patch('taskuary.intacct.requests.post', fake):
            intacct.query(dict(CFG), 'VENDOR', ['VENDORID'], [['STATUS', '=', 'active']])
        fil = sent[1][1].find('.//query/filter')
        self.assertIsNone(fil.find('and'))
        self.assertEqual(fil[0].tag, 'equalto')

    def test_no_fields_asks_for_all_of_them(self):
        sent, fake = _posts(LOGIN_OK, _data([]))
        with mock.patch('taskuary.intacct.requests.post', fake):
            intacct.query(dict(CFG), 'VENDOR')
        self.assertEqual([f.text for f in sent[1][1].findall('.//select/field')], ['*'])

    def test_an_unknown_operator_is_refused_rather_than_sent(self):
        _, fake = _posts(LOGIN_OK)
        with mock.patch('taskuary.intacct.requests.post', fake):
            with self.assertRaises(intacct.IntacctError) as e:
                intacct.query(dict(CFG), 'VENDOR', ['X'], [['F', 'contains', 'v']])
        self.assertIn('contains', str(e.exception))

    def test_in_takes_a_list(self):
        sent, fake = _posts(LOGIN_OK, _data([]))
        with mock.patch('taskuary.intacct.requests.post', fake):
            intacct.query(dict(CFG), 'VENDOR', ['X'], [['VENDORID', 'in', ['V1', 'V2']]])
        cond = sent[1][1].find('.//filter/in')
        self.assertEqual([v.text for v in cond.findall('value')], ['V1', 'V2'])

    def test_isnull_carries_no_value(self):
        sent, fake = _posts(LOGIN_OK, _data([]))
        with mock.patch('taskuary.intacct.requests.post', fake):
            intacct.query(dict(CFG), 'VENDOR', ['X'], [['TERM', 'isnull', None]])
        self.assertEqual(sent[1][1].findall('.//filter/isnull/value'), [])


class PagingTests(unittest.TestCase):
    def setUp(self): intacct._sessions.clear()

    def test_it_follows_the_offset_until_the_server_runs_out(self):
        full = [f'<N>{i}</N>' for i in range(intacct.PAGE)]
        sent, fake = _posts(LOGIN_OK, _data(full, remaining=2), _data(['<N>x</N>', '<N>y</N>']))
        with mock.patch('taskuary.intacct.requests.post', fake):
            rows = intacct.query(dict(CFG), 'GLENTRY', ['N'], limit=5000)
        self.assertEqual(len(rows), intacct.PAGE + 2)
        self.assertEqual(sent[2][1].findtext('.//query/offset'), str(intacct.PAGE))

    def test_a_short_page_ends_it_even_when_numremaining_lies(self):
        """An object that omits (or overstates) numremaining used to loop forever. A page
        shorter than the one asked for means the server is done, whatever it claims."""
        sent, fake = _posts(LOGIN_OK, _data(['<N>1</N>'], remaining=99))
        with mock.patch('taskuary.intacct.requests.post', fake):
            rows = intacct.query(dict(CFG), 'GLENTRY', ['N'], limit=5000)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(sent), 2)          # login + one page, then it stopped

    def test_the_limit_is_honoured(self):
        sent, fake = _posts(LOGIN_OK, _data([f'<N>{i}</N>' for i in range(10)]))
        with mock.patch('taskuary.intacct.requests.post', fake):
            rows = intacct.query(dict(CFG), 'GLENTRY', ['N'], limit=3)
        self.assertEqual(len(rows), 3)
        self.assertEqual(sent[1][1].findtext('.//query/pagesize'), '3')


class EndpointIsPinnedTests(unittest.TestCase):
    """The endpoint every later call posts credentials to comes back INSIDE the login response.
    A login that answers with somewhere else is a bug or an attack; either way it does not get
    the password."""
    def setUp(self): intacct._sessions.clear()

    def test_a_non_intacct_endpoint_is_refused(self):
        evil = LOGIN_OK.replace(b'https://api.intacct.com/ia/xml/xmlgw.phtml',
                                b'https://collector.example.net/x')
        _, fake = _posts(evil, LOGIN_OK)
        with mock.patch('taskuary.intacct.requests.post', fake):
            intacct.login(dict(CFG))                       # the login itself goes to the gateway
            with self.assertRaises(intacct.IntacctError) as e:
                intacct.query(dict(CFG), 'VENDOR', ['X'])
        self.assertIn('not a Sage Intacct endpoint', str(e.exception))

    def test_a_regional_intacct_host_is_allowed(self):
        ok = LOGIN_OK.replace(b'https://api.intacct.com/ia/xml/xmlgw.phtml',
                              b'https://api.eu.intacct.com/ia/xml/xmlgw.phtml')
        sent, fake = _posts(ok, _data([]))
        with mock.patch('taskuary.intacct.requests.post', fake):
            intacct.query(dict(CFG), 'VENDOR', ['X'])
        self.assertTrue(sent[1][0].startswith('https://api.eu.intacct.com'))

    def test_a_lookalike_domain_is_not_intacct(self):
        evil = LOGIN_OK.replace(b'https://api.intacct.com/ia/xml/xmlgw.phtml',
                                b'https://api.intacct.com.evil.net/x')
        _, fake = _posts(evil, LOGIN_OK)
        with mock.patch('taskuary.intacct.requests.post', fake):
            intacct.login(dict(CFG))
            with self.assertRaises(intacct.IntacctError):
                intacct.query(dict(CFG), 'VENDOR', ['X'])


class SchemaTests(unittest.TestCase):
    def setUp(self): intacct._sessions.clear()

    def test_the_field_list_comes_back_readable(self):
        """This is what lets a report be written in English against the real schema."""
        body = (b'<response><operation><result><status>success</status><data><Type>'
                b'<Fields><Field><ID>VENDORID</ID><LABEL>Vendor ID</LABEL><DATATYPE>TEXT</DATATYPE></Field>'
                b'<Field><ID>TOTALDUE</ID><LABEL>Total due</LABEL><DATATYPE>CURRENCY</DATATYPE></Field>'
                b'</Fields></Type></data></result></operation></response>')
        _, fake = _posts(LOGIN_OK, body)
        with mock.patch('taskuary.intacct.requests.post', fake):
            fields = intacct.fields_of(dict(CFG), 'APBILL')
        self.assertEqual([f['ID'] for f in fields], ['VENDORID', 'TOTALDUE'])
        self.assertEqual(fields[1]['DATATYPE'], 'CURRENCY')


class ReportExecutorTests(unittest.TestCase):
    def setUp(self): intacct._sessions.clear()

    def test_the_report_type_runs_the_query(self):
        from taskuary.reports import run_intacct
        _, fake = _posts(LOGIN_OK, _data(['<AMOUNT>10</AMOUNT>', '<AMOUNT>20</AMOUNT>']))
        with mock.patch('taskuary.intacct.requests.post', fake):
            head, body = run_intacct({**CFG, 'object': 'GLENTRY', 'fields': ['AMOUNT']})
        self.assertIn('2 rows', head)
        self.assertIn('AMOUNT', body)

    def test_no_object_says_what_to_put_there(self):
        from taskuary.reports import run_intacct
        with self.assertRaises(RuntimeError) as e: run_intacct(dict(CFG))
        self.assertIn('GLENTRY', str(e.exception))

    def test_it_is_a_read_only_connection(self):
        """Nothing here posts a journal entry, and the authority says so."""
        from taskuary import scopes
        self.assertEqual(scopes.default_scope('intacct'), 'read')
        self.assertEqual(scopes.ACTIONS['intacct'], 'read')
        from taskuary.store import DEFAULT_ROLES
        self.assertNotIn('trigger', DEFAULT_ROLES['intacct'])


CREATED = (b"""<response><operation><result><status>success</status>
<function>create</function><key>1042</key>
<data listtype="objects" count="1"><apbill><RECORDNO>1042</RECORDNO>
<DOCNUMBER>AP-1042</DOCNUMBER><TOTALENTERED>412.50</TOTALENTERED></apbill></data>
</result></operation></response>""")

REFUSED = (b"""<response><operation><result><status>failure</status>
<errormessage><error><description2>Currency BILL is not valid</description2></error></errormessage>
</result></operation></response>""")


class WriteTests(unittest.TestCase):
    """Posting to the books goes through the same gateway as reading, generically by object -
    and the same 200-with-failure trap has to be caught here, where the cost of missing it is a
    proposal the owner approved that silently did nothing."""

    def setUp(self): intacct._sessions.clear()

    BILL = {'VENDORID': 'V100', 'WHENCREATED': '09/01/2026',
            'APBILLITEMS': [{'ACCOUNTNO': '6120', 'AMOUNT': '412.50'},
                            {'ACCOUNTNO': '6130', 'AMOUNT': '18.00'}]}

    def test_a_bill_is_built_as_the_gateway_wants_it(self):
        sent, fake = _posts(LOGIN_OK, CREATED)
        with mock.patch('taskuary.intacct.requests.post', fake):
            out = intacct.create(dict(CFG), 'APBILL', self.BILL)
        doc = sent[1][1]
        self.assertEqual(doc.findtext('.//create/APBILL/VENDORID'), 'V100')
        # a list becomes REPEATED children named by dropping one trailing S - APBILLITEM under APBILLITEMS
        lines = doc.findall('.//create/APBILL/APBILLITEMS/APBILLITEM')
        self.assertEqual([l.findtext('AMOUNT') for l in lines], ['412.50', '18.00'])
        # the receipt names the document, not "success"
        self.assertEqual((out['verb'], out['object'], out['key']), ('create', 'APBILL', '1042'))
        self.assertEqual(out['record']['DOCNUMBER'], 'AP-1042')

    def test_a_nested_dict_stays_nested(self):
        sent, fake = _posts(LOGIN_OK, CREATED)
        with mock.patch('taskuary.intacct.requests.post', fake):
            intacct.create(dict(CFG), 'VENDOR', {'NAME': 'Acme', 'MAILADDRESS': {'ADDRESS1': '1 Main St'}})
        self.assertEqual(sent[1][1].findtext('.//create/VENDOR/MAILADDRESS/ADDRESS1'), '1 Main St')

    def test_a_refusal_is_raised_with_the_reason_not_swallowed(self):
        sent, fake = _posts(LOGIN_OK, REFUSED)
        with mock.patch('taskuary.intacct.requests.post', fake):
            with self.assertRaises(intacct.IntacctError) as e:
                intacct.create(dict(CFG), 'APBILL', self.BILL)
        self.assertIn('Currency BILL is not valid', str(e.exception))

    def test_an_update_must_say_which_record_it_changes(self):
        with self.assertRaises(intacct.IntacctError) as e:
            intacct.update(dict(CFG), 'APBILL', {'DESCRIPTION': 'corrected'})
        self.assertIn('RECORDNO', str(e.exception))
        sent, fake = _posts(LOGIN_OK, CREATED)
        with mock.patch('taskuary.intacct.requests.post', fake):
            out = intacct.update(dict(CFG), 'APBILL', {'RECORDNO': '1042', 'DESCRIPTION': 'corrected'})
        self.assertEqual(sent[1][1].findtext('.//update/APBILL/RECORDNO'), '1042')
        self.assertEqual(out['verb'], 'update')

    def test_nothing_to_write_is_refused_before_a_login(self):
        for bad in ({}, None):
            with self.assertRaises(intacct.IntacctError):
                intacct.create(dict(CFG), 'APBILL', bad)
        with self.assertRaises(intacct.IntacctError):
            intacct.create(dict(CFG), '', {'X': 1})


class TheWriteIsGatedTests(unittest.TestCase):
    """What actually keeps a bill from posting on an agent's say-so is the SCOPE ladder, not
    intacct.py: the card ships at read, so /api/tools/run refuses the write and the only road
    left is a proposal the owner approves."""

    def test_the_card_ships_read_and_the_writes_need_write(self):
        from taskuary import scopes
        from taskuary.reports import CARD_OF, CONNECTION_OF, REGISTRY
        self.assertEqual(scopes.default_scope('intacct'), 'read')
        for t in ('intacct_create', 'intacct_update'):
            self.assertIn(t, REGISTRY)
            self.assertEqual(scopes.needs(t), 'write')
            self.assertEqual(CARD_OF[t], 'intacct')       # it runs on the Intacct card's five credentials
            self.assertIn(t, CONNECTION_OF)
        self.assertEqual(scopes.needs('intacct'), 'read')

    def test_a_read_scoped_card_refuses_the_write(self):
        from taskuary import scopes
        card = {'Type': 'intacct', 'Scope': 'read', 'Active': 1}
        with self.assertRaises(Exception):
            scopes.require(card, 'intacct_create')
        scopes.require(card, 'intacct')                    # the reads still run
        scopes.require({**card, 'Scope': 'write'}, 'intacct_create')


if __name__ == '__main__':
    unittest.main()

"""A From address is a claim; the receiving server's Authentication-Results is the evidence (DMARC/DKIM).

A forged From - a colleague's address, or the owner's own domain, typed into a stranger's mail - must not be trusted
for an unattended start. No results at all keeps today's rules, so mail stored before this never flips."""
import email, json
from unittest import mock
from taskuary import ingest, mailauth, origin, senders, imapmail
from taskuary.channels import _header_marks
from taskuary.store import MemoryStore

FROM = ('From', 'Erin Blake <erin@northwind.example>')
def AR(v): return ('Authentication-Results', v)

def test_dmarc_pass_and_fail():
    assert mailauth.verdict([FROM, AR('mx.northwind.example; spf=pass smtp.mailfrom=northwind.example; dmarc=pass header.from=northwind.example')]) == 'pass'
    assert mailauth.verdict([FROM, AR('mx.northwind.example; dmarc=fail (p=reject dis=none) header.from=northwind.example')]) == 'fail'
    assert mailauth.verdict([FROM, AR('mx.northwind.example; dmarc=quarantine header.from=northwind.example')]) == 'fail'

def test_aligned_dkim_pass_is_a_pass_and_an_unaligned_one_is_not():
    assert mailauth.verdict([FROM, AR('mx.northwind.example; dkim=pass header.d=northwind.example; dmarc=none')]) == 'pass'
    assert mailauth.verdict([FROM, AR('mx.northwind.example; dkim=pass header.d=mail.northwind.example')]) == 'pass'
    assert mailauth.verdict([FROM, AR('mx.northwind.example; dkim=pass header.d=vendor.example')]) == 'none'
    assert mailauth.verdict([FROM, AR('mx.northwind.example; dkim=pass header.d=vendor.example; dmarc=fail header.from=northwind.example')]) == 'fail'

def test_aligned_dkim_fail_with_no_pass_is_a_fail():
    assert mailauth.verdict([FROM, AR('mx.northwind.example; dkim=fail (bad signature) header.d=northwind.example')]) == 'fail'

def test_exchange_internal_mail_is_a_pass():
    assert mailauth.verdict({'From': FROM[1], 'X-MS-Exchange-Organization-AuthAs': 'Internal',
                             'X-MS-Exchange-Organization-AuthSource': 'mx01.northwind.example'}) == 'pass'
    assert mailauth.verdict({'From': FROM[1], 'X-MS-Exchange-Organization-AuthAs': 'Anonymous'}) == 'none'

def test_no_results_is_none():
    assert mailauth.verdict([FROM, ('Received', 'from mx.vendor.example')]) == 'none'
    assert mailauth.verdict([]) == 'none' and mailauth.verdict(None) == 'none'

def test_folded_case_insensitive_exchange_style_and_graph_shape():
    v = 'spf=pass (sender IP is 192.0.2.1)\r\n smtp.mailfrom=northwind.example; DKIM=Pass (signature was verified)\r\n\theader.d=Northwind.example;dmarc=pass action=none header.from=northwind.example;compauth=pass reason=100'
    assert mailauth.verdict([{'name': 'from', 'value': FROM[1]}, {'name': 'authentication-results', 'value': v}]) == 'pass'

def test_a_fail_anywhere_beats_a_pass_a_sender_could_have_written_themselves():
    hs = [FROM, AR('mx.northwind.example; dmarc=fail header.from=northwind.example'), AR('forged.example; dmarc=pass')]
    assert mailauth.verdict(hs) == 'fail'

def test_arc_results_count_only_from_the_receiving_server():
    arc = ('ARC-Authentication-Results', 'i=1; mx.northwind.example; dmarc=pass header.from=northwind.example')
    assert mailauth.verdict([FROM, AR('mx.northwind.example; dmarc=none'), arc]) == 'pass'
    other = ('ARC-Authentication-Results', 'i=1; relay.vendor.example; dmarc=pass header.from=northwind.example')
    assert mailauth.verdict([FROM, AR('mx.northwind.example; dmarc=none'), other]) == 'none'


def _store():
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
    s.save_source({'Channel': 'email', 'Address': 'alex@northwind.example', 'Owner': 'me', 'Active': 1}, 't')
    return s

def _msg(frm, **kw): return {'channel': 'email', 'from_email': frm, 'source_name': 'alex@northwind.example', **kw}

def test_known_refuses_a_failed_colleague_address_and_keeps_pass_and_none():
    s = _store()
    with mock.patch.object(s, 'trusted_sender', return_value=True):
        ok, why = senders.known(s, _msg('ray@partner.example', auth='fail'))
        assert not ok and 'failed sender verification' in why and 'ray@partner.example' in why
        assert senders.known(s, _msg('ray@partner.example', auth='pass'))[0]
        assert senders.known(s, _msg('ray@partner.example'))[0]

def test_an_own_domain_from_with_dmarc_fail_is_not_trusted():
    s = _store()
    assert senders.known(s, _msg('erin@northwind.example'))[0]
    assert not senders.known(s, _msg('erin@northwind.example', auth='fail'))[0]
    assert not senders.known(s, _msg('erin@northwind.example', MailMetaJson=json.dumps({'auth': 'fail'})))[0]
    assert not senders.known(s, _msg('alex@northwind.example', auth='fail'))[0]

def test_origin_marks_a_forged_own_domain_task_stranger():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'email'}, 'router')
    s.add_message({'TaskId': t, 'Channel': 'email', 'SourceName': 'alex@northwind.example', 'FromEmail': 'erin@northwind.example',
                   'Subject': 'x', 'BodyText': 'y', 'Status': 'routed', 'MailMetaJson': json.dumps({'folder': 'inbox', 'auth': 'fail'})})
    o, why = origin.of_task(s, t)
    assert o == 'stranger' and 'forged' in why


def _meta(s, ext): return json.loads(s.message_by_external(ext)['MailMetaJson'])

def test_a_graph_message_records_its_verdict_beside_the_mail_meta():
    m = {'internetMessageHeaders': [{'name': 'From', 'value': FROM[1]},
                                    {'name': 'Authentication-Results', 'value': 'mx.northwind.example; dmarc=fail header.from=northwind.example'}]}
    marks = _header_marks(m)
    assert marks['auth'] == 'fail'
    s = _store()
    ingest.ingest_message(s, file_only=True, llm=None, msg={'external_id': 'graph:g1', 'subject': 's', 'body': 'b', 'sent_at': '2026-10-01 09:00',
                                                            **_msg('erin@northwind.example'), **marks, 'mail_meta': {'folder': 'inbox'}})
    assert _meta(s, 'graph:g1') == {'folder': 'inbox', 'auth': 'fail'}

def test_an_imap_raw_message_records_its_verdict():
    raw = (b'Authentication-Results: mx.northwind.example;\r\n dkim=pass header.d=northwind.example;\r\n dmarc=pass header.from=northwind.example\r\n'
           b'From: Erin Blake <erin@northwind.example>\r\nSubject: s\r\n\r\nbody\r\n')
    marks = imapmail.protocol_marks(email.message_from_bytes(raw))
    assert marks['auth'] == 'pass'
    s = _store()
    ingest.ingest_message(s, file_only=True, llm=None, msg={'external_id': 'imap:i1', 'subject': 's', 'body': 'b', 'sent_at': '2026-10-01 09:00',
                                                            **_msg('erin@northwind.example'), **marks})
    assert _meta(s, 'imap:i1')['auth'] == 'pass'

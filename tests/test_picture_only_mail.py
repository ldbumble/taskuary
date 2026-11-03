"""A MAIL THAT IS ONLY A PICTURE, AND THE LINKS BEHIND A MAIL'S WORDS (the owner, 2026-11-03: "in a fyi email where entire email was a
image it showed nothing", "hyper links in fyi email like view report are not coming thru").

The HTML was turned into text and thrown away: an image-only body came to "" - stored, triaged and shown as nothing - and an <a href>
kept its words but lost its address unless it was a document. Everything here is invented: a vendor at vendor.example mailing Alex
Doyle at Northwind, a 1x1 PNG made on the spot.
"""
import base64, json, struct, zlib
from datetime import datetime, timedelta
from email.message import EmailMessage
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import channels, imapmail, server
from taskuary.store import MemoryStore

ME = 'alex@northwind.example'
REPORT = 'https://reports.vendor.example/r/9?u=alex&t=1'


def png() -> bytes:
    "A real 1x1 PNG."
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) + \
        chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00')) + chunk(b'IEND', b'')


# the whole mail: one pasted picture, wrapped in a link to the report, and the sender's tracking pixel
PICTURE_ONLY = ('<html><head><style>p{}</style></head><body><a href="https://reports.vendor.example/r/9">'
                '<img src="cid:image001.png@01DB0000" alt="October numbers"></a>'
                '<img src="https://t.vendor.example/open.gif" width="1" height="1"></body></html>')
WITH_LINKS = (f'<p>Your October report is ready.</p><a href="{REPORT.replace("&", "&amp;")}" style="color:#fff"><span>View report</span></a>'
              ' <a href="mailto:help@vendor.example">Write to us</a> <a href="javascript:alert(1)">Run me</a>'
              ' <a href="https://docs.google.com/spreadsheets/d/Abc123DefGhi/edit">Open</a>')


def test_a_picture_only_mail_reads_as_its_pictures_and_a_pixel_is_none():
    assert channels._clean(PICTURE_ONLY) == '[image: October numbers]'
    assert channels._clean('<p><img src="https://cdn.vendor.example/a/banner.png?x=1"></p>') == '[remote image: banner.png]'
    assert channels._clean('<img src="cid:image002.jpg@01DB">') == '[image: image002.jpg]'
    assert channels._clean('<img src="https://t.vendor.example/p.gif" width=1 height="1px">') == ''
    # ...and a mail with words keeps only its words: a logo beside them is not a stand-in triage has to read past
    assert channels._clean('<p>Thanks, Alex.</p><img src="cid:logo.png" alt="Vendor logo">') == 'Thanks, Alex.'


def test_the_links_behind_words_are_kept_beside_the_text_never_in_it():
    text = channels._clean(WITH_LINKS)
    assert 'View report' in text and 'reports.vendor.example' not in text          # linkdocs never reads (and so never GETs) it
    assert channels.mail_links(WITH_LINKS) == [['View report', REPORT], ['Write to us', 'mailto:help@vendor.example']]
    assert channels.mail_links('<a href="https://x.vendor.example/a">https://x.vendor.example/a</a><a href="#top">Top</a>') == []


def test_imap_keeps_the_links_of_its_html_part():
    m = EmailMessage()
    m['From'], m['Subject'] = 'Reports <reports@vendor.example>', 'October report'
    m.set_content('Your October report is ready. View report')
    m.add_alternative(WITH_LINKS, subtype='html')
    assert imapmail.html_links(m) == {'links': [['View report', REPORT], ['Write to us', 'mailto:help@vendor.example']]}


def _world():
    s = MemoryStore()
    cid = s.get_connector_by_type('outlook')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1, 'ConfigJson': '{"tenant_id": "t", "client_id": "c"}'}, 't')
    s.save_source({'Channel': 'email', 'Address': ME, 'ConnectorId': cid, 'Active': 1}, 't')
    return s


def _poll(s, html, atts=()):
    mail = {'id': 'm1', 'subject': 'October report', 'body': {'contentType': 'html', 'content': html}, 'hasAttachments': False,
            'from': {'emailAddress': {'name': 'Reports at Vendor', 'address': 'reports@vendor.example'}},
            'toRecipients': [{'emailAddress': {'address': ME}}], 'ccRecipients': [],
            'receivedDateTime': (datetime.now() - timedelta(minutes=5)).isoformat(), 'conversationId': 'c1', 'webLink': 'https://outlook.example/m1'}
    seen = {}
    def classify(msg, **kw): seen.update(msg); return {'intent': 'fyi', 'why': 'a report, nothing to do'}
    with mock.patch.object(channels, 'graph_token', return_value='tok'), \
         mock.patch.object(channels, '_mail_msgs', side_effect=lambda t, u, since, folder='inbox': [] if folder == 'sentitems' else [mail]), \
         mock.patch.object(channels, 'mail_attachments', return_value=list(atts)), \
         mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: '{}'), \
         mock.patch('taskuary.ingest.classify_intent', classify):
        channels.poll_channels(s)
    return seen, s.feed(limit=5)[0]['MessageId']


def test_a_pasted_picture_reaches_triage_by_its_words_and_the_screen_by_its_bytes():
    s = _world()
    att = {'id': 'a1', 'name': 'image001.png', 'contentType': 'image/png', 'size': len(png()), 'isInline': True,
           'contentId': 'image001.png@01DB0000', 'contentBytes': base64.b64encode(png()).decode()}
    seen, mid = _poll(s, PICTURE_ONLY, [att])
    assert seen['body'] == '[image: October numbers]'                              # triage read the picture's alt, not nothing
    assert [ct for ct, _ in seen.get('images') or []] == ['image/png']             # ...and saw the picture itself
    with mock.patch.object(server, 'store', s):
        c = TestClient(server.app)
        got = c.get(f'/api/messages/{mid}').json()
        files = c.get(f'/api/messages/{mid}/attachments').json()['data']
    assert got['BodyText'] == '[image: October numbers]' and got['Links'] == []
    assert [(f['name'], f['inline'], f['is_image'], bool(f['url'])) for f in files] == [('image001.png', True, True, True)]


def test_the_view_report_link_comes_with_the_message():
    s = _world()
    _seen, mid = _poll(s, WITH_LINKS)
    with mock.patch.object(server, 'store', s):
        got = TestClient(server.app).get(f'/api/messages/{mid}').json()
    assert got['Links'] == [['View report', REPORT], ['Write to us', 'mailto:help@vendor.example']]
    assert 'reports.vendor.example' not in got['BodyText']
    # ...and only a web or mail address is ever handed to a screen as a link, whatever the row holds
    s.cx.execute('UPDATE message SET MailMetaJson=? WHERE MessageId=?',
                 (json.dumps({'links': [['Run me', 'javascript:alert(1)'], ['View report', REPORT], 'junk']}), mid))
    with mock.patch.object(server, 'store', s):
        assert TestClient(server.app).get(f'/api/messages/{mid}').json()['Links'] == [['View report', REPORT]]


def test_a_wordless_mail_says_what_came_with_it_on_its_card():
    from taskuary import funnel
    s = MemoryStore()
    mid = s.add_message({'Channel': 'email', 'FromEmail': 'reports@vendor.example', 'Subject': 'October report', 'BodyText': '',
                         'SentAt': '2026-11-03 09:00', 'Status': 'filed'})
    for n in ('October.xlsx', 'Notes.pdf'): s.add_attachment({'MessageId': mid, 'ExternalId': f'x:{n}', 'Name': n, 'ContentType': 'application/pdf', 'Size': 9})
    assert funnel._preview(s, {'MessageId': mid, 'Preview': ''}) == 'Attached: October.xlsx, Notes.pdf'
    assert funnel._preview(s, {'MessageId': mid, 'Preview': '[image: October numbers]'}) == '[image: October numbers]'

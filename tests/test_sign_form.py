"""A FORM SIGNED WITH THE SIGNATURE THE OWNER SAVED ONCE (the owner, 2026-11-04: "A person got a permission slip to sign for their
kid. The agent should sign it and say 'do you want me to send it out'").

The slip here is made in the test - a text field for the child's name, a box to tick, and a signature field on page 2 - and signed
through the agent's own door (the sign_form tool on /api/mcp). The signature picture is the owner's alone: no agent or stranger reads
it back, and with none saved the tool says so instead of signing.
"""
import base64, io, struct, tempfile, unittest, zlib
from datetime import date
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, BooleanObject, DecodedStreamObject, DictionaryObject, FloatObject, NameObject, NumberObject, TextStringObject
from taskuary import config, guard, handsign, server
from taskuary.store import MemoryStore

c = TestClient(server.app)
SRV = server.cfg['server']
def agent(tid): return {'X-Taskuary-Token': SRV['agent_token'], guard.TASK_HDR: guard.task_proof(SRV, tid)}
def n(k): return NameObject(k)


def a_png(w=48, h=14) -> bytes:
    "A stroke of ink on nothing: RGBA, every row filtered Sub so the unpacking is exercised, not skipped."
    rows = []
    for y in range(h):
        px = [(20, 30, 90, 255) if abs(x * h // w - y) <= 1 else (0, 0, 0, 0) for x in range(w)]
        raw = bytes(v for p in px for v in p)
        rows.append(b'\x01' + bytes((raw[i] - (raw[i - 4] if i >= 4 else 0)) & 255 for i in range(len(raw))))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b''))


def a_slip() -> bytes:
    "Page 1: the child's name and a box to tick. Page 2: 'Parent signature' and its signature field."
    w = PdfWriter()
    font = w._add_object(DictionaryObject({n('/Type'): n('/Font'), n('/Subtype'): n('/Type1'), n('/BaseFont'): n('/Helvetica')}))
    fields = []
    for i, words in enumerate(['Field trip permission - Northwind Elementary', 'Parent signature']):
        pg = w.add_blank_page(612, 792)
        body = DecodedStreamObject(); body.set_data(f'BT /F1 12 Tf 72 700 Td ({words}) Tj ET'.encode())
        pg[n('/Contents')] = w._add_object(body)
        pg[n('/Resources')] = DictionaryObject({n('/Font'): DictionaryObject({n('/F1'): font})})
        mine = [('child_name', '/Tx', [200, 640, 400, 660]), ('lunch', '/Btn', [72, 600, 86, 614])] if i == 0 else [('parent_signature', '/Sig', [200, 690, 400, 720])]
        annots = ArrayObject()
        for name, ft, rect in mine:
            a = DictionaryObject({n('/Type'): n('/Annot'), n('/Subtype'): n('/Widget'), n('/FT'): n(ft), n('/T'): TextStringObject(name),
                                  n('/Rect'): ArrayObject([FloatObject(v) for v in rect]), n('/F'): NumberObject(4), n('/DA'): TextStringObject('/Helv 10 Tf 0 g')})
            if ft == '/Btn':
                on = DecodedStreamObject(); on.set_data(b'')
                a[n('/AP')] = DictionaryObject({n('/N'): DictionaryObject({n('/Yes'): w._add_object(on), n('/Off'): w._add_object(DecodedStreamObject())})})
                a[n('/AS')] = n('/Off')
            ref = w._add_object(a); annots.append(ref); fields.append(ref)
        pg[n('/Annots')] = annots
    w._root_object[n('/AcroForm')] = DictionaryObject({n('/Fields'): ArrayObject(fields), n('/DA'): TextStringObject('/Helv 0 Tf 0 g'),
                                                        n('/DR'): DictionaryObject({n('/Font'): DictionaryObject({n('/Helv'): font})}),
                                                        n('/NeedAppearances'): BooleanObject(True)})
    out = io.BytesIO(); w.write(out); return out.getvalue()


def images_on(page) -> list:
    xo = (page.get('/Resources') or {}).get('/XObject') or {}
    return [k for k, v in xo.items() if v.get_object().get('/Subtype') == '/Image']


class Base(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.patches = [mock.patch('taskuary.config.home', return_value=self.home), mock.patch.object(server, 'store', MemoryStore())]
        for p in self.patches: p.start()
        self.s = server.store
        self.tid = self.s.create_task({'Title': 'Sign the field trip slip', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        mid = self.s.add_message({'TaskId': self.tid, 'ExternalId': 'slip1', 'ConversationId': 'conv-slip', 'Channel': 'email',
                                  'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'Subject': 'Field trip slip',
                                  'BodyText': 'Please sign and return the slip.', 'SentAt': '2026-11-03 08:00:00', 'Status': 'routed'})
        self.s.update_task(self.tid, {'TrustedThrough': mid}, 'owner')              # the school is someone the owner knows
        (self.home / 'attachments').mkdir(parents=True, exist_ok=True)
        f = self.home / 'attachments' / 'slip.pdf'; f.write_bytes(a_slip())
        self.att = self.s.add_attachment({'MessageId': mid, 'ExternalId': 'a1', 'Name': 'slip.pdf', 'ContentType': 'application/pdf',
                                          'Size': f.stat().st_size, 'Inline': 0, 'Path': str(f)})

    def tearDown(self):
        for p in reversed(self.patches): p.stop()

    def tool(self, **args):
        r = c.post(f'/api/mcp?task={self.tid}', headers=agent(self.tid),
                   json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'sign_form', 'arguments': args}})
        self.assertEqual(r.status_code, 200, r.text)
        res = r.json()['result']
        return res['content'][0]['text'], res['isError']


class SigningASlip(Base):
    def test_it_fills_the_field_ticks_the_box_and_signs_on_the_signature_page(self):
        handsign.save(a_png())
        text, err = self.tool(attachment=self.att, fields={'child_name': 'Sam Doyle', 'lunch': 'yes'}, sign={'field': 'parent_signature'})
        self.assertFalse(err, text); self.assertIn('slip-signed.pdf', text); self.assertIn('Send', text)
        out = handsign.folder().parent / 'scratch' / 'outputs'
        signed = next(out.rglob('slip-signed.pdf'))
        r = PdfReader(signed)
        self.assertEqual(r.get_fields()['child_name'].get('/V'), 'Sam Doyle')
        self.assertEqual(r.get_fields()['lunch'].get('/V'), '/Yes')
        self.assertEqual(images_on(r.pages[0]), [])                      # page 1 has no signature on it...
        self.assertEqual(len(images_on(r.pages[1])), 1)                  # ...page 2, the line, does
        img = r.pages[1]['/Resources']['/XObject'][images_on(r.pages[1])[0]].get_object()
        self.assertEqual((img['/Width'], img['/Height']), (48, 14)); self.assertIn('/SMask', img)   # the line under it still shows
        self.assertIn(b'/TqSig Do', r.pages[1].get_contents().get_data())
        self.assertIn(b'Parent signature', r.pages[1].get_contents().get_data())  # the page's own words are kept under it
        # ...and shown in the chat, on the task
        shown = [a for a in self.s.list_task_artifacts(self.tid) if a.get('Kind') == 'shown']
        self.assertEqual([a['ContentType'] for a in shown], ['application/pdf'])
        self.assertTrue(Path(shown[0]['Path']).read_bytes().startswith(b'%PDF'))

    def test_a_flat_line_is_found_by_its_words_and_dated(self):
        handsign.save(a_png())
        text, err = self.tool(attachment=self.att, sign={'near': 'Parent signature'}, date=True)
        self.assertFalse(err, text); self.assertIn('page 2', text)
        r = PdfReader(next(self.home.rglob('slip-signed.pdf')))
        body = r.pages[1].get_contents().get_data()
        self.assertIn(b'/TqSig Do', body); self.assertIn(f'{date.today():%B}'.encode(), body)

    def test_with_no_saved_signature_it_signs_nothing_and_says_where_to_add_one(self):
        text, err = self.tool(attachment=self.att, fields={'child_name': 'Sam Doyle'}, sign={'field': 'parent_signature'})
        self.assertIn('Settings -> Your signature', text); self.assertIn('Never draw', text)
        self.assertEqual(list(self.home.rglob('*-signed.pdf')), [])
        self.assertEqual([a for a in self.s.list_task_artifacts(self.tid) if a.get('Kind') == 'shown'], [])

    def test_a_field_the_form_does_not_have_is_said_with_the_ones_it_does(self):
        handsign.save(a_png())
        text, err = self.tool(attachment=self.att, fields={'kid': 'Sam'}, sign={'field': 'parent_signature'})
        self.assertTrue(err); self.assertIn('child_name', text); self.assertIn('parent_signature (signature, page 2)', text)

    def test_another_tasks_attachment_is_not_its_to_sign(self):
        handsign.save(a_png())
        other = self.s.create_task({'Title': 'Someone else', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        self.tid = other
        text, err = self.tool(attachment=self.att, sign={'field': 'parent_signature'})
        self.assertTrue(err); self.assertIn('not an attachment on this task', text)
        self.assertEqual(list(self.home.rglob('*-signed.pdf')), [])

    def test_the_signed_copy_rides_on_the_reply_for_the_owners_send(self):
        handsign.save(a_png())
        self.tool(attachment=self.att, fields={'child_name': 'Sam Doyle'}, sign={'field': 'parent_signature'})
        r = c.post(f'/api/mcp?task={self.tid}', headers=agent(self.tid), json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
            'name': 'propose_reply', 'arguments': {'text': 'Signed slip attached.', 'attach': ['slip-signed.pdf']}}}).json()['result']
        self.assertFalse(r['isError'], r)
        rv = self.s._rows('SELECT * FROM review WHERE TaskId=?', (self.tid,))
        self.assertTrue(rv); self.assertTrue(all(x['Status'] != 'sent' for x in rv))
        self.assertIn('slip-signed.pdf', r['content'][0]['text'])


class TheSignatureIsTheOwners(Base):
    def test_the_owner_saves_sees_and_clears_it(self):
        b64 = base64.b64encode(a_png()).decode()
        self.assertFalse(c.get('/api/hand-signature').json()['saved'])
        got = c.put('/api/hand-signature', json={'data': f'data:image/png;base64,{b64}'}).json()
        self.assertTrue(got['saved']); self.assertEqual((got['width'], got['height']), (48, 14))
        img = c.get('/api/hand-signature/image')
        self.assertEqual(img.status_code, 200); self.assertEqual(img.content, a_png()); self.assertIn('no-store', img.headers['cache-control'])
        self.assertTrue(str(handsign.stored()).startswith(str(self.home)))            # in Taskuary's home, not the repository
        self.assertEqual(c.delete('/api/hand-signature').status_code, 200)
        self.assertFalse(c.get('/api/hand-signature').json()['saved']); self.assertIsNone(handsign.stored())

    def test_a_file_that_is_not_a_picture_is_refused(self):
        r = c.put('/api/hand-signature', json={'data': base64.b64encode(b'%PDF-1.4 not a picture').decode()})
        self.assertEqual(r.status_code, 422); self.assertIsNone(handsign.stored())

    def test_no_agent_and_no_stranger_reads_or_changes_it(self):
        handsign.save(a_png())
        stranger = {'X-Taskuary-Token': guard.stranger_token(SRV, self.tid)}
        for who in (agent(self.tid), stranger):
            for m, path in (('GET', '/api/hand-signature'), ('GET', '/api/hand-signature/image'), ('PUT', '/api/hand-signature'), ('DELETE', '/api/hand-signature')):
                r = c.request(m, path, headers=who, json={'data': ''} if m == 'PUT' else None)
                self.assertEqual(r.status_code, 403, f'{m} {path}')
        self.assertTrue(handsign.stored())

    def test_a_strangers_session_cannot_sign(self):
        handsign.save(a_png())
        stranger = {'X-Taskuary-Token': guard.stranger_token(SRV, self.tid)}
        r = c.post(f'/api/mcp?task={self.tid}', headers=stranger,
                   json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'sign_form', 'arguments': {'attachment': self.att}}})
        self.assertEqual(r.status_code, 403)
        r = c.post('/api/agent/sign-form', headers=stranger, json={'task_id': self.tid, 'attachment': self.att, 'sign': {'field': 'parent_signature'}})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(list(self.home.rglob('*-signed.pdf')), [])

    def test_the_cli_sends_the_files_bytes_and_a_strangers_session_has_no_such_verb(self):
        from taskuary import cli
        f = self.home / 'slip.pdf'; f.write_bytes(a_slip()); sent = []
        args = mock.Mock(sign_form=str(f), form='{"sign": {"field": "parent_signature"}, "date": true}')
        resp = mock.Mock(status_code=200)
        with mock.patch.dict('os.environ', {'TASKUARY_TASK': str(self.tid)}), \
             mock.patch.object(cli, '_post', side_effect=lambda p, b, *a, **k: sent.append((p, b)) or (resp, {'says': 'signed'})):
            cli._sign_form(args, None)
        path, body = sent[0]
        self.assertEqual(path, '/api/agent/sign-form'); self.assertNotIn(str(f), str(body))
        self.assertEqual(base64.b64decode(body['data'])[:4], b'%PDF'); self.assertEqual(body['sign'], {'field': 'parent_signature'})
        self.assertIn('sign_form', cli.AGENT_ACTS); self.assertNotIn('sign_form', cli.STRANGER_ACTS)

    def test_the_door_is_an_agents_and_the_picture_is_denied_to_one(self):
        self.assertEqual(guard.classify('POST', '/api/agent/sign-form')[0], 'agent')
        for m in ('GET', 'PUT', 'DELETE'): self.assertEqual(guard.classify(m, '/api/hand-signature')[0], 'deny')
        self.assertEqual(guard.classify('GET', '/api/hand-signature/image')[0], 'deny')


if __name__ == '__main__': unittest.main()

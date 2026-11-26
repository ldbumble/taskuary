"""A post is set up for the owner's one press, with its picture (the owner, 2026-11-05: "it's not showing the post and the image as a
linkedin post and asking me if i want to post it ... I have linkedin connected"). The agent proposes the post with a picture from its
task folder; nothing reaches LinkedIn until Approve; the press uploads the picture (initializeUpload, then the bytes), posts with it, and
the review keeps what went and where. The general agent is told the roads THIS owner has connected, from the store.
"""
import json, shutil, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import config, general, guard, linkedin, outputs, proposals, server, verdicts

c = TestClient(server.app)
SRV = config.load()['server']
PNG = b'\x89PNG\r\n\x1a\n' + b'\0' * 64


def agent(tid): return {'X-Taskuary-Token': SRV['agent_token'], guard.TASK_HDR: guard.task_proof(SRV, tid)}


class LinkedIn:
    "LinkedIn's HTTP, stubbed: every call recorded, none leaves the machine."
    def __init__(self): self.calls = []
    def get(self, url, **kw):
        self.calls.append(('GET', url)); return mock.Mock(ok=True, json=lambda: {'sub': 'ALEX1', 'name': 'Alex Doyle'})
    def post(self, url, **kw):
        self.calls.append(('POST', url, kw.get('json')))
        if 'initializeUpload' in url:
            return mock.Mock(ok=True, json=lambda: {'value': {'uploadUrl': 'https://upload.linkedin.test/up/1', 'image': 'urn:li:image:C1'}})
        return mock.Mock(ok=True, headers={'x-restli-id': 'urn:li:share:42'}, json=lambda: {})
    def put(self, url, **kw):
        self.calls.append(('PUT', url, len(kw.get('data') or b''))); return mock.Mock(ok=True)


def stubbed(net): return mock.patch.multiple(linkedin.requests, get=net.get, post=net.post, put=net.put)


def mp4(secs=12, size=80 * 1024):
    "The bytes of an MP4 as its header says it: an ftyp, a moov whose mvhd runs `secs`, and a body that fills it to `size`."
    import struct
    ftyp = struct.pack('>I4s', 16, b'ftyp') + b'isom' + b'\0' * 4
    mvhd = struct.pack('>I4sIIIII', 28, b'mvhd', 0, 0, 0, 1000, secs * 1000)
    pad = size - len(ftyp) - 8 - len(mvhd) - 8
    return ftyp + struct.pack('>I4s', 8 + len(mvhd), b'moov') + mvhd + struct.pack('>I4s', 8 + pad, b'mdat') + b'\0' * pad


class LinkedInVideo(LinkedIn):
    "...and its Videos API: an address per part, an ETag per part sent, the finalize that names them, the video read."
    def post(self, url, **kw):
        if 'videos?action=initializeUpload' in url:
            self.calls.append(('POST', url, kw.get('json'))); n = kw['json']['initializeUploadRequest']['fileSizeBytes']
            parts = [{'uploadUrl': f'https://upload.linkedin.test/v/{i}', 'firstByte': a, 'lastByte': min(a + 49999, n - 1)} for i, a in enumerate(range(0, n, 50000))]
            return mock.Mock(ok=True, json=lambda: {'value': {'video': 'urn:li:video:V1', 'uploadToken': 'tok', 'uploadInstructions': parts}})
        return super().post(url, **kw)
    def put(self, url, **kw):
        self.calls.append(('PUT', url, len(kw.get('data') or b''))); return mock.Mock(ok=True, headers={'etag': f'"e{url.rsplit("/", 1)[-1]}"'})
    def get(self, url, **kw):
        if '/rest/videos/' in url: self.calls.append(('GET', url)); return mock.Mock(ok=True, json=lambda: {'status': 'AVAILABLE'})
        return super().get(url, **kw)


class TheExecutor(unittest.TestCase):
    def test_a_picture_is_uploaded_then_named_on_the_post(self):
        f = outputs.folder(9001); f.mkdir(parents=True, exist_ok=True); (f / 'gas.png').write_bytes(PNG)
        net = LinkedIn()
        with stubbed(net): out = linkedin.run_linkedin_post({'token': 't', 'text': 'Gas is up 4 cents.', 'image_path': str(f / 'gas.png')})
        kinds = [x[0] + (' init' if 'initializeUpload' in x[1] else '') for x in net.calls]
        self.assertEqual(kinds, ['GET', 'POST init', 'PUT', 'POST'])           # who, the upload address, the bytes, then the post
        self.assertEqual(net.calls[1][2]['initializeUploadRequest']['owner'], 'urn:li:person:ALEX1')
        self.assertEqual(net.calls[2][2], len(PNG))
        self.assertEqual(net.calls[3][2]['content'], {'media': {'id': 'urn:li:image:C1'}})
        self.assertEqual(out['rows'][0]['url'], 'https://www.linkedin.com/feed/update/urn:li:share:42')

    def test_no_picture_is_the_plain_post(self):
        net = LinkedIn()
        with stubbed(net): linkedin.run_linkedin_post({'token': 't', 'text': 'Hi', 'author': 'urn:li:person:a'})
        self.assertEqual(len(net.calls), 1); self.assertNotIn('content', net.calls[0][2])


class OnePress(unittest.TestCase):
    def setUp(self):
        s = server.store
        self.tid = s.create_task({'Title': 'A post about local gas prices', 'Kind': 'general', 'Status': 'open'}, 'owner')
        self.card = s.get_connector_by_type('linkedin')
        s.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 1, 'Secret': 'tok',
                          'ConfigJson': json.dumps({'member_name': 'Alex Doyle'})}, 'linkedin')
        f = outputs.folder(self.tid); f.mkdir(parents=True, exist_ok=True); (f / 'gas-prices.png').write_bytes(PNG)

    def tearDown(self):
        server.store.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 0}, 'test')
        shutil.rmtree(outputs.folder(self.tid), ignore_errors=True)       # the home is shared: another test's task of this number would offer the picture

    def propose(self, **kw):
        return c.post('/api/agent/propose', headers=agent(self.tid), json={
            'task_id': self.tid, 'action': 'run_tool', 'type': 'linkedin_post', 'connector_id': self.card['ConnectorId'],
            'why': 'Alex asked for a post with a visual', **kw})

    def test_proposed_waits_then_posts_with_the_picture_on_approve(self):
        net = LinkedIn()
        with stubbed(net):
            r = self.propose(text='Gas rose 4 cents this week.', image='gas-prices.png', image_path='C:/Windows/win.ini')
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(net.calls, [])                                   # nothing reached LinkedIn before the press
            rv = server.store.get_review(r.json()['review'])
            self.assertNotIn('image_path', json.loads(rv['DraftText']))      # a path is Taskuary's to resolve, never the agent's
            got = c.get(f'/api/tasks/{self.tid}/assistant').json()
            post = next(p for p in got['cards'] if p['ReviewId'] == rv['ReviewId'])
            self.assertEqual((post['network'], post['as'], post['Status']), ('LinkedIn', 'Alex Doyle', 'pending'))
            out = verdicts.decide(server.store, rv, 'approve', 'Gas rose 4 cents this week - here is why.')
        self.assertTrue(out['ok'], out)
        sent = [x for x in net.calls if x[0] == 'POST' and x[1].endswith('/rest/posts')][0][2]
        self.assertEqual(sent['commentary'], 'Gas rose 4 cents this week - here is why.')      # the owner's edit is what went
        self.assertEqual(sent['content']['media']['id'], 'urn:li:image:C1')
        kept = json.loads(server.store.get_review(rv['ReviewId'])['FinalText'])
        self.assertEqual(kept['result']['url'], 'https://www.linkedin.com/feed/update/urn:li:share:42')

    def test_a_picture_named_by_its_full_path_is_kept_by_its_name(self):
        """A real turn named the picture by its full path; the card builds its address from the name in the folder."""
        r = self.propose(text='Hi', image=str(outputs.folder(self.tid) / 'gas-prices.png'))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(json.loads(server.store.get_review(r.json()['review'])['DraftText'])['image'], 'gas-prices.png')

    def test_a_picture_the_agent_saved_anywhere_it_may_read_rides_on_the_card_as_its_copy_in_the_folder(self):
        """His live app, 2026-11-25: a Codex chat's picture was drawn by its own image tool into ~/.codex/generated_images/<thread> and copied
        to its work folder - and a post card took only the task's folder. Where the agent saved a picture never decides whether it rides:
        one in its work folder (by name or full path) or in its own CLI's pictures is copied into the task's folder and carried; one the read
        gate keeps from this task is refused, and nothing is copied."""
        import os
        from pathlib import Path
        from taskuary import agenttools
        work = outputs.work_folder(self.tid); (work / 'gate.png').write_bytes(PNG + b'work')
        server.store.save_session(self.tid, 'codex', '', 'thread-7f3a', 'k')                      # the chat's kept Codex conversation
        drawn = Path(os.environ['CODEX_HOME']) / 'generated_images' / 'thread-7f3a'; drawn.mkdir(parents=True, exist_ok=True)
        (drawn / 'exec-1.png').write_bytes(PNG + b'codex')
        for named, kept in (('gate.png', b'work'), (str(work / 'gate.png'), b'work'), (str(drawn / 'exec-1.png'), b'codex')):
            r = self.propose(text='Hi', image=named)
            self.assertEqual(r.status_code, 200, r.text)
            image = json.loads(server.store.get_review(r.json()['review'])['DraftText'])['image']
            self.assertEqual((outputs.folder(self.tid) / image).read_bytes(), PNG + kept, named)
        # ...an email's attachment takes the same road
        (f,) = agenttools.attached(server.store, self.tid, [str(drawn / 'exec-1.png')])
        self.assertEqual(f['name'], 'exec-1.png')
        # ...and a picture in a folder this task may not read - another CLI thread's, his own Documents - is no card's, and copied nowhere
        other = Path(os.environ['CODEX_HOME']) / 'generated_images' / 'thread-other'; other.mkdir(parents=True, exist_ok=True)
        docs = Path(os.environ['USERPROFILE']) / 'Documents'; docs.mkdir(parents=True, exist_ok=True)
        for p in (other / 'x.png', docs / 'y.png'):
            p.write_bytes(PNG)
            r = self.propose(text='Hi', image=str(p))
            self.assertFalse((outputs.folder(self.tid) / p.name).exists(), p)
            self.assertIn('no picture this task may read', r.text, p)

    def test_a_home_named_by_its_short_form_still_carries_the_picture(self):
        """A home given as C:/Users/ABCDEF~1 (an 8.3 short name, as %TEMP% often is) resolves to the long name, and one side of the
        comparison was never resolved: every picture post crashed. The short form is real where the disk makes one, else stood in for by
        a path that resolves to somewhere spelled differently - the same mismatch."""
        home = config.home()
        short = home.parent / '_alias' / '..' / home.name                   # resolves to home, spelled otherwise
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(1024)
            if ctypes.windll.kernel32.GetShortPathNameW(str(home), buf, 1024) and buf.value != str(home): short = type(home)(buf.value)
        except (AttributeError, OSError): pass
        self.assertNotEqual(str(short), str(short.resolve()))
        with mock.patch.object(outputs.config, 'home', lambda: short):
            r = self.propose(text='Hi', image=str(home / 'scratch' / 'outputs' / outputs.task_ref(self.tid) / 'gas-prices.png'))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(json.loads(server.store.get_review(r.json()['review'])['DraftText'])['image'], 'gas-prices.png')

    def test_a_tool_failure_comes_back_in_words(self):
        from taskuary import agenttools
        def run(name, a): raise ValueError("gas.png is not a file in your task folder - save the picture there first")
        out = agenttools.rpc({'id': 1, 'method': 'tools/call', 'params': {'name': 'propose', 'arguments': {}}}, run)['result']
        self.assertTrue(out['isError']); self.assertEqual(out['content'][0]['text'], 'gas.png is not a file in your task folder - save the picture there first')
        def boom(name, a): raise RuntimeError('database is locked')
        said = agenttools.rpc({'id': 1, 'method': 'tools/call', 'params': {'name': 'tick', 'arguments': {}}}, boom)['result']['content'][0]['text']
        self.assertNotIn('Error', said); self.assertNotIn('Traceback', said)
        def need(name, a): return a['item']
        said = agenttools.rpc({'id': 1, 'method': 'tools/call', 'params': {'name': 'tick', 'arguments': {}}}, need)['result']['content'][0]['text']
        self.assertEqual(said, agenttools.refusal('`item` was not given', 'call tick again with it'))

    def test_a_picture_the_agent_drew_rides_on_its_card_by_the_handle_its_tool_gave_and_is_drawn_there_only(self):
        """Walk 23, 2026-11-25: draw_image drew the picture into the chat and answered only `shown:1`; propose refused that handle ("no picture
        this task may read"), both post cards were queued with no picture, and the picture stood in the chat as a file of its own. A picture
        the agent drew is a file of its task by the handle its tool gave, by its name and by the path its answer says - and once a card
        carries it, the chat draws it on that card only, whichever tool showed it (the test below)."""
        from taskuary import agenttools, images, outbound
        s = server.store
        drew = {'data': PNG + b'drawn', 'mime': 'image/png', 'provider': 'pictures', 'label': 'Pictures', 'model': 'm', 'prompt': 'a four-day close'}
        with mock.patch.object(images, 'generate', return_value=drew), mock.patch.object(outbound, 'connect_fix', return_value=None):
            said = agenttools._call(s, self.tid, 'draw_image', {'prompt': 'a four-day close'}, {})
        [made] = list(outputs.folder(self.tid).glob('image-*.png'))
        self.assertIn(str(made), said)                                                                # ...its answer says where the file is
        self.assertEqual((outputs.pages(s, self.tid), outputs.calls(self.tid)), ([], []), 'drawn into the chat by itself: only a card or `show` draws it')
        row = json.loads(agenttools.show_files(s, self.tid, [str(made)]).partition(agenttools.FILES_MARK)[2])[0]      # ...shown, it has a handle too
        self.assertTrue(row['path'].startswith('shown:'))
        for handle in (row['path'], row['name'], str(outputs.folder(self.tid) / row['name'])):
            r = self.propose(text='We close the month in four days.', image=handle)
            self.assertEqual(r.status_code, 200, f'{handle}: {r.text}')
            f = outputs.named(self.tid, json.loads(s.get_review(r.json()['review'])['DraftText'])['image'])
            self.assertTrue(f and f.read_bytes() == PNG + b'drawn', handle)
        # ...and a handle of another task's picture is no file of this one
        other = s.create_task({'Title': 'Another post', 'Kind': 'general', 'Status': 'open'}, 'owner')
        self.assertIsNone(outputs.take(s, other, row['path']))

    def test_a_picture_a_card_carries_is_drawn_on_its_card_only_whichever_tool_showed_it_and_queued_or_drawn(self):
        """Walks 22 and 23: an agent `show`ed the picture it then put on a post - and the picture stood in the chat with Download beside the
        cards, the second post's too while its card waited behind the first. A file a card of the task carries is drawn on that card only."""
        from taskuary import agenttools
        s = server.store
        work = outputs.work_folder(self.tid)
        for n in ('x.png', 'linkedin.png', 'chart.png'): (work / n).write_bytes(PNG + n.encode())
        agenttools.show_files(s, self.tid, [str(work / 'x.png'), str(work / 'linkedin.png'), str(work / 'chart.png')])
        self.assertEqual(sorted(p['name'] for p in outputs.pages(s, self.tid)), ['chart.png', 'linkedin.png', 'x.png'])
        for n in ('x.png', 'linkedin.png'):                        # ...two cards in a row: the second waits behind the first, drawn nowhere yet
            self.assertEqual(self.propose(text=f'We close the month in four days ({n}).', image=str(work / n)).status_code, 200)
        self.assertEqual([p['name'] for p in outputs.pages(s, self.tid)], ['chart.png'], 'only the file handed to him on purpose stays in the chat')

    def test_a_video_rides_on_the_post_card_and_the_press_uploads_it_then_posts_with_it(self):
        """The owner, 2026-11-26: "we have linkedin connected, no need for browser" - asked for a post with a screen recording, the card took a
        picture only, the agent wrote the words to a file and went to the site with the video. A video LinkedIn takes rides on the card as a
        picture does; the press sends it in the parts LinkedIn names, finalizes them in order, and posts with the video's urn."""
        (outputs.folder(self.tid) / 'tour.mp4').write_bytes(mp4())
        net = LinkedInVideo()
        with stubbed(net):
            r = self.propose(text='A tour of the availability view.', image='tour.mp4')
            self.assertEqual(r.status_code, 200, r.text); self.assertEqual(net.calls, [])
            rv = server.store.get_review(r.json()['review'])
            self.assertEqual(json.loads(rv['DraftText'])['image'], 'tour.mp4')
            out = verdicts.decide(server.store, rv, 'approve', 'A tour of the availability view.')
        self.assertTrue(out['ok'], out)
        said = [x[0] + ' ' + x[1].split('linkedin.com')[-1].split('linkedin.test')[-1] for x in net.calls]
        self.assertEqual(said[-6:], ['POST /rest/videos?action=initializeUpload', 'PUT /v/0', 'PUT /v/1', 'POST /rest/videos?action=finalizeUpload',
                                     'GET /rest/videos/urn%3Ali%3Avideo%3AV1', 'POST /rest/posts'])
        self.assertEqual(sum(x[2] for x in net.calls if x[0] == 'PUT'), 80 * 1024, 'every byte of it, once')
        done = next(x[2] for x in net.calls if x[0] == 'POST' and 'finalizeUpload' in x[1])['finalizeUploadRequest']
        self.assertEqual(done, {'video': 'urn:li:video:V1', 'uploadToken': 'tok', 'uploadedPartIds': ['e0', 'e1']})
        self.assertEqual(net.calls[-1][2]['content']['media']['id'], 'urn:li:video:V1')

    def test_a_video_its_network_cannot_take_is_answered_with_that_fact_and_no_card_is_shown(self):
        "A WebM screen recording, one too long, and a video on a network whose card carries none: each answered with what the network takes and what the file is, nothing raised."
        f = outputs.folder(self.tid)
        (f / 'tour.webm').write_bytes(b'\x1aE\xdf\xa3' + b'\0' * 90000); (f / 'long.mp4').write_bytes(mp4(secs=45 * 60)); (f / 'tour.mp4').write_bytes(mp4())
        was = len(verdicts.unsent(server.store, self.tid))
        r = self.propose(text='A tour.', image='tour.webm')
        self.assertEqual(r.status_code, 422, r.text)
        self.assertIn('LinkedIn takes MP4 (H.264) video; tour.webm is WEBM', r.json()['detail'])
        self.assertNotIn('ffmpeg', r.text)                 # ...the fact, never a how-to: converting it is the agent's own work
        r = self.propose(text='A tour.', image='long.mp4')
        self.assertEqual(r.status_code, 422, r.text); self.assertIn('3 seconds to 30 minutes', r.text)
        self.assertIn('not a video', proposals.picture_why(self.tid, {'type': 'x_post', 'image': 'tour.mp4'}))
        self.assertEqual(len(verdicts.unsent(server.store, self.tid)), was, 'no card was shown')

    def test_a_picture_outside_the_task_folder_is_refused(self):
        r = self.propose(text='Hi', image='../../secret.png')
        self.assertEqual(r.status_code, 422, r.text)

    def test_a_network_that_takes_no_picture_from_here_carries_it_on_its_card_all_the_same(self):
        # the owner, 2026-11-20: every post card carries its picture - one Taskuary uploads none to is shown to save and add by hand
        self.assertEqual(proposals.picture_why(self.tid, {'type': 'bluesky_post', 'image': 'gas-prices.png'}), '')
        self.assertIn('no picture this task may read', proposals.picture_why(self.tid, {'type': 'bluesky_post', 'image': 'nowhere.png'}))



if __name__ == '__main__':
    unittest.main()




# ONE POST CARD PER NETWORK, EACH WITH ITS PICTURE, CONNECTED OR NOT (the owner's live routine, 2026-11-20: drafts for X, Reddit and LinkedIn went
# into one text file and only the connected one got a card - the agent was told of connected roads only)

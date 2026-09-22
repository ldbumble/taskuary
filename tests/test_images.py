"""Image models as a connector card: text in, a picture out, filed where the owner can see it.

Built like voice.py, which is the same shape of problem - several vendors, one thing wanted, the
owner picking whichever they already pay for. Eight cards on five wire shapes, because four of
them speak OpenAI's /v1/images/generations and Replicate reaches the long tail (FLUX, SDXL,
Ideogram) through one async poll rather than eight hand-written vendors.

Nothing here touches the network: every provider is exercised by asserting the REQUEST we build
and decoding the RESPONSE shape it answers with, which is where the bugs in this kind of code live.
"""
import base64
import json
import unittest
from unittest import mock

from taskuary import images
from taskuary.store import MemoryStore

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 32
B64 = base64.b64encode(PNG).decode()


def _resp(status=200, payload=None, content=None):
    r = mock.Mock(status_code=status, content=content or b'', text=json.dumps(payload or {}))
    r.json.return_value = payload or {}
    return r


def _conn(s, kind, cfg=None, secret='k'):
    row = next((c for c in s.list_connectors() if c['Type'] == kind), None)
    if row:
        s.save_connector({'ConnectorId': row['ConnectorId'], 'Secret': secret, 'Active': 1,
                          'ConfigJson': json.dumps(cfg or {})}, 'owner')
        return s.get_connector(row['ConnectorId'], with_secret=True)
    cid = s.save_connector({'Type': kind, 'Name': images.LABELS[kind], 'Secret': secret, 'Active': 1,
                            'ConfigJson': json.dumps(cfg or {})}, 'owner')
    return s.get_connector(cid, with_secret=True)


class TheCardsAgreeEverywhereTests(unittest.TestCase):
    """Four tables have to say the same thing or a card half-exists - the failure that put a CLI
    install button on master for two days. A parity test is cheaper than finding out later."""

    def test_every_type_has_a_label_and_a_wire_shape(self):
        for t in images.IMAGE_TYPES:
            self.assertIn(t, images.LABELS, f'{t} has no label')
            self.assertTrue(images.shape_of(t), f'{t} has no wire shape')

    def test_every_type_is_registered_as_a_connector_the_store_knows(self):
        from taskuary.store import DEFAULT_ROLES
        for t in images.IMAGE_TYPES:
            self.assertIn(t, DEFAULT_ROLES, f'{t} is missing from the store roles table')
            self.assertIn('tool', DEFAULT_ROLES[t], f'{t} must be callable as a tool')

    def test_every_type_has_a_card_in_the_connections_page(self):
        page = open('website/src/ConnectorsView.jsx', encoding='utf-8').read()
        for t in images.IMAGE_TYPES:
            self.assertIn(f'{t}: {{', page, f'{t} has no card in ConnectorsView')
        self.assertIn('AI — images', page)

    def test_every_type_is_seeded_so_the_group_is_not_empty(self):
        """The Connections page renders from connector ROWS, not from the type table -
        channelCards filters the rows it was given by Type. A type with no seeded row is a group
        with no cards in it, which is exactly what the owner got: an "AI - images" tab with
        nothing under it (2026-09-15). The roles table is not what puts a card on the page."""
        s = MemoryStore()
        have = {c['Type'] for c in s.list_connectors()}
        for t in images.IMAGE_TYPES:
            self.assertIn(t, have, f'{t} is not seeded, so its card never appears')

    def test_every_card_wears_a_brand_mark_rather_than_the_generic_sparkle(self):
        """chanCard falls back to the channel glyph when hasLogo is false, so eight image cards
        would all wear the same AI sparkle and tell you nothing about which is which - the exact
        thing logos.jsx was written to stop."""
        marks = open('website/src/logos.jsx', encoding='utf-8').read()
        for t in images.IMAGE_TYPES:
            self.assertTrue(f'LOGOS.{t} =' in marks or f'  {t}: (p)' in marks,
                            f'{t} has no brand mark, so its card gets the generic glyph')

    def test_every_type_can_be_tested_from_the_card(self):
        branch = open('taskuary/channels.py', encoding='utf-8').read()
        self.assertIn('images.test', branch)
        for t in images.IMAGE_TYPES:
            self.assertIn(t, branch, f'{t} is not in the connector test branch')


class ChoosingTheProviderTests(unittest.TestCase):
    def test_the_first_active_card_with_a_key_is_the_one_used(self):
        s = MemoryStore()
        self.assertIsNone(images.pick(s))
        _conn(s, 'openai_image')
        self.assertEqual(images.pick(s)['Type'], 'openai_image')

    def test_with_nothing_set_up_it_says_where_to_go(self):
        s = MemoryStore()
        with self.assertRaises(RuntimeError) as e: images.generate(s, 'a duck')
        self.assertIn('Connections', str(e.exception))

    def test_a_card_with_no_key_is_not_picked(self):
        s = MemoryStore()
        _conn(s, 'openai_image', secret='')
        self.assertIsNone(images.pick(s))


class TheOpenAICompatibleShapeTests(unittest.TestCase):
    """One code path, four cards."""

    def test_the_request_names_the_model_and_carries_the_key(self):
        s = MemoryStore(); c = _conn(s, 'openai_image', {'model': 'gpt-image-1'})
        with mock.patch.object(images.requests, 'post', return_value=_resp(payload={'data': [{'b64_json': B64}]})) as post:
            out = images.generate(s, 'a duck on a pond', size='1024x1024', c=c)
        url, kw = post.call_args.args[0], post.call_args.kwargs
        self.assertTrue(url.endswith('/images/generations'))
        self.assertEqual(kw['headers']['Authorization'], 'Bearer k')
        self.assertEqual(kw['json']['prompt'], 'a duck on a pond')
        self.assertEqual(kw['json']['model'], 'gpt-image-1')
        self.assertEqual(out['data'], PNG); self.assertEqual(out['provider'], 'openai_image')

    def test_a_url_answer_is_fetched_rather_than_handed_back_as_a_link(self):
        """DALL-E-style answers point at a signed URL that expires within the hour. The owner
        wants the picture on the task, not a link that dies before they open it."""
        s = MemoryStore(); c = _conn(s, 'openai_image')
        with mock.patch.object(images.requests, 'post', return_value=_resp(payload={'data': [{'url': 'https://x/i.png'}]})), \
             mock.patch.object(images.requests, 'get', return_value=_resp(content=PNG)) as get:
            out = images.generate(s, 'a duck', c=c)
        self.assertEqual(get.call_args.args[0], 'https://x/i.png'); self.assertEqual(out['data'], PNG)

    def test_azure_speaks_the_same_body_with_its_own_url_and_header(self):
        s = MemoryStore()
        c = _conn(s, 'azure_openai_image', {'endpoint': 'https://northwind.openai.azure.com', 'deployment': 'gpt-image-1'})
        with mock.patch.object(images.requests, 'post', return_value=_resp(payload={'data': [{'b64_json': B64}]})) as post:
            images.generate(s, 'a duck', c=c)
        url, kw = post.call_args.args[0], post.call_args.kwargs
        self.assertIn('/openai/deployments/gpt-image-1/images/generations', url)
        self.assertEqual(kw['headers']['api-key'], 'k')          # azure does not use Bearer
        self.assertNotIn('Authorization', kw['headers'])

    def test_a_local_server_needs_no_key_at_all(self):
        s = MemoryStore(); c = _conn(s, 'image_server', {'base_url': 'http://127.0.0.1:7860/v1'}, secret='')
        with mock.patch.object(images.requests, 'post', return_value=_resp(payload={'data': [{'b64_json': B64}]})) as post:
            images.generate(s, 'a duck', c=c)
        self.assertTrue(post.call_args.args[0].startswith('http://127.0.0.1:7860/v1'))


class TheOtherShapesTests(unittest.TestCase):
    def test_gemini_reads_the_picture_out_of_its_parts(self):
        s = MemoryStore(); c = _conn(s, 'gemini_image')
        payload = {'candidates': [{'content': {'parts': [{'text': 'here you go'},
                                                         {'inlineData': {'mimeType': 'image/png', 'data': B64}}]}}]}
        with mock.patch.object(images.requests, 'post', return_value=_resp(payload=payload)):
            self.assertEqual(images.generate(s, 'a duck', c=c)['data'], PNG)

    def test_stability_answers_with_the_bytes_themselves(self):
        s = MemoryStore(); c = _conn(s, 'stability_image')
        with mock.patch.object(images.requests, 'post', return_value=_resp(payload={'image': B64})) as post:
            self.assertEqual(images.generate(s, 'a duck', c=c)['data'], PNG)
        self.assertEqual(post.call_args.kwargs['headers']['Accept'], 'application/json')

    def test_openrouter_reads_the_image_off_a_chat_answer(self):
        s = MemoryStore(); c = _conn(s, 'openrouter_image')
        payload = {'choices': [{'message': {'images': [{'image_url': {'url': f'data:image/png;base64,{B64}'}}]}}]}
        with mock.patch.object(images.requests, 'post', return_value=_resp(payload=payload)):
            self.assertEqual(images.generate(s, 'a duck', c=c)['data'], PNG)

    def test_replicate_starts_a_prediction_and_waits_for_it(self):
        """The long tail - FLUX, SDXL, Ideogram - all arrive through this one async path."""
        s = MemoryStore(); c = _conn(s, 'replicate_image', {'model': 'black-forest-labs/flux-schnell'})
        started = _resp(payload={'id': 'p1', 'status': 'starting', 'urls': {'get': 'https://api.replicate.com/v1/predictions/p1'}})
        done = _resp(payload={'id': 'p1', 'status': 'succeeded', 'output': ['https://x/out.png']})
        with mock.patch.object(images.requests, 'post', return_value=started), \
             mock.patch.object(images.requests, 'get', side_effect=[done, _resp(content=PNG)]), \
             mock.patch.object(images.time, 'sleep'):
            self.assertEqual(images.generate(s, 'a duck', c=c)['data'], PNG)

    def test_a_failed_prediction_says_what_the_vendor_said(self):
        s = MemoryStore(); c = _conn(s, 'replicate_image')
        started = _resp(payload={'id': 'p1', 'status': 'starting', 'urls': {'get': 'https://g/p1'}})
        failed = _resp(payload={'id': 'p1', 'status': 'failed', 'error': 'NSFW content detected'})
        with mock.patch.object(images.requests, 'post', return_value=started), \
             mock.patch.object(images.requests, 'get', return_value=failed), \
             mock.patch.object(images.time, 'sleep'):
            with self.assertRaises(RuntimeError) as e: images.generate(s, 'a duck', c=c)
        self.assertIn('NSFW content detected', str(e.exception))


class WhenItGoesWrongTests(unittest.TestCase):
    def test_a_refused_key_says_so_rather_than_printing_json(self):
        s = MemoryStore(); c = _conn(s, 'openai_image')
        with mock.patch.object(images.requests, 'post', return_value=_resp(status=401, payload={'error': 'bad key'})):
            with self.assertRaises(RuntimeError) as e: images.generate(s, 'a duck', c=c)
        self.assertIn('the key was refused', str(e.exception))

    def test_an_answer_with_no_picture_in_it_is_an_error_not_empty_bytes(self):
        s = MemoryStore(); c = _conn(s, 'openai_image')
        with mock.patch.object(images.requests, 'post', return_value=_resp(payload={'data': []})):
            with self.assertRaises(RuntimeError) as e: images.generate(s, 'a duck', c=c)
        self.assertIn('no image', str(e.exception).lower())

    def test_an_empty_prompt_never_reaches_a_paid_endpoint(self):
        s = MemoryStore(); c = _conn(s, 'openai_image')
        with mock.patch.object(images.requests, 'post', side_effect=AssertionError('must not be called')):
            with self.assertRaises(RuntimeError): images.generate(s, '   ', c=c)


class TheToolAgentsCallTests(unittest.TestCase):
    def test_the_tool_is_registered_and_scoped(self):
        from taskuary import reports, scopes
        self.assertIn('image_generate', reports.REGISTRY)           # reports and the assistant can call it
        self.assertEqual(scopes.needs('image_generate'), 'read')   # it spends, but moves nothing upstream

    def test_a_generated_image_is_filed_on_the_message_so_it_shows_inline(self):
        s = MemoryStore(); _conn(s, 'openai_image')
        mid = s.add_message({'Channel': 'email', 'Direction': 'in', 'Subject': 'need a diagram',
                             'BodyText': 'x', 'SentAt': '2026-09-15T09:00:00'})
        with mock.patch.object(images.requests, 'post', return_value=_resp(payload={'data': [{'b64_json': B64}]})):
            out = images.run_image_generate(s, {'prompt': 'a duck'}, message_id=mid)
        atts = s.list_attachments(mid)
        self.assertEqual(len(atts), 1)
        self.assertTrue(str(atts[0]['ContentType']).startswith('image/'))
        self.assertIn('attachment_id', out)


if __name__ == '__main__':
    unittest.main()

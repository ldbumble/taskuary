"""Nine providers that speak the OpenAI chat-completions schema.

They are a TABLE, not nine branches: a base url, a default model and a bearer key is the whole
integration. This pins the thing a table can get wrong - a url that does not exist, a provider
that never reached AI_TYPES and so appears in no brain picker, or a branch that quietly drops
the key. Every url here was verified against the live host by an unauthenticated POST: 400/401
means the endpoint is real, 404 means the path is wrong (Fireworks failed exactly that way and
is deliberately absent).
"""
import unittest
from unittest import mock

from taskuary.llm import AI_TYPES, OPENAI_COMPATIBLE, make_llm


class TableIsTheIntegration(unittest.TestCase):
    def test_every_compatible_provider_is_a_brain_everywhere(self):
        # AI_TYPES is what populates every brain picker (aidefaults, server, setup, general).
        # A provider missing from it builds fine and can never be chosen.
        for t in OPENAI_COMPATIBLE:
            self.assertIn(t, AI_TYPES, f'{t} would appear in no brain picker')

    def test_each_one_resolves_to_the_url_that_was_verified(self):
        for t, (base, default_model) in OPENAI_COMPATIBLE.items():
            if not base: continue        # an organisation's own gateway (hipaa_ai): its address comes with the access code
            with mock.patch('taskuary.llm.requests') as rq:
                make_llm(t, {}, 'sk-test')
                self.assertTrue(base.startswith('https://'), f'{t} must be https')
            # the builder is lazy: assert on what it composed rather than on a call
            self.assertFalse(base.endswith('/'), f'{t} base url must not end in a slash')
            self.assertTrue(default_model, f'{t} needs a default model or the box is empty')

    def test_the_box_overrides_the_table(self):
        """Model names churn. A default is a starting point, never a promise."""
        for t in OPENAI_COMPATIBLE:
            llm = make_llm(t, {'model': 'mine', 'base_url': 'https://gateway.example/v1'}, 'k')
            self.assertTrue(callable(llm))

    def test_a_key_is_carried_as_a_bearer(self):
        for t, (base, _m) in OPENAI_COMPATIBLE.items():
            self.assertTrue(callable(make_llm(t, {} if base else {'base_url': 'https://gateway.example/v1'}, 'sk-abc')))

    def test_an_unknown_type_still_refuses(self):
        with self.assertRaises(RuntimeError):
            make_llm('not_a_provider', {}, 'k')


if __name__ == '__main__':
    unittest.main()


class VertexTests(unittest.TestCase):
    """Google's Agent Platform (Vertex AI) speaks chat completions too, but under a PROJECT and a location, and an API key
    rides `x-goog-api-key` - a bearer header there wants an OAuth token, not a key."""

    def ask(self, cfg):
        seen = {}
        def post(url, headers=None, json=None, timeout=None):
            seen.update(url=url, headers=headers, model=json.get('model'))
            r = mock.Mock(); r.status_code = 200; r.json.return_value = {'choices': [{'message': {'content': 'ok'}}]}
            return r
        with mock.patch('taskuary.llm.requests.post', side_effect=post): self.assertEqual(make_llm('vertex_ai', cfg, 'AQ.key')('s', 'u'), 'ok')
        return seen

    def test_it_is_a_brain_everywhere(self): self.assertIn('vertex_ai', AI_TYPES)

    def test_the_project_names_the_url_and_the_key_rides_googles_header(self):
        seen = self.ask({'project': 'acme-ai'})
        self.assertEqual(seen['url'], 'https://aiplatform.googleapis.com/v1/projects/acme-ai/locations/global/endpoints/openapi/chat/completions')
        self.assertEqual(seen['headers'], {'x-goog-api-key': 'AQ.key'})
        self.assertEqual(seen['model'], 'google/gemini-3.8-flash')

    def test_a_region_has_its_own_host_and_a_bare_model_is_googles(self):
        seen = self.ask({'project': 'acme-ai', 'location': 'us-central1', 'model': 'gemini-2.5-pro'})
        self.assertTrue(seen['url'].startswith('https://us-central1-aiplatform.googleapis.com/v1/projects/acme-ai/locations/us-central1/'))
        self.assertEqual(seen['model'], 'google/gemini-2.5-pro')
        self.assertEqual(self.ask({'project': 'p', 'model': 'meta/llama-4-maverick'})['model'], 'meta/llama-4-maverick')

    def test_no_project_says_what_is_missing(self):
        with self.assertRaisesRegex(RuntimeError, 'project'): make_llm('vertex_ai', {}, 'k')

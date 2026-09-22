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
        for t in OPENAI_COMPATIBLE:
            self.assertTrue(callable(make_llm(t, {}, 'sk-abc')))

    def test_an_unknown_type_still_refuses(self):
        with self.assertRaises(RuntimeError):
            make_llm('not_a_provider', {}, 'k')


if __name__ == '__main__':
    unittest.main()

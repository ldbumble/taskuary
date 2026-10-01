"""The model picker offers what the key can call AND can answer a prompt (llm.list_models).

Azure named its deployments - four chat models and an embedding one - and the picker offered all five as brains (the
owner, 2026-10-01). An embedding model cannot answer a prompt; picking it would leave the slot with nothing to say."""
import unittest
from unittest import mock

from taskuary import llm


class R:
    def __init__(self, ids): self.status_code, self._ids = 200, ids
    def json(self): return {'data': [{'id': i} for i in self._ids]}


class ModelListTests(unittest.TestCase):
    def test_azure_deployments_without_the_ones_that_cannot_answer(self):
        got = ['gpt-5.2-chat', 'gpt-4o', 'text-embedding-3-small', 'gpt-5.4', 'gpt-4.1']
        with mock.patch.object(llm.requests, 'get', return_value=R(got)):
            self.assertEqual(llm.list_models('azure_openai', {'endpoint': 'https://res.openai.azure.example'}, 'k'),
                             ['gpt-5.2-chat', 'gpt-4o', 'gpt-5.4', 'gpt-4.1'])

    def test_every_provider_drops_speech_image_and_moderation_models(self):
        got = ['gpt-4o-mini', 'whisper-1', 'tts-1', 'dall-e-3', 'omni-moderation-latest', 'gpt-4o-realtime-preview', 'gpt-image-1']
        with mock.patch.object(llm.requests, 'get', return_value=R(got)):
            self.assertEqual(llm.list_models('openai', {}, 'k'), ['gpt-4o-mini'])


if __name__ == '__main__':
    unittest.main()

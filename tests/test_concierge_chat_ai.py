"""THIS CHAT'S OWN BRAIN (the owner, 2026-10-29): the composer's model picker chooses the brain for this chat only - it never changes
Settings' AI defaults, and a New chat speaks with the Assistant's default again."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, general, server, terminal
from taskuary.store import MemoryStore


def store():
    s = MemoryStore()
    s.upsert_agent('claude', 'coding', 'cli', '{"cmd": "claude"}')
    return s


class ChatBrainTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch('taskuary.agents.default_pick', return_value='cli:claude'); p.start(); self.addCleanup(p.stop)
        w = mock.patch.object(server, '_warm_assistant', lambda: None); w.start(); self.addCleanup(w.stop)   # no live CLI left behind

    def test_a_chat_picks_its_own_brain_and_settings_stay_as_they_were(self):
        s = store()
        s.set_setting(concierge.AI_KEY, 'cli:claude', 't'); s.set_setting(concierge.MODEL_KEY, 'sonnet', 't')
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            c = TestClient(server.app)
            st = c.get('/api/concierge').json()
            self.assertEqual((st['pick'], st['model'], st['chatPick'], st['defaultPick']), ('cli:claude', 'sonnet', False, 'cli:claude'))
            out = c.post('/api/concierge/chat-ai', json={'pick': 'connector:3', 'model': 'gpt-5'}).json()
            self.assertEqual((out['pick'], out['model'], out['chatPick']), ('connector:3', 'gpt-5', True))
            self.assertEqual((concierge.pick(s), concierge.model_of(s)), ('connector:3', 'gpt-5'), "the chat speaks on its own choice")
            self.assertEqual((s.get_setting(concierge.AI_KEY), s.get_setting(concierge.MODEL_KEY)), ('cli:claude', 'sonnet'), "Settings never change")
            st = c.get('/api/concierge').json()
            self.assertEqual((st['pick'], st['chatPick'], st['defaultPick']), ('connector:3', True, 'cli:claude'))
            # ...back to the default by an empty pick
            self.assertEqual(c.post('/api/concierge/chat-ai', json={'pick': ''}).json()['pick'], 'cli:claude')
            self.assertEqual(concierge.model_of(s), 'sonnet')

    def test_a_new_chat_is_back_on_the_assistants_default(self):
        s = store()
        tid = general.dock_task(s)[0]['TaskId']
        s.set_setting(f'{concierge.CHAT_AI}:{tid}', '{"pick": "connector:3", "model": ""}', 't')
        self.assertEqual(concierge.pick(s), 'connector:3')
        s.set_setting('assistant_dock_task_id', str(tid + 1000), 't')        # a New chat is another dock task
        self.assertEqual(concierge.pick(s), 'cli:claude')
        self.assertEqual(concierge.chat_choice(s), {})


if __name__ == '__main__':
    unittest.main()

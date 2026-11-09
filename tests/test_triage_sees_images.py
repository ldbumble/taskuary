"""TRIAGE ON CLAUDE SEES THE PICTURE (the owner, 2026-11-09): a chat line that was only a screenshot of an export error became its own
task, "read <sender>'s image", instead of joining the export-error task already open - the CLI brain dropped the image, and triage has no
tools to open a file. A one-shot claude now gets the image as a block in its stream-json input; a CLI that cannot take one keeps today's."""
import json
from unittest import mock

from taskuary import agents

class Claude:
    "A stand-in for the claude process (spawn.popen): what it was launched with and what it read, kept; one stream-json result back."
    seen = {}
    def __init__(self, cmd, *a, **k):
        import io, threading
        Claude.seen, self.done, self.returncode = {'argv': [str(x) for x in cmd]}, threading.Event(), 0
        me = self
        class In(io.StringIO):
            def close(s): Claude.seen['stdin'] = s.getvalue(); me.done.set()
        self.stdin, self.stderr = In(), io.StringIO('')
    @property
    def stdout(self):
        self.done.wait(10)
        yield json.dumps({'type': 'result', 'subtype': 'success', 'result': '{"intent": "reply"}', 'session_id': 's1'}) + '\n'
    def wait(self, timeout=None): return 0
    def poll(self): return 0
    def kill(self): pass
PNG = ('image/png', 'iVBORw0KGgo=')


def run(tmp_path, args, images):
    with mock.patch.object(agents, '_resolve_cmd', lambda name: ['claude']), mock.patch.object(agents.spawn, 'popen', Claude):
        out, _sid, _ = agents.run_cli({'cmd': 'claude', 'args': args, 'cwd': str(tmp_path)}, 'What is this message?', lambda *a, **k: None, images=images)
    return out, Claude.seen


def test_a_one_shot_claude_is_shown_the_picture_as_an_image_block(tmp_path):
    out, seen = run(tmp_path, ['-p', '--output-format', 'stream-json', '--verbose', '--tools', ''], [PNG])
    assert '"intent"' in out
    assert seen['argv'][seen['argv'].index('--input-format') + 1] == 'stream-json'
    msg = json.loads(seen['stdin'])
    assert msg['type'] == 'user'
    img, text = msg['message']['content']
    assert img == {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': PNG[1]}}     # the picture first
    assert text == {'type': 'text', 'text': 'What is this message?'}


def test_no_picture_or_a_cli_that_cannot_take_one_keeps_the_plain_prompt(tmp_path):
    _out, seen = run(tmp_path, ['-p', '--output-format', 'stream-json', '--verbose'], None)
    assert '--input-format' not in seen['argv'] and seen['stdin'] == 'What is this message?'
    _out, seen = run(tmp_path, ['-p'], [PNG])                     # plain text out: no stream-json input to carry it
    assert '--input-format' not in seen['argv'] and seen['stdin'] == 'What is this message?'
    assert not agents.sees_images('codex', ['exec', '--json'])


def test_the_cli_brain_hands_its_images_on(monkeypatch):
    from taskuary import llm
    from taskuary.store import MemoryStore
    got = {}
    monkeypatch.setattr(agents, 'agent_row', lambda store, name: {'Config': json.dumps({'cmd': 'claude'})})
    monkeypatch.setattr(agents, 'with_cmd', lambda prof, store=None: prof)
    def fake_run(prof, prompt, trace, resume=None, images=None, **kw): got['images'] = images; return '{"intent": "reply"}', 's1', None
    monkeypatch.setattr(agents, 'run_cli', fake_run)
    brain = llm.make_cli_llm(MemoryStore(), 'claude')
    brain('You are triage.', 'What is this message?', images=[PNG])
    assert got['images'] == [PNG]

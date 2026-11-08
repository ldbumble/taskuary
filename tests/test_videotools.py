"""VIDEO TOOLS (videotools.py, the owner 2026-11-08): a vendor's remote MCP server added to the agent CLIs here, a skill put on disk with
its key, and a clip made on a key card - every command stood in for, nothing installed and nothing reached."""
import json, tempfile, unittest
from pathlib import Path
from unittest import mock

from taskuary import sendfilter, videotools as vt
from taskuary.store import MemoryStore

EXE = {'claude': r'C:\bin\claude.exe', 'codex': r'C:\bin\codex.exe', 'git': 'git', 'uv': r'C:\bin\uv.exe', 'ffmpeg': r'C:\bin\ffmpeg.exe'}


class Machine:
    "A computer as the card sees it: which programs are here, which servers each CLI has, and a skills folder of its own."
    def __init__(self, have=EXE, claude=(), codex=()):
        self.have, self.servers, self.ran = dict(have), {'claude': set(claude), 'codex': set(codex)}, []
        self.root = Path(tempfile.mkdtemp(prefix='tq-skills-'))
    def run(self, argv, cwd=None, timeout=0):
        self.ran.append((list(argv), cwd))
        if argv[1:3] == ['mcp', 'add']: self.servers['claude' if 'claude' in argv[0] else 'codex'].add(argv[-1] if 'claude' in argv[0] else argv[3])
        if argv[1] == 'clone': (Path(argv[-1])).mkdir(parents=True); (Path(argv[-1]) / 'SKILL.md').write_text('x')
        return 0, 'ok'
    def __enter__(self):
        self.ps = [mock.patch.object(vt, '_which', side_effect=lambda c: self.have.get(c, '')),
                   mock.patch.object(vt, 'skills_root', return_value=self.root),
                   mock.patch.object(sendfilter, 'claude_servers', side_effect=lambda: {n: {} for n in self.servers['claude']}),
                   mock.patch.object(sendfilter, 'codex_servers', side_effect=lambda: {n: {} for n in self.servers['codex']})]
        for p in self.ps: p.start()
        return self
    def __exit__(self, *a):
        for p in self.ps: p.stop()


class TheMcpRoad(unittest.TestCase):
    def test_each_cli_gets_its_own_spelling(self):
        self.assertEqual(vt.add_argv('claude', 'claude', 'invideo', 'https://mcp.invideo.io/mcp'),
                         ['claude', 'mcp', 'add', '--transport', 'http', '--scope', 'user', 'invideo', 'https://mcp.invideo.io/mcp'])
        self.assertEqual(vt.add_argv('codex', 'codex', 'invideo', 'https://mcp.invideo.io/mcp'),
                         ['codex', 'mcp', 'add', 'invideo', '--url', 'https://mcp.invideo.io/mcp'])

    def test_add_registers_where_missing_keeps_it_for_the_send_filter_and_turns_the_card_on(self):
        s = MemoryStore()
        with Machine(claude={'descript'}) as m:                          # already in Claude Code, not in Codex
            self.assertFalse(vt.state(s, 'descript')['ready'])            # ...so Add still has Codex to do
            out = vt.add(s, 'descript', runner=m.run)
        self.assertEqual([a[0] for a, _ in m.ran], [EXE['codex']])        # only the CLI that lacked it was touched
        self.assertEqual(m.ran[0][0][1:], ['mcp', 'add', 'descript', '--url', 'https://api.descript.com/v2/mcp'])
        self.assertTrue(out['ready'] and all(v['added'] for v in out['clis'].values()))
        self.assertIn('codex mcp login descript', ' '.join(out['sign_in']))
        self.assertEqual(json.loads(s.get_setting(sendfilter.OVERRIDES))['descript/*'], 'keep')
        self.assertTrue(s.get_connector_by_type('descript')['Active'])
        with Machine(claude={'descript'}, codex={'descript'}): self.assertIn('ready in Claude Code, Codex', vt.test(s, 'descript'))

    def test_no_agent_cli_here_says_so_and_adds_nothing(self):
        s = MemoryStore()
        with Machine(have={}) as m:
            st = vt.add(s, 'invideo', runner=m.run)
            with self.assertRaises(RuntimeError): vt.test(s, 'invideo')
        self.assertEqual((m.ran, st['ready'], st['missing']), ([], False, ['Claude Code or Codex on this computer']))
        self.assertFalse(s.get_setting(sendfilter.OVERRIDES))
        self.assertFalse(s.get_connector_by_type('invideo')['Active'])

    def test_the_demo_shows_nobodys_machine_and_installs_nothing(self):
        with mock.patch('taskuary.demo.enabled', return_value=True), Machine(claude={'opusclip'}) as m:
            self.assertEqual((vt.state(MemoryStore(), 'opusclip')['clis'], vt.state(MemoryStore(), 'opusclip')['demo']), ({}, True))
            with self.assertRaises(RuntimeError): vt.add(MemoryStore(), 'opusclip', runner=m.run)
        self.assertEqual(m.ran, [])


class TheSkillRoad(unittest.TestCase):
    def eleven(self, s, key='el-key'):
        c = s.get_connector_by_type('elevenlabs_stt'); s.save_connector({'ConnectorId': c['ConnectorId'], 'Secret': key}, 'test')

    def test_video_use_is_cloned_synced_and_given_the_elevenlabs_key(self):
        s = MemoryStore(); self.eleven(s)
        with Machine() as m:
            self.assertFalse(vt.state(s, 'video_use')['skill']['here'])
            out = vt.add(s, 'video_use', runner=m.run)
            d = m.root / 'video-use'
            self.assertEqual([a[1] for a, _ in m.ran], ['clone', 'sync'])
            self.assertEqual(m.ran[1][1], str(d))                        # uv sync runs in the skill's own folder
            self.assertIn('ELEVENLABS_API_KEY=el-key', (d / '.env').read_text())
            self.assertTrue(out['ready']); self.assertTrue(s.get_connector_by_type('video_use')['Active'])

    def test_without_uv_it_makes_a_venv_and_pip_installs(self):
        s = MemoryStore(); self.eleven(s)
        with Machine(have={**{k: v for k, v in EXE.items() if k != 'uv'}, 'python': 'python'}) as m:
            vt.add(s, 'video_use', runner=m.run)
        self.assertEqual([a[1:3] for a, _ in m.ran[1:]], [['-m', 'venv'], ['install', '-e']])

    def test_missing_ffmpeg_and_key_are_said_and_the_card_stays_off(self):
        s = MemoryStore()
        with Machine(have={k: v for k, v in EXE.items() if k != 'ffmpeg'}) as m:
            out = vt.add(s, 'video_use', runner=m.run)
        self.assertFalse(out['ready'])
        self.assertEqual(len(out['missing']), 2)
        self.assertTrue(any('ffmpeg' in x for x in out['missing']) and any('ElevenLabs' in x for x in out['missing']))
        self.assertFalse(s.get_connector_by_type('video_use')['Active'])

    def test_an_existing_env_keeps_its_other_lines(self):
        d = Path(tempfile.mkdtemp()); (d / '.env').write_text('OTHER=1\nELEVENLABS_API_KEY=old\n')
        vt._write_env(d, 'ELEVENLABS_API_KEY', 'new')
        self.assertEqual((d / '.env').read_text().splitlines(), ['OTHER=1', 'ELEVENLABS_API_KEY=new'])

    def test_vidova_rides_both_roads(self):
        s = MemoryStore()
        with Machine(have={'claude': EXE['claude'], 'npx': 'npx'}) as m:
            vt.add(s, 'vidova', runner=m.run)
        self.assertEqual(m.ran[0][0][1:], ['mcp', 'add', '--transport', 'http', '--scope', 'user', 'vidova', 'https://mcp.vidova.ai/mcp'])
        self.assertEqual(m.ran[1][0], ['npx', '--yes', 'skills', 'add', 'youneslaaroussi/vidova-skills', '-g', '-y', '-a', 'claude-code'])


class R:
    def __init__(self, j, content=b''): self._j, self.content, self.status_code, self.text = j, content, 200, json.dumps(j)
    def json(self): return self._j
    def raise_for_status(self): pass


class AClipOnAKeyCard(unittest.TestCase):
    def test_kling_starts_polls_and_files_the_clip_in_the_tasks_outputs(self):
        out = Path(tempfile.mkdtemp())
        gets = [R({'data': [{'status': 'processing'}]}), R({'data': [{'status': 'succeeded', 'outputs': [{'type': 'video', 'url': 'https://x.test/v.mp4'}]}]}),
                R({}, b'MP4')]
        with mock.patch('requests.post', return_value=R({'data': {'id': 't1'}})) as post, mock.patch('requests.get', side_effect=gets), \
                mock.patch('time.sleep'), mock.patch('taskuary.outputs.folder', return_value=out):
            head, body = vt.run_kling_video({'api_key': 'k', 'prompt': 'a cat on a skateboard', 'task_id': 7, 'seconds': 10, 'ratio': '9:16'})
        self.assertEqual(post.call_args.args[0], 'https://api-singapore.klingai.com/text-to-video/kling-2.6')
        self.assertEqual(post.call_args.kwargs['json']['settings'], {'duration': 10, 'aspect_ratio': '9:16'})
        self.assertIn("TQ-0007's outputs", head)
        self.assertEqual(Path(json.loads(body)['file']).read_bytes(), b'MP4')

    def test_runway_uses_the_image_cards_key_and_a_failure_says_why(self):
        from taskuary.reports import CARD_OF, resolve_cfg
        self.assertEqual(CARD_OF['runway_video'], 'runway_image')
        s = MemoryStore(); c = s.get_connector_by_type('runway_image'); s.save_connector({'ConnectorId': c['ConnectorId'], 'Secret': 'rw'}, 't')
        self.assertEqual(resolve_cfg(s, {'type': 'runway_video'})['api_key'], 'rw')
        with mock.patch('requests.post', return_value=R({'id': 'r1'})) as post, mock.patch('requests.get', return_value=R({'status': 'FAILED', 'failure': 'nsfw'})), \
                mock.patch('time.sleep'), self.assertRaisesRegex(RuntimeError, 'Runway: nsfw'):
            vt.run_runway_video({'api_key': 'rw', 'prompt': 'p', 'task_id': 3, 'image_url': 'https://x.test/a.png'})
        self.assertTrue(post.call_args.args[0].endswith('/image_to_video'))
        self.assertEqual(post.call_args.kwargs['json']['promptImage'], 'https://x.test/a.png')

    def test_no_task_no_clip(self):
        with self.assertRaisesRegex(RuntimeError, 'task'): vt.run_kling_video({'api_key': 'k', 'prompt': 'p'})


if __name__ == '__main__':
    unittest.main()

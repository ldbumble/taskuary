"""Config writer tests - the UI persists agents/settings, so save() must round-trip
exactly through stdlib tomllib.
"""
import os, unittest
from unittest import mock
try: import tomllib
except ImportError: import tomli as tomllib
from taskuary import config, cli


class TomlTests(unittest.TestCase):
    def test_round_trip(self):
        cfg = {'server': {'host': '127.0.0.1', 'port': 7787},
               'agents': {'coder': {'cmd': 'claude', 'args': ['-p', '--output-format', 'json'],
                                    'resume_args': ['--resume'], 'timeout': 1500,
                                    'cwd_map': {'you/your-repo': 'C:/src/your-repo'}}},
               'github': {'token': 'ghp_x"quote', 'default_repo': 'a/b'}}
        self.assertEqual(tomllib.loads(config.dumps_toml(cfg)), cfg)

    def test_scalar_types(self):
        cfg = {'x': {'i': 3, 'f': 1.5, 'b': True, 's': 'line\nbreak \\ slash'}}
        self.assertEqual(tomllib.loads(config.dumps_toml(cfg)), cfg)

    def test_save_then_load(self):
        cfg = config.load()
        cfg['agents']['t2'] = {'cmd': 'echo', 'args': ['hi'], 'timeout': 5}
        config.save(cfg)
        again = config.load()
        self.assertEqual(again['agents']['t2'], {'cmd': 'echo', 'args': ['hi'], 'timeout': 5})

    def test_env_overrides_server_bind(self):
        # Docker sets these so the process listens on 0.0.0.0 without rewriting config.toml
        with mock.patch.dict(os.environ, {'TASKUARY_HOST': '0.0.0.0', 'TASKUARY_PORT': '9000',
                                          'TASKUARY_TOKEN': 'abc'}):
            cfg = config.load()
        self.assertEqual((cfg['server']['host'], cfg['server']['port'], cfg['server']['token']),
                         ('0.0.0.0', 9000, 'abc'))

    def test_env_overrides_do_not_persist_on_agent_save(self):
        """Runtime overlays must not round-trip through save() — that's how Docker was
        writing host = 0.0.0.0 and token = None onto the volume."""
        path = config.home() / 'config.toml'
        previous = path.read_text(encoding='utf-8') if path.exists() else None
        stored = {'host': '127.0.0.1', 'port': 7787, 'token': 'stored-secret'}
        path.write_text('[server]\nhost = "127.0.0.1"\nport = 7787\ntoken = "stored-secret"\n',
                        encoding='utf-8')
        try:
            env_empty = {'TASKUARY_HOST': '0.0.0.0', 'TASKUARY_PORT': '9000', 'TASKUARY_TOKEN': ''}
            with mock.patch.dict(os.environ, env_empty):
                runtime = config.load()
                self.assertEqual((runtime['server']['host'], runtime['server']['port'],
                                  runtime['server']['token']),
                                 ('0.0.0.0', 9000, 'stored-secret'))  # empty env does not disable
                runtime.setdefault('agents', {})['overlay'] = {'cmd': 'echo', 'timeout': 5}
                config.save(runtime)
                # the running object keeps the overlay after save
                self.assertEqual(runtime['server']['host'], '0.0.0.0')
                self.assertEqual(runtime['server']['token'], 'stored-secret')
            raw = path.read_text(encoding='utf-8')
            self.assertEqual(tomllib.loads(raw)['server'], stored)
            self.assertNotIn('0.0.0.0', raw)
            self.assertNotIn('None', raw)
            self.assertEqual(tomllib.loads(raw)['agents']['overlay']['cmd'], 'echo')

            with mock.patch.dict(os.environ, {'TASKUARY_HOST': '0.0.0.0', 'TASKUARY_TOKEN': 'from-env'}):
                runtime = config.load()
                self.assertEqual(runtime['server']['token'], 'from-env')
                runtime.setdefault('agents', {})['overlay2'] = {'cmd': 'true'}
                config.save(runtime)
                self.assertEqual(runtime['server']['token'], 'from-env')  # still the overlay
            disk = tomllib.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(disk['server'], stored)
            self.assertEqual(disk['agents']['overlay2']['cmd'], 'true')
        finally:
            if previous is None: path.unlink(missing_ok=True)
            else: path.write_text(previous, encoding='utf-8')

    def test_dumps_toml_omits_none(self):
        dumped = config.dumps_toml({'server': {'host': '127.0.0.1', 'token': None}})
        self.assertNotIn('None', dumped)
        self.assertEqual(tomllib.loads(dumped)['server'], {'host': '127.0.0.1'})

    def test_public_url_rewrites_wildcard_bind(self):
        self.assertEqual(cli.public_url('0.0.0.0', 7787), 'http://127.0.0.1:7787')
        self.assertEqual(cli.public_url('::', 7787), 'http://127.0.0.1:7787')
        self.assertEqual(cli.public_url('127.0.0.1', 7787), 'http://127.0.0.1:7787')
        self.assertEqual(cli.public_url('10.0.0.5', 9000), 'http://10.0.0.5:9000')


if __name__ == '__main__':
    unittest.main()

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
        with mock.patch.dict(os.environ, {'TASKUARY_TOKEN': ''}):
            self.assertIsNone(config.load()['server'].get('token'))

    def test_public_url_rewrites_wildcard_bind(self):
        self.assertEqual(cli.public_url('0.0.0.0', 7787), 'http://127.0.0.1:7787')
        self.assertEqual(cli.public_url('::', 7787), 'http://127.0.0.1:7787')
        self.assertEqual(cli.public_url('127.0.0.1', 7787), 'http://127.0.0.1:7787')
        self.assertEqual(cli.public_url('10.0.0.5', 9000), 'http://10.0.0.5:9000')


if __name__ == '__main__':
    unittest.main()

"""Config writer tests - the UI persists agents/settings, so save() must round-trip
exactly through stdlib tomllib.
"""
import unittest
try: import tomllib
except ImportError: import tomli as tomllib
from taskuary import config


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


if __name__ == '__main__':
    unittest.main()

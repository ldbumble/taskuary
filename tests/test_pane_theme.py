"""A new Claude session opens in the theme of the pane it is drawn in: Claude paints its own text colours, white under its
dark theme, and they vanished on the white pane that became the default (2026-10-07)."""
import json, unittest
from unittest import mock
from taskuary import terminal, hooks
from taskuary.store import MemoryStore


def theme_of(args):
    return json.loads(open(args[1], encoding='utf-8').read())['theme'] if args else None


class PaneThemeTests(unittest.TestCase):
    def setUp(self):                    # the owner's real instance: its hooks are user-wide, so the file is the theme alone
        p = mock.patch.object(hooks, 'user_wide', return_value=True); p.start(); self.addCleanup(p.stop)

    def test_blank_is_the_white_default_and_dark_follows_the_picker(self):
        s = MemoryStore()
        args = terminal.claude_theme_args(s, own='dark')
        self.assertEqual(args[0], '--settings'); self.assertEqual(theme_of(args), 'light')
        s.set_setting('pane_theme', 'dark', 't')
        self.assertEqual(theme_of(terminal.claude_theme_args(s, own='dark')), 'dark')
        self.assertEqual(theme_of(terminal.claude_theme_args(s, own='')), 'dark')

    def test_a_variant_keeps_its_kind_and_a_custom_theme_is_left_alone(self):
        s = MemoryStore()
        self.assertEqual(theme_of(terminal.claude_theme_args(s, own='dark-daltonized')), 'light-daltonized')
        self.assertEqual(theme_of(terminal.claude_theme_args(s, own='dark-ansi')), 'light-ansi')
        self.assertEqual(terminal.claude_theme_args(s, own='catppuccin-mocha'), [], 'a plugin theme the owner chose is theirs')


class SecondInstanceTests(unittest.TestCase):
    """Not the owner's real instance (a demo, a second home): it writes no user-wide hooks, so each Claude session it launches
    carries them in its one --settings file, theme beside them - and a custom theme still left alone."""
    def test_the_session_file_carries_the_hooks_with_the_theme(self):
        s = MemoryStore()
        self.assertFalse(hooks.user_wide())                      # a test's home is never the real one
        d = json.load(open(terminal.claude_theme_args(s, own='dark')[1], encoding='utf-8'))
        self.assertEqual(d['theme'], 'light')
        self.assertTrue(all(hooks.MARK in d['hooks'][e][0]['hooks'][0]['command'] for e in hooks.EVENTS))
        self.assertEqual(d['hooks']['PreToolUse'][0]['matcher'], 'AskUserQuestion')
        d = json.load(open(terminal.claude_theme_args(s, own='catppuccin-mocha')[1], encoding='utf-8'))
        self.assertNotIn('theme', d); self.assertIn('Stop', d['hooks'])

    def test_it_never_writes_the_user_wide_files(self):
        with mock.patch('os.path.expanduser', side_effect=AssertionError('touched the user home')):
            self.assertFalse(hooks.install_user('claude', base='http://127.0.0.1:1', token='t'))

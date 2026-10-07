"""A new Claude session opens in the theme of the pane it is drawn in: Claude paints its own text colours, white under its
dark theme, and they vanished on the white pane that became the default (2026-10-07)."""
import json, unittest
from taskuary import terminal
from taskuary.store import MemoryStore


def theme_of(args):
    return json.loads(open(args[1], encoding='utf-8').read())['theme'] if args else None


class PaneThemeTests(unittest.TestCase):
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

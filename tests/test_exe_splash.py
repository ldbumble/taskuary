"""The exe is on screen the instant it is double-clicked (the owner, 2026-10-15: "when you hit taskuary.exe it should startup right
away instant ... it doesn't matter if it takes a minute. you can also do a circle showing how long it takes"): the launcher's own
splash before the one-file bundle unpacks, then the window's own spinner and seconds until the app is up."""
import re, sys, unittest
from pathlib import Path
from unittest import mock

from taskuary import desktop

ROOT = Path(desktop.__file__).resolve().parent.parent


class SplashTests(unittest.TestCase):
    def test_the_exe_build_shows_the_launchers_splash_first(self):
        spec = (ROOT / 'taskuary.spec').read_text(encoding='utf-8')
        self.assertIn("Splash('assets/splash.png'", spec)
        self.assertRegex(spec, r"EXE\(pyz, a\.scripts, splash, splash\.binaries,")
        self.assertTrue((ROOT / 'assets' / 'splash.png').stat().st_size > 1000)

    def test_the_app_hands_over_from_it_and_is_a_no_op_outside_the_exe(self):
        desktop.splash('Starting'); desktop.splash()                       # no pyi_splash here: nothing happens, nothing raises
        fake = mock.Mock()
        with mock.patch.dict(sys.modules, {'pyi_splash': fake}):
            desktop.splash('Starting Taskuary...'); desktop.splash()
        fake.update_text.assert_called_once_with('Starting Taskuary...'); fake.close.assert_called_once()

    def test_the_window_waits_with_a_spinner_and_the_seconds_and_a_stall_shows_neither(self):
        self.assertIn('class="r"', desktop.SPLASH); self.assertIn('id="e"', desktop.SPLASH)
        self.assertIn('the first start can take a minute', desktop.SPLASH)
        self.assertNotIn('class="r"', desktop.STALLED); self.assertIn('could not start', desktop.STALLED)

    def test_the_pages_made_from_it_say_their_own_words(self):
        """STALLED and the goodbye are SPLASH with its words swapped: a reworded splash must not leave them saying "Loading"."""
        bye = desktop.goodbye_html('See you tomorrow.')
        for page in (desktop.STALLED, bye):
            self.assertNotIn('Loading your work', page); self.assertNotIn('class="r"', page)
        self.assertIn('See you tomorrow.', bye); self.assertIn('Taskuary is closing', bye)


if __name__ == '__main__': unittest.main()

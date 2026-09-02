"""When Windows refuses the update, say which refusal it is.

Reported 2026-09-02 from Settings → Updates:
    [Errno 13] Permission denied: 'C:\\Users\\uri\\Downloads\\Taskuary.new.exe'
A true sentence that tells the owner nothing they can act on - and it invites the two wrong
answers, run as administrator and install as a service, neither of which touches any of the
three real causes.
"""
import tempfile, unittest
from pathlib import Path
from unittest import mock

from taskuary import update

DENIED = PermissionError(13, 'Permission denied')


class WhyRefusedTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix='tq_dl_'))
        self.exe = self.d / 'Taskuary.exe'
        self.exe.write_bytes(b'MZ')
        self.new = self.d / 'Taskuary.new.exe'

    def test_a_leftover_from_last_time_says_to_delete_it(self):
        self.new.write_bytes(b'MZ')
        why = update._why_refused(self.new, self.exe, DENIED)
        self.assertIn('from an earlier attempt', why)
        self.assertIn(str(self.new), why)                       # the exact file to remove
        self.assertIn('press Update again', why)

    def test_a_folder_that_takes_files_but_not_programs_names_the_setting(self):
        why = update._why_refused(self.new, self.exe, DENIED)
        self.assertIn('Controlled Folder Access', why)
        self.assertIn('Ransomware protection', why)             # where to click
        self.assertIn('folder of its own', why)                 # ...or sidestep it entirely

    def test_a_folder_nothing_can_be_written_to_says_admin_will_not_help(self):
        """The wrong answer this error keeps inviting, refused in the message itself."""
        with mock.patch.object(Path, 'write_bytes', side_effect=PermissionError(13, 'nope')):
            why = update._why_refused(self.new, self.exe, DENIED)
        self.assertIn('administrator does not help', why)
        self.assertIn('on the program, not on your account', why)

    def test_the_write_test_never_leaves_anything_behind(self):
        before = set(p.name for p in self.d.iterdir())
        update._why_refused(self.new, self.exe, DENIED)
        self.assertEqual(set(p.name for p in self.d.iterdir()), before)


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix='tq_ap_'))
        self.exe = self.d / 'Taskuary.exe'
        self.exe.write_bytes(b'MZ')

    def test_a_refusal_becomes_the_explanation(self):
        with mock.patch.object(update.sys, 'executable', str(self.exe)), \
             mock.patch.object(update, '_download', side_effect=DENIED):
            with self.assertRaises(RuntimeError) as cm:
                update._apply_exe('https://example.invalid/Taskuary.exe')
        said = str(cm.exception)
        self.assertIn('could not be saved next to Taskuary.exe', said)
        self.assertIn('Controlled Folder Access', said)
        self.assertIn('Windows said:', said)                    # the original, still there to quote

    def test_anything_that_is_not_a_refusal_is_left_alone(self):
        """A short download or a missing asset must keep saying what it says."""
        with mock.patch.object(update.sys, 'executable', str(self.exe)), \
             mock.patch.object(update, '_download', side_effect=RuntimeError('download stopped short')):
            with self.assertRaisesRegex(RuntimeError, 'download stopped short'):
                update._apply_exe('https://example.invalid/Taskuary.exe')
        with mock.patch.object(update.sys, 'executable', str(self.exe)), \
             mock.patch.object(update, '_download', side_effect=FileNotFoundError(2, 'no such file')):
            with self.assertRaises(FileNotFoundError):
                update._apply_exe('https://example.invalid/Taskuary.exe')


if __name__ == '__main__':
    unittest.main()

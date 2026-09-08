"""The network share and the SFTP card (files.py).

Most of these tests are about ONE thing: a path the caller supplied stays under the root the owner
configured. That is the whole authority of a card that can write, it is pure, and it is where a
mistake would put a document somewhere nobody agreed to - so it gets tested exhaustively and
offline, and the protocol plumbing gets tested at its seam.
"""
import io
import posixpath
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from taskuary import files, scopes
from taskuary.reports import CONNECTION_KEYS, query_only
from taskuary.store import MemoryStore


def _share(**names):
    d = Path(tempfile.mkdtemp(prefix='taskuary_share_')).resolve()
    for n, body in names.items():
        p = d / n.replace('__', '.')
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding='utf-8')
    return d


def _cfg(share, **kw):
    return {'share': str(share), **kw}


class ThePathRuleTests(unittest.TestCase):
    """_rel is the gate every caller-supplied path goes through."""

    def test_an_absolute_path_cannot_pose_as_a_relative_one(self):
        for bad in ('/etc/passwd', '//fileserv/other', '\\\\fileserv\\other', 'C:/Windows', 'c:\\Windows'):
            with self.assertRaises(files.Refused, msg=bad): files._rel(bad)

    def test_dotdot_is_refused_in_every_position(self):
        for bad in ('..', '../x', 'a/../..', 'a/../../b', 'a/b/..'):
            with self.assertRaises(files.Refused, msg=bad): files._rel(bad)

    def test_a_backslash_path_is_accepted_because_both_kinds_of_caller_are_real(self):
        """The owner types what Explorer shows; the agent passes what the playbook said."""
        self.assertEqual(files._rel('Vendors\\2026\\acme.pdf'), 'Vendors/2026/acme.pdf')
        self.assertEqual(files._rel('/'), '')
        self.assertEqual(files._rel(None), '')

    def test_a_dot_in_a_name_is_not_a_climb(self):
        self.assertEqual(files._rel('a..b/c...d.pdf'), 'a..b/c...d.pdf')

    def test_under_local_returns_the_root_itself_for_an_empty_path(self):
        d = _share()
        self.assertEqual(files.under_local(str(d), ''), d)
        self.assertEqual(files.under_local(str(d) + '\\', ''), d)

    def test_under_local_refuses_a_sibling_that_merely_shares_a_prefix(self):
        """C:/Ops2 startswith C:/Ops and is a different folder - hence is_relative_to, not a string test."""
        base = Path(tempfile.mkdtemp(prefix='taskuary_pfx_')).resolve()
        (base / 'Ops').mkdir()
        (base / 'Ops2').mkdir()
        self.assertEqual(files.under_local(str(base / 'Ops'), 'x.txt'), base / 'Ops' / 'x.txt')
        with self.assertRaises(files.Refused): files.under_local(str(base / 'Ops'), '../Ops2/x.txt')

    def test_under_local_refuses_a_card_with_no_folder(self):
        with self.assertRaises(files.Refused): files.under_local('', 'x.txt')
        with self.assertRaises(files.Refused): files.under_local('   ', 'x.txt')

    def test_a_symlink_out_of_the_share_is_caught_because_resolve_comes_first(self):
        d, outside = _share(), _share(secret__txt='not yours')
        try: (d / 'link').symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError): self.skipTest('symlinks need privilege on this box')
        with self.assertRaises(files.Refused): files.under_local(str(d), 'link/secret.txt')

    def test_under_remote_joins_and_refuses_on_posix_rules_only(self):
        self.assertEqual(files.under_remote('/home/u', 'out/x.pdf'), '/home/u/out/x.pdf')
        self.assertEqual(files.under_remote('/home/u/', ''), '/home/u')
        self.assertEqual(files.under_remote('home/u', 'x'), '/home/u/x')
        with self.assertRaises(files.Refused): files.under_remote('/home/u', '../etc/passwd')
        with self.assertRaises(files.Refused): files.under_remote('/home/u', '/etc/passwd')

    def test_a_filename_never_carries_a_path(self):
        self.assertEqual(files._name('a/b/c.pdf'), 'c.pdf')
        self.assertEqual(files._name('..\\..\\evil.pdf'), 'evil.pdf')
        for bad in ('', '   ', '.', '..', '/'):
            with self.assertRaises(files.Refused, msg=bad): files._name(bad)


class WhereAWriteLandsTests(unittest.TestCase):
    def test_a_trailing_separator_means_a_folder_and_the_file_keeps_its_name(self):
        self.assertEqual(files._dest_rel('Vendors/2026/', 'acme.pdf'), 'Vendors/2026/acme.pdf')
        self.assertEqual(files._dest_rel('Vendors\\2026\\', 'acme.pdf'), 'Vendors/2026/acme.pdf')
        self.assertEqual(files._dest_rel('', 'acme.pdf'), 'acme.pdf')

    def test_anything_else_is_the_name_which_is_how_a_rename_happens(self):
        self.assertEqual(files._dest_rel('Vendors/2026/statement-q3.pdf', 'acme.pdf'),
                         'Vendors/2026/statement-q3.pdf')

    def test_a_folder_with_no_name_to_use_is_refused_rather_than_guessed(self):
        with self.assertRaises(files.Refused) as e: files._dest_rel('Vendors/', '')
        self.assertIn('filename', str(e.exception))


class NoSilentOverwriteTests(unittest.TestCase):
    def test_a_collision_is_numbered_and_the_headline_says_so(self):
        taken = {'a/x.pdf', 'a/x (2).pdf'}
        rel, note = files._free(lambda r: r in taken, 'a/x.pdf', False)
        self.assertEqual(rel, 'a/x (3).pdf')
        self.assertIn('x.pdf was already there', note)
        self.assertIn('x (3).pdf', note)

    def test_overwrite_true_means_it(self):
        rel, note = files._free(lambda r: True, 'a/x.pdf', True)
        self.assertEqual((rel, note), ('a/x.pdf', ''))

    def test_a_dotfile_is_numbered_without_a_stray_separator(self):
        rel, _ = files._free(lambda r: r == '.gitignore', '.gitignore', False)
        self.assertEqual(rel, '.gitignore (2)')

    def test_a_free_name_is_left_exactly_alone(self):
        self.assertEqual(files._free(lambda r: False, 'a/x.pdf', False), ('a/x.pdf', ''))


class ReadingTheShareTests(unittest.TestCase):
    """smb_read delegates, so these prove the DELEGATION and the root check - run_local_file's own
    parsers are covered by test_local_file.py and are not re-tested here."""

    def test_rows_come_back_through_the_local_file_parsers(self):
        d = _share(a__csv='name,qty\nwidget,4\nbolt,9\n')
        head, body = files.run_smb_read(_cfg(d, path='a.csv'))
        self.assertIn('2 rows', head)
        self.assertIn('widget', body)

    def test_a_folder_lists_what_is_in_it(self):
        d = _share(one__csv='a\n1\n', two__csv='a\n2\n')
        head, body = files.run_smb_read(_cfg(d, path=''))
        self.assertIn('2 files', head)
        self.assertIn('two.csv', body)

    def test_a_glob_picks_one_file_and_it_is_still_checked_against_the_root(self):
        d = _share(**{'sales-2026-08-01__csv': 'a\n1\n'})
        (d / 'sales-2026-09-01.csv').write_text('a\n2\n', encoding='utf-8')
        head, _ = files.run_smb_read(_cfg(d, path='sales-*.csv', pick='name'))
        self.assertIn('sales-2026-09-01.csv', head)

    def test_reading_out_of_the_share_is_refused(self):
        d = _share()
        with self.assertRaises(files.Refused): files.run_smb_read(_cfg(d, path='../secrets.csv'))

    def test_the_cards_password_does_not_travel_into_the_delegated_call(self):
        d = _share(a__csv='name\nx\n')
        with mock.patch('taskuary.reports.run_local_file') as rlf:
            rlf.return_value = ('1 rows', '{}')
            files.run_smb_read(_cfg(d, path='a.csv', username='svc', password='hunter2', tail=5))
        passed = rlf.call_args[0][0]
        self.assertEqual(passed['tail'], 5)
        for leaked in ('password', 'username', 'share', 'store'):
            self.assertNotIn(leaked, passed)


class ReachingTheShareTests(unittest.TestCase):
    """_mapped decides whether the card's credentials are used at all. Blank is the normal case."""

    def test_no_credentials_means_the_owners_own_session_and_no_shelling_out(self):
        d = _share()
        with mock.patch('taskuary.files.spawn.run') as run:
            self.assertEqual(files._mapped(_cfg(d)), str(d))
        run.assert_not_called()

    def test_credentials_on_a_local_path_are_ignored_rather_than_used_on_c_drive(self):
        d = _share()
        with mock.patch('taskuary.files.spawn.run') as run:
            files._mapped(_cfg(d, username='svc', password='pw'))
        run.assert_not_called()

    def test_a_unc_root_authenticates_the_share_not_the_folder_inside_it(self):
        files._mapped_roots.clear()
        root = '\\\\fileserv\\Ops\\Vendors\\2026'
        with mock.patch('taskuary.files.os.name', 'nt'), mock.patch('taskuary.files.spawn.run') as run:
            run.return_value = mock.Mock(returncode=0, stdout='', stderr='')
            files._mapped({'share': root, 'username': 'dom\\svc', 'password': 'pw'})
            argv = run.call_args[0][0]
            self.assertEqual(argv[:3], ['net', 'use', '\\\\fileserv\\Ops'])
            self.assertIn('/user:dom\\svc', argv)
            # ...and a second call does not ask again: the session is process-wide
            files._mapped({'share': root, 'username': 'dom\\svc', 'password': 'pw'})
            self.assertEqual(run.call_count, 1)
        files._mapped_roots.clear()

    def test_an_already_connected_share_is_not_an_error(self):
        """1219 is "already connected with another user" - the session exists, which is the goal."""
        files._mapped_roots.clear()
        with mock.patch('taskuary.files.os.name', 'nt'), mock.patch('taskuary.files.spawn.run') as run:
            run.return_value = mock.Mock(returncode=2, stdout='System error 1219 has occurred.', stderr='')
            files._mapped({'share': '\\\\fileserv\\Ops', 'username': 'svc', 'password': 'pw'})
        files._mapped_roots.clear()

    def test_a_real_failure_names_the_share_and_the_account(self):
        files._mapped_roots.clear()
        with mock.patch('taskuary.files.os.name', 'nt'), mock.patch('taskuary.files.spawn.run') as run:
            run.return_value = mock.Mock(returncode=2, stdout='System error 5 has occurred.', stderr='')
            with self.assertRaises(RuntimeError) as e:
                files._mapped({'share': '\\\\fileserv\\Ops', 'username': 'svc', 'password': 'pw'})
        self.assertIn('fileserv', str(e.exception))
        self.assertIn('svc', str(e.exception))
        files._mapped_roots.clear()

    def test_a_card_with_no_share_says_what_to_enter(self):
        with self.assertRaises(files.Refused) as e: files._mapped({})
        self.assertIn('fileserv', str(e.exception))      # the message carries an example


class WritingToTheShareTests(unittest.TestCase):
    def test_text_lands_where_the_path_says(self):
        d = _share()
        head, detail = files.run_smb_write(_cfg(d, path='Filed/note.txt', text='hello'))
        self.assertEqual((d / 'Filed' / 'note.txt').read_text(encoding='utf-8'), 'hello')
        self.assertIn('5 bytes to Filed/note.txt', head)
        self.assertIn('note.txt', detail)

    def test_a_second_write_does_not_replace_the_first(self):
        d = _share(x__txt='original')
        head, _ = files.run_smb_write(_cfg(d, path='x.txt', text='second'))
        self.assertEqual((d / 'x.txt').read_text(encoding='utf-8'), 'original')
        self.assertEqual((d / 'x (2).txt').read_text(encoding='utf-8'), 'second')
        self.assertIn('x (2).txt', head)

    def test_overwrite_replaces_when_the_call_says_to(self):
        d = _share(x__txt='original')
        files.run_smb_write(_cfg(d, path='x.txt', text='second', overwrite=True))
        self.assertEqual((d / 'x.txt').read_text(encoding='utf-8'), 'second')

    def test_a_write_outside_the_share_is_refused(self):
        d = _share()
        for bad in ('../escape.txt', '/etc/x.txt', 'C:/Windows/x.txt'):
            with self.assertRaises(files.Refused, msg=bad):
                files.run_smb_write(_cfg(d, path=bad, text='x'))

    def test_exactly_one_source_is_required(self):
        d = _share()
        with self.assertRaises(files.Refused) as e: files.run_smb_write(_cfg(d, path='x.txt'))
        self.assertIn('nothing to write', str(e.exception))
        with self.assertRaises(files.Refused) as e:
            files.run_smb_write(_cfg(d, path='x.txt', text='a', source_path='b'))
        self.assertIn('one source', str(e.exception))

    def test_a_source_outside_taskuarys_own_home_is_refused(self):
        """Otherwise {"source_path": "~/.ssh/id_rsa"} is an exfiltration tool with a card."""
        d = _share()
        outside = _share(id_rsa='PRIVATE KEY')
        with self.assertRaises(files.Refused) as e:
            files.run_smb_write(_cfg(d, path='stolen.txt', source_path=str(outside / 'id_rsa')))
        self.assertIn('outside', str(e.exception))

    def test_a_staged_file_is_a_legal_source_which_is_what_chains_the_two_cards(self):
        from taskuary import config
        stage = config.home() / files.STAGE / 'server'
        stage.mkdir(parents=True, exist_ok=True)
        (stage / 'statement.pdf').write_bytes(b'%PDF-1.4 pretend')
        d = _share()
        head, _ = files.run_smb_write(_cfg(d, path='Filed/', source_path=str(stage / 'statement.pdf')))
        self.assertTrue((d / 'Filed' / 'statement.pdf').is_file())
        self.assertIn('Filed/statement.pdf', head)

    def test_move_renames_inside_the_share_and_nowhere_else(self):
        d = _share(x__txt='body')
        head, _ = files.run_smb_move(_cfg(d, path='x.txt', to='Filed/renamed.txt'))
        self.assertFalse((d / 'x.txt').exists())
        self.assertEqual((d / 'Filed' / 'renamed.txt').read_text(encoding='utf-8'), 'body')
        self.assertIn('Filed/renamed.txt', head)
        (d / 'y.txt').write_text('y', encoding='utf-8')
        with self.assertRaises(files.Refused): files.run_smb_move(_cfg(d, path='y.txt', to='../out.txt'))
        self.assertTrue((d / 'y.txt').exists())      # refused means nothing moved

    def test_moving_something_that_is_not_there_says_so(self):
        d = _share()
        with self.assertRaises(files.Refused) as e: files.run_smb_move(_cfg(d, path='nope.txt', to='x.txt'))
        self.assertIn('does not exist', str(e.exception))


class WritingAnAttachmentTests(unittest.TestCase):
    """The owner, 2026-09-08: "yes attachement id included" - so filing the PDF a mail carried is
    ONE call, and the Path column is verified the way server._attachment_path verifies it."""

    def _store_with_attachment(self, path, name='invoice.pdf'):
        st = MemoryStore()
        mid = st.add_message({'ExternalId': 'x:1', 'Channel': 'report', 'Subject': 's', 'Body': 'b'}) \
            if hasattr(st, 'add_message') else 1
        aid = st.add_attachment({'MessageId': mid, 'ExternalId': f'x:{name}', 'Name': name,
                                 'ContentType': 'application/pdf', 'Size': 4, 'Path': str(path) if path else None})
        return st, aid

    def _attachment_file(self, name='invoice.pdf', body=b'%PDF'):
        from taskuary import config
        d = config.home() / 'attachments' / '77'
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        p.write_bytes(body)
        return p

    def test_the_mailed_file_is_filed_under_its_own_name(self):
        p = self._attachment_file()
        st, aid = self._store_with_attachment(p)
        d = _share()
        head, _ = files.run_smb_write(_cfg(d, path='Vendors/2026/', attachment=aid, store=st))
        self.assertEqual((d / 'Vendors' / '2026' / 'invoice.pdf').read_bytes(), b'%PDF')
        self.assertIn('Vendors/2026/invoice.pdf', head)

    def test_naming_the_path_renames_it_on_the_way_in(self):
        p = self._attachment_file()
        st, aid = self._store_with_attachment(p)
        d = _share()
        files.run_smb_write(_cfg(d, path='Vendors/acme-2026-09.pdf', attachment=aid, store=st))
        self.assertTrue((d / 'Vendors' / 'acme-2026-09.pdf').is_file())

    def test_an_attachment_recorded_without_bytes_says_which_one(self):
        st, aid = self._store_with_attachment(None, name='linked.pdf')
        d = _share()
        with self.assertRaises(files.Refused) as e:
            files.run_smb_write(_cfg(d, path='x/', attachment=aid, store=st))
        self.assertIn('linked.pdf', str(e.exception))
        self.assertIn('no file on disk', str(e.exception))

    def test_a_path_column_pointing_out_of_the_attachments_tree_is_refused(self):
        outside = _share(loot__txt='secrets')
        st, aid = self._store_with_attachment(outside / 'loot.txt')
        d = _share()
        with self.assertRaises(files.Refused): files.run_smb_write(_cfg(d, path='x/', attachment=aid, store=st))

    def test_an_unknown_attachment_id_is_refused(self):
        st = MemoryStore()
        d = _share()
        with self.assertRaises(files.Refused):
            files.run_smb_write(_cfg(d, path='x/', attachment=99999, store=st))
        with self.assertRaises(files.Refused):
            files.run_smb_write(_cfg(d, path='x/', attachment='not-a-number', store=st))


class _FakeAttr:
    def __init__(self, filename, size, mtime, mode=0o100644):
        self.filename, self.st_size, self.st_mtime, self.st_mode = filename, size, mtime, mode


class _FakeSftp:
    """The SFTPClient surface files.py actually uses. Fake at this seam so list/get/put/move are
    tested for real logic without a server; the host-key and path rules are tested on their own."""

    def __init__(self, listing=(), existing=()):
        self.listing, self.existing = list(listing), set(existing)
        self.put_calls, self.renames, self.got = [], [], []

    def listdir_attr(self, d): return list(self.listing)
    def normalize(self, _): return '/home/u'

    def stat(self, path):
        if path not in self.existing: raise IOError(f'no such file {path}')
        return _FakeAttr(posixpath.basename(path), 12, 0)

    def put(self, local, remote): self.put_calls.append((str(local), remote))
    def putfo(self, fo, remote): self.put_calls.append((fo.read(), remote))
    def get(self, remote, local):
        self.got.append((remote, str(local)))
        Path(local).write_bytes(b'fetched')

    def rename(self, a, b): self.renames.append((a, b))
    def close(self): pass


class SftpToolTests(unittest.TestCase):
    def _patched(self, fake, base='/home/u'):
        from contextlib import contextmanager

        @contextmanager
        def _c(cfg):
            yield fake, base
        return mock.patch.object(files, '_client', _c)

    def test_a_listing_is_newest_first_and_skips_directories(self):
        fake = _FakeSftp(listing=[_FakeAttr('old.csv', 10, 1_600_000_000),
                                  _FakeAttr('new.csv', 20, 1_700_000_000),
                                  _FakeAttr('subdir', 0, 1_800_000_000, mode=0o040755)])
        with self._patched(fake):
            head, body = files.run_sftp_list({'host': 'h', 'path': 'outgoing/'})
        self.assertIn('2 files', head)
        self.assertLess(body.index('new.csv'), body.index('old.csv'))
        self.assertNotIn('subdir', body)

    def test_get_lands_in_staging_and_answers_with_the_path(self):
        fake = _FakeSftp(existing={'/home/u/out/statement.pdf'})
        with self._patched(fake):
            head, local = files.run_sftp_get({'host': 'h', 'path': 'out/statement.pdf'})
        self.assertIn('12 bytes', head)
        self.assertTrue(Path(local).is_file())
        self.assertEqual(Path(local).name, 'statement.pdf')
        self.assertIn(files.STAGE, local)
        # ...and that path is a legal source for the share, which is the whole chain
        d = _share()
        files.run_smb_write(_cfg(d, path='Filed/', source_path=local))
        self.assertTrue((d / 'Filed' / 'statement.pdf').is_file())

    def test_get_refuses_a_remote_path_that_climbs(self):
        with self._patched(_FakeSftp()):
            with self.assertRaises(files.Refused):
                files.run_sftp_get({'host': 'h', 'path': '../../etc/passwd'})

    def test_get_says_so_when_the_file_is_not_there(self):
        with self._patched(_FakeSftp()):
            with self.assertRaises(files.Refused) as e:
                files.run_sftp_get({'host': 'h', 'path': 'out/missing.pdf'})
        self.assertIn('does not exist', str(e.exception))

    def test_put_uploads_under_the_base_and_numbers_a_collision(self):
        fake = _FakeSftp(existing={'/home/u/in/note.txt'})
        with self._patched(fake):
            head, target = files.run_sftp_put({'host': 'h', 'path': 'in/note.txt', 'text': 'body'})
        self.assertEqual(target, '/home/u/in/note (2).txt')
        self.assertIn('note (2).txt', head)
        self.assertEqual(fake.put_calls[0][0], b'body')

    def test_put_refuses_a_source_outside_taskuarys_home(self):
        outside = _share(id_rsa='KEY')
        with self._patched(_FakeSftp()):
            with self.assertRaises(files.Refused):
                files.run_sftp_put({'host': 'h', 'path': 'in/', 'source_path': str(outside / 'id_rsa')})

    def test_move_marks_the_remote_file_done(self):
        fake = _FakeSftp(existing={'/home/u/out/x.pdf'})
        with self._patched(fake):
            head, _ = files.run_sftp_move({'host': 'h', 'path': 'out/x.pdf', 'to': 'processed/x.pdf'})
        self.assertEqual(fake.renames, [('/home/u/out/x.pdf', '/home/u/processed/x.pdf')])
        self.assertIn('processed/x.pdf', head)

    def test_move_needs_both_ends(self):
        with self._patched(_FakeSftp(existing={'/home/u/x'})):
            with self.assertRaises(files.Refused): files.run_sftp_move({'host': 'h', 'path': 'x'})
            with self.assertRaises(files.Refused): files.run_sftp_move({'host': 'h', 'to': 'y'})

    def test_a_card_with_no_host_or_user_is_refused_before_any_socket(self):
        with self.assertRaises(files.Refused): next(files._client({}).__enter__() for _ in [0])


class _FakeKey:
    def __init__(self, raw=b'ssh-ed25519 AAAA'): self.raw = raw
    def asbytes(self): return self.raw


class HostKeyTests(unittest.TestCase):
    def test_the_fingerprint_is_printed_the_way_openssh_prints_it(self):
        fp = files.fingerprint(_FakeKey())
        self.assertTrue(fp.startswith('SHA256:'))
        self.assertNotIn('=', fp)

    def test_the_card_may_hold_either_form_the_owner_actually_has(self):
        k = _FakeKey()
        sha = files.fingerprint(k)
        self.assertTrue(files.key_matches(sha, k))
        self.assertTrue(files.key_matches(sha.split(':', 1)[1], k))
        self.assertTrue(files.key_matches(sha.lower(), k))
        import hashlib
        md5 = hashlib.md5(k.asbytes()).hexdigest()
        self.assertTrue(files.key_matches(md5, k))
        self.assertTrue(files.key_matches(':'.join(md5[i:i + 2] for i in range(0, 32, 2)), k))
        self.assertTrue(files.key_matches('MD5:' + md5, k))

    def test_a_different_key_never_matches_and_neither_does_nothing(self):
        k = _FakeKey()
        self.assertFalse(files.key_matches(files.fingerprint(_FakeKey(b'other')), k))
        self.assertFalse(files.key_matches('', k))
        self.assertFalse(files.key_matches(None, k))

    def _policy(self, cfg):
        """The policy object _client builds, without connecting anything."""
        got = {}
        real = files._paramiko()

        class Probe(real.SSHClient):
            def set_missing_host_key_policy(self, p): got['p'] = p
            def connect(self, **kw): raise _Stop()
            def close(self): pass

        class _Stop(Exception): pass
        with mock.patch.object(real, 'SSHClient', Probe):
            try:
                with files._client(cfg): pass
            except _Stop:
                pass
        return got['p']

    def test_a_card_with_no_expected_key_cannot_connect_and_is_told_what_to_paste(self):
        p = self._policy({'host': 'h', 'username': 'u'})
        with self.assertRaises(files.Refused) as e:
            p.missing_host_key(None, 'h', _FakeKey())
        self.assertIn('SHA256:', str(e.exception))
        self.assertIn('host key field', str(e.exception))

    def test_a_mismatch_is_refused_and_names_both_fingerprints(self):
        want = files.fingerprint(_FakeKey(b'the real server'))
        p = self._policy({'host': 'h', 'username': 'u', 'hostkey': want})
        with self.assertRaises(files.Refused) as e:
            p.missing_host_key(None, 'h', _FakeKey(b'somebody else'))
        msg = str(e.exception)
        self.assertIn(want, msg)
        self.assertIn(files.fingerprint(_FakeKey(b'somebody else')), msg)

    def test_the_expected_key_is_accepted_silently(self):
        k = _FakeKey()
        p = self._policy({'host': 'h', 'username': 'u', 'hostkey': files.fingerprint(k)})
        self.assertIsNone(p.missing_host_key(None, 'h', k))


class AuthorityTests(unittest.TestCase):
    def test_a_fetch_is_a_read_and_the_four_that_change_the_far_side_are_writes(self):
        for t in ('smb_read', 'sftp_list', 'sftp_get'):
            self.assertEqual(scopes.needs(t), 'read', t)
        for t in ('smb_write', 'smb_move', 'sftp_put', 'sftp_move'):
            self.assertEqual(scopes.needs(t), 'write', t)

    def test_both_cards_ship_read_only_so_the_first_save_is_a_proposal(self):
        for t in ('smb_file', 'sftp'):
            self.assertEqual(scopes.scope_of({'Type': t}), 'read', t)
            self.assertTrue(scopes.allows({'Type': t}, 'smb_read' if t == 'smb_file' else 'sftp_list'))
            self.assertFalse(scopes.allows({'Type': t}, 'smb_write' if t == 'smb_file' else 'sftp_put'))

    def test_raising_the_card_is_what_lets_it_write(self):
        self.assertTrue(scopes.allows({'Type': 'smb_file', 'Scope': 'write'}, 'smb_write'))
        self.assertTrue(scopes.allows({'Type': 'sftp', 'Scope': 'write'}, 'sftp_put'))

    def test_a_tool_call_cannot_bring_its_own_root(self):
        """resolve_cfg lets the body win, so WHERE THE FILES ARE has to be un-overridable - the
        same lesson base_url taught (audit 2026-09-02)."""
        for k in ('share', 'root', 'port', 'hostkey', 'private_key', 'host', 'username', 'password'):
            self.assertIn(k, CONNECTION_KEYS, k)
        body = query_only({'type': 'smb_write', 'path': 'x.txt', 'text': 'a',
                           'share': '\\\\attacker\\open', 'root': '/', 'hostkey': 'whatever'})
        self.assertEqual(body, {'type': 'smb_write', 'path': 'x.txt', 'text': 'a'})


class WiringTests(unittest.TestCase):
    def test_every_tool_is_registered_and_points_at_its_card(self):
        from taskuary.reports import REGISTRY, CARD_OF, CONNECTION_OF, card_of
        for t in ('smb_read', 'smb_write', 'smb_move'):
            self.assertIn(t, REGISTRY, t)
            self.assertEqual(card_of(t), 'smb_file')
            self.assertIn(t, CONNECTION_OF, t)
        for t in ('sftp_list', 'sftp_get', 'sftp_put', 'sftp_move'):
            self.assertIn(t, REGISTRY, t)
            self.assertEqual(card_of(t), 'sftp')
            self.assertIn(t, CONNECTION_OF, t)
        self.assertNotIn('smb_file', CARD_OF)      # the card is not a tool type

    def test_the_share_is_no_longer_advertised_as_planned(self):
        from taskuary.reports import PLANNED
        self.assertNotIn('smb_file', PLANNED)
        self.assertNotIn('sftp', PLANNED)

    def test_both_cards_are_seeded_as_a_report_source_and_an_agent_tool(self):
        from taskuary import store as store_mod
        for t in ('smb_file', 'sftp'):
            self.assertEqual(store_mod.DEFAULT_ROLES[t], 'report,tool')
        st = MemoryStore()
        for t in ('smb_file', 'sftp'):
            c = st.get_connector_by_type(t)
            self.assertTrue(c, f'{t} card was not seeded')
            self.assertEqual(store_mod.roles_of(c), {'report', 'tool'})
            self.assertFalse(c.get('Active'), 'a seeded card must start off')

    def test_the_connection_helper_carries_the_store_because_an_attachment_is_a_row(self):
        from taskuary.reports import smb_connection, sftp_connection
        st = MemoryStore()
        self.assertIs(smb_connection(st)['store'], st)
        self.assertIs(sftp_connection(st)['store'], st)

    def test_paramiko_is_bundled_so_the_exe_arrives_able_to_use_the_card(self):
        from taskuary import deps
        self.assertIn('paramiko', deps.BUNDLE)
        self.assertIn('paramiko', deps.OPTIONAL)
        self.assertEqual(deps.pip_name('paramiko'), 'paramiko')

    def test_a_composed_write_must_say_where(self):
        from taskuary.compose import REQUIRED
        self.assertEqual(REQUIRED['smb_write'], ('path',))
        self.assertEqual(REQUIRED['sftp_move'], ('path', 'to'))
        self.assertNotIn('smb_read', REQUIRED)     # the card's root IS a folder worth reading


if __name__ == '__main__':
    unittest.main()

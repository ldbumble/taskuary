"""The CLIs that neither take an id nor stream one: their conversation is a file on disk.

Layouts here are SYNTHETIC, written from each vendor's documentation - gemini and cursor are not
installed on the machine this was built on. The finding logic is what these tests pin; if a vendor
spells its directory differently the fix is one entry in sessionfiles.SOURCES.
"""
import hashlib
import json
import time
from unittest import mock

import pytest

from taskuary import sessionfiles


def gemini_home(home, cwd, name='session-2026-09-15T10-11-1991bea1.json', body=None):
    d = home / '.gemini' / 'tmp' / hashlib.sha256(str(cwd).encode()).hexdigest() / 'chats'
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(body if body is not None else
                                     {'sessionId': '1991bea1-0000-4000-8000-000000000001'}), encoding='utf-8')
    return d / name


def test_a_gemini_session_under_this_pane_s_project_hash_gives_its_id(tmp_path):
    home, cwd = tmp_path / 'home', tmp_path / 'repo'; cwd.mkdir()
    f = gemini_home(home, cwd)
    with mock.patch.object(sessionfiles, '_home', return_value=home):
        assert sessionfiles.find('gemini', str(cwd), f.stat().st_mtime - 5) == '1991bea1-0000-4000-8000-000000000001'


def test_a_session_older_than_the_pane_is_not_claimed_as_its_own(tmp_path):
    home, cwd = tmp_path / 'home', tmp_path / 'repo'; cwd.mkdir()
    f = gemini_home(home, cwd)
    with mock.patch.object(sessionfiles, '_home', return_value=home):
        assert sessionfiles.find('gemini', str(cwd), f.stat().st_mtime + 5) == ''


def test_a_session_file_that_names_no_uuid_falls_back_to_the_id_in_its_name(tmp_path):
    home, cwd = tmp_path / 'home', tmp_path / 'repo'; cwd.mkdir()
    f = gemini_home(home, cwd, body={'messages': []})
    with mock.patch.object(sessionfiles, '_home', return_value=home):
        assert sessionfiles.find('gemini', str(cwd), f.stat().st_mtime - 5) == '1991bea1'


def test_a_hash_we_cannot_reproduce_still_finds_the_newest_session_in_this_home(tmp_path):
    """The project hash is sha256 of the project ROOT, which may be a git root rather than the cwd.
    Guessing wrong must degrade to 'the newest one, just now' - not to nothing at all."""
    home, cwd = tmp_path / 'home', tmp_path / 'repo'; cwd.mkdir()
    f = gemini_home(home, tmp_path / 'somewhere-else')
    with mock.patch.object(sessionfiles, '_home', return_value=home):
        assert sessionfiles.find('gemini', str(cwd), f.stat().st_mtime - 5) == '1991bea1-0000-4000-8000-000000000001'


def test_a_cursor_chat_is_named_by_the_directory_it_lives_in(tmp_path):
    home, cwd = tmp_path / 'home', tmp_path / 'repo'; cwd.mkdir()
    d = home / '.cursor' / 'chats' / 'workspace-a' / '7c9e6679-7425-40de-944b-e07fc1f90ae7'
    d.mkdir(parents=True)
    (d / 'store.db').write_bytes(b'SQLite format 3\x00')
    with mock.patch.object(sessionfiles, '_home', return_value=home):
        found = sessionfiles.find('cursor-agent', str(cwd), (d / 'store.db').stat().st_mtime - 5)
    assert found == '7c9e6679-7425-40de-944b-e07fc1f90ae7'


def test_a_cli_that_files_nothing_we_know_about_is_simply_not_watched(tmp_path):
    assert sessionfiles.find('claude', str(tmp_path), 0) == ''     # claude is TOLD its id instead
    assert not sessionfiles.watches('codex')                       # codex has its own rollout tail
    assert sessionfiles.watches('gemini') and sessionfiles.watches('cursor-agent')


def test_the_newest_session_wins_when_a_pane_has_written_more_than_one(tmp_path):
    home, cwd = tmp_path / 'home', tmp_path / 'repo'; cwd.mkdir()
    first = gemini_home(home, cwd, name='session-2026-09-15T10-00-aaaaaaaa.json',
                        body={'sessionId': 'aaaaaaaa-0000-4000-8000-000000000001'})
    time.sleep(0.02)
    gemini_home(home, cwd, name='session-2026-09-15T10-30-bbbbbbbb.json',
                body={'sessionId': 'bbbbbbbb-0000-4000-8000-000000000002'})
    with mock.patch.object(sessionfiles, '_home', return_value=home):
        assert sessionfiles.find('gemini', str(cwd), first.stat().st_mtime - 5).startswith('bbbbbbbb')

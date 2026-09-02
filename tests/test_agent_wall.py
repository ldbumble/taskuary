"""The wall: what agents tell each other.

peers() and dirty() read facts off git and the run trace - who holds which file, who is busy.
True, and about as expressive as a security camera: they cannot say "the migration is half
applied, don't run the tests yet" or "this is green, safe to build on". Only the agent doing
the work knows that, so it writes it down, and the next agent reads it before it starts.

An agent in a terminal has a shell and no API token, so the door is `taskuary --note` /
`taskuary --board`, with the session telling the child which agent, task and checkout it is.
"""
import json
import os
import unittest
from datetime import datetime
from unittest import mock

from taskuary import blackboard as bb, terminal
from taskuary.store import MemoryStore

CWD = os.path.normcase(os.path.normpath('C:/work/census' if os.name == 'nt' else '/work/census'))


class PostingTests(unittest.TestCase):
    def test_a_note_lands_on_the_checkout_it_was_written_in(self):
        s = MemoryStore()
        n = bb.post(s, 'store.py is mine for the next 20 minutes', 'working', 'codex', CWD, 7)
        self.assertEqual((n['Kind'], n['Agent'], n['TaskId']), ('working', 'codex', 7))
        self.assertEqual(len(bb.wall(s, CWD)), 1)
        self.assertEqual(bb.wall(s, 'C:/work/other'), [])       # another repo is none of its business

    def test_a_note_with_no_words_is_refused(self):
        s = MemoryStore()
        for empty in ('', '   ', None):
            with self.assertRaises(ValueError): bb.post(s, empty)

    def test_only_the_kinds_the_agents_are_taught_are_accepted(self):
        s = MemoryStore()
        for k in bb.KINDS: bb.post(s, 'x', k, 'coder', CWD)
        with self.assertRaises(ValueError): bb.post(s, 'x', 'shipit', 'coder', CWD)

    def test_a_speech_is_trimmed_to_a_line(self):
        s = MemoryStore()
        n = bb.post(s, 'word ' * 800, 'note', 'coder', CWD)
        self.assertLessEqual(len(n['Body']), 1200)
        self.assertNotIn('\n', n['Body'])

    def test_everything_but_the_words_is_optional(self):
        """An agent that knows only what it wants to say still gets to say it."""
        s = MemoryStore()
        n = bb.post(s, 'the mssql tests need pyodbc')
        self.assertEqual((n['Agent'], n['Kind'], n['TaskId']), ('agent', 'note', None))


class ReadingTests(unittest.TestCase):
    def test_the_prompt_gets_a_pointer_and_the_newest_note_not_the_whole_wall(self):
        """A seed is typed into a TUI on one line; the transcript does not belong there."""
        s = MemoryStore()
        for i, (k, body) in enumerate((('working', 'taking auth.py'), ('blocked', 'need the staging key'),
                                       ('ready', 'auth done, suite green'))):
            bb.post(s, body, k, f'agent{i}', CWD)
        text = bb.wall_text(s, CWD)
        self.assertIn('auth done, suite green', text)       # the newest, in full
        self.assertNotIn('taking auth.py', text)            # ...and not the whole history
        self.assertIn('taskuary --board', text)             # with the way to read the rest
        self.assertIn('3 note(s)', text)
        self.assertLessEqual(len(text), bb.SEED_BUDGET)     # it shares one line with the task itself

    def test_a_loud_wall_cannot_eat_the_prompt(self):
        """The wall is the one part of a seed that grows every time an agent says something."""
        s = MemoryStore()
        for i in range(40): bb.post(s, f'note {i} ' + 'x' * 400, 'note', f'agent{i}', CWD)
        self.assertLessEqual(len(bb.wall_text(s, CWD)), bb.SEED_BUDGET)

    def test_an_empty_wall_says_nothing_at_all(self):
        """A prompt paragraph that says "no notes" is tokens spent to say nothing."""
        self.assertEqual(bb.wall_text(MemoryStore(), CWD), '')

    def test_who_has_read_it_is_recorded_once_per_reader(self):
        s = MemoryStore()
        n = bb.post(s, 'watch out for the flaky test', 'note', 'coder', CWD)
        s.mark_note_read(n['NoteId'], 'codex')
        s.mark_note_read(n['NoteId'], 'codex')
        s.mark_note_read(n['NoteId'], 'gemini')
        self.assertEqual(s.get_note(n['NoteId'])['ReadBy'], 'codex,gemini')

    def test_the_etiquette_names_the_command_that_writes_and_the_one_before_a_push(self):
        self.assertIn('taskuary --note', bb.HOW_TO_POST)
        self.assertIn('--kind ready', bb.HOW_TO_POST)


class TheSeedTests(unittest.TestCase):
    def test_a_session_tells_its_cli_which_agent_task_and_checkout_it_is(self):
        env = terminal.session_env('codex', 7, CWD)
        self.assertEqual((env['TASKUARY_AGENT'], env['TASKUARY_TASK'], env['TASKUARY_CWD']), ('codex', '7', CWD))

    def test_a_shell_with_no_task_carries_nothing_but_its_own_authority(self):
        """No agent, no task, no checkout - so none of those are announced. The agent token IS
        there, and deliberately: everything Taskuary spawns is a process, and a process gets
        less authority than the person at the browser does (guard.py). A plain shell inside the
        app is not the owner clicking a button, and the send routes tell the two apart by
        exactly this header."""
        from taskuary import config, guard
        env = terminal.session_env('', None, '')
        self.assertEqual(set(env), {guard.AGENT_ENV})
        self.assertEqual(env[guard.AGENT_ENV], config.load()['server']['agent_token'])

    def test_the_wall_rides_into_the_next_agents_prompt(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'ship the thing', 'Kind': 'coding'}, 'o')
        bb.post(s, 'the migration is half applied - do not run the tests yet', 'blocked', 'codex', CWD)
        seed = terminal.seed_text(s, tid, repo=None, cwd=CWD)
        self.assertIn('half applied', seed)
        self.assertIn('taskuary --board', seed)

    def test_a_general_task_with_no_checkout_gets_no_wall(self):
        """The wall is per checkout; a question about a meeting has none."""
        s = MemoryStore()
        tid = s.create_task({'Title': 'prep the board meeting', 'Kind': 'general'}, 'o')
        bb.post(s, 'do not touch store.py', 'working', 'codex', CWD)
        seed = terminal.seed_text(s, tid, repo=None, cwd='')
        self.assertNotIn('do not touch store.py', seed)


class TheChatIsOnItTooTests(unittest.TestCase):
    """The chat researches, reads systems, and finds the thing the next session would spend an
    hour rediscovering. Leaving it out meant the only agents talking to each other were the ones
    standing in a checkout."""
    def test_a_note_with_no_checkout_is_everybodys(self):
        s = MemoryStore()
        bb.post(s, 'the Intacct credentials are being rotated today', 'blocked', 'you', '')
        bb.post(s, 'mine alone', 'note', 'codex', CWD)
        self.assertEqual([n['Body'] for n in bb.house_wall(s)], ['the Intacct credentials are being rotated today'])
        self.assertEqual(len(bb.wall(s, CWD)), 2)                  # a checkout sees its own AND the house
        self.assertEqual(len(bb.wall(s, os.path.normcase('/work/other'))), 1)   # ...but never another repo's

    def test_the_chat_reads_the_house_lane_and_not_a_checkouts(self):
        s = MemoryStore()
        bb.post(s, 'everybody should know this', 'note', 'you', '')
        bb.post(s, 'only the people in this repo', 'note', 'codex', CWD)
        text = bb.chat_text(s)
        self.assertIn('everybody should know this', text)
        self.assertNotIn('only the people in this repo', text)

    def test_it_rides_into_the_chats_own_prompt(self):
        from taskuary import general
        s = MemoryStore()
        tid = s.create_task({'Title': 'research', 'Kind': 'general', 'Summary': 'x'}, 'o')
        bb.post(s, 'the Intacct credentials are being rotated today', 'blocked', 'you', '')
        _system, user = general._prompt(s, tid)
        self.assertIn('rotated today', user)

    def test_only_a_cli_backed_chat_is_told_how_to_post(self):
        """An API provider has no shell; telling it about a command it cannot run is a lie."""
        from taskuary import general
        self.assertIn('taskuary --note', general.POST_LINE)

    def test_an_empty_house_lane_says_nothing(self):
        self.assertEqual(bb.chat_text(MemoryStore()), '')


class TheWallCompostsTests(unittest.TestCase):
    """A wall that only grows is a wall nobody reads to the bottom of - and "taking store.py for
    twenty minutes" three days ago is worse than nothing, because it reads as now. Each day is
    folded into one note per checkout, and the originals are marked rather than deleted."""
    def _aged(self, s, day, kind, body, cwd=CWD, agent='codex'):
        n = bb.post(s, body, kind, agent, cwd)
        s._exec('UPDATE boardnote SET CreatedAt=? WHERE NoteId=?', (f'{day} 10:00:00', n['NoteId']))
        return n

    def test_a_day_becomes_one_note_and_the_transient_ones_stop_showing(self):
        s = MemoryStore()
        self._aged(s, '2026-08-29', 'working', 'taking store.py for 20 minutes')
        self._aged(s, '2026-08-29', 'note', 'the mssql tests need pyodbc')
        self._aged(s, '2026-08-29', 'ready', 'auth pushed, suite green')
        self.assertEqual(bb.roll_up(s, '2026-08-30', llm=None), 1)
        live = bb.wall(s, CWD)
        self.assertEqual([n['Kind'] for n in live], [bb.SUMMARY])
        self.assertIn('pyodbc', live[0]['Body'])                      # what survives
        self.assertNotIn('20 minutes', live[0]['Body'])               # what does not

    def test_nothing_is_deleted_and_the_board_can_still_show_it_all(self):
        s = MemoryStore()
        self._aged(s, '2026-08-29', 'note', 'the mssql tests need pyodbc')
        bb.roll_up(s, '2026-08-30', llm=None)
        self.assertEqual(len(s.notes(CWD, rolled=True)), 2)           # the original AND the summary
        self.assertEqual(len(s.notes(CWD)), 1)

    def test_today_is_left_alone(self):
        s = MemoryStore()
        bb.post(s, 'happening now', 'working', 'codex', CWD)
        self.assertEqual(bb.roll_up(s, datetime.now().strftime('%Y-%m-%d'), llm=None), 0)
        self.assertEqual(len(bb.wall(s, CWD)), 1)

    def test_each_checkout_gets_its_own_summary(self):
        s = MemoryStore()
        self._aged(s, '2026-08-29', 'note', 'this repo', CWD)
        self._aged(s, '2026-08-29', 'note', 'the other repo', os.path.normcase('/work/other'))
        self._aged(s, '2026-08-29', 'note', 'everybody', '')
        self.assertEqual(bb.roll_up(s, '2026-08-30', llm=None), 3)

    def test_the_ai_writes_it_when_there_is_one_and_may_say_there_is_nothing(self):
        s = MemoryStore()
        self._aged(s, '2026-08-29', 'working', 'holding a file')
        self.assertEqual(bb.roll_up(s, '2026-08-30', llm=lambda *a, **k: 'NOTHING'), 0)
        self.assertEqual(bb.wall(s, CWD), [])                          # composted, nothing carried
        self._aged(s, '2026-08-28', 'note', 'a real finding')
        self.assertEqual(bb.roll_up(s, '2026-08-30', llm=lambda *a, **k: 'the finding, in short'), 1)
        self.assertIn('the finding, in short', bb.wall(s, CWD)[0]['Body'])

    def test_a_model_that_fails_still_leaves_the_facts_behind(self):
        s = MemoryStore()
        self._aged(s, '2026-08-29', 'note', 'the mssql tests need pyodbc')
        def boom(*a, **k): raise RuntimeError('no brain today')
        self.assertEqual(bb.roll_up(s, '2026-08-30', llm=boom), 1)
        self.assertIn('pyodbc', bb.wall(s, CWD)[0]['Body'])

    def test_it_runs_once_a_day_however_often_it_is_asked(self):
        s = MemoryStore()
        self._aged(s, '2026-08-29', 'note', 'one')
        self.assertEqual(bb.roll_daily(s, llm=None), 1)
        self._aged(s, '2026-08-29', 'note', 'two')
        self.assertEqual(bb.roll_daily(s, llm=None), 0)                # already composted today
        self.assertEqual(len(bb.wall(s, CWD)), 2)                      # ...and the new one is untouched

    def test_agents_are_not_offered_the_summary_kind(self):
        s = MemoryStore()
        with self.assertRaises(ValueError): bb.post(s, 'x', 'shipit', 'codex', CWD)
        self.assertNotIn(bb.SUMMARY, bb.KINDS)                          # the roll-up writes it, nobody else
        self.assertTrue(bb.post(s, 'x', bb.SUMMARY, 'the wall', CWD))   # ...and it is accepted from there


class TheRulesTests(unittest.TestCase):
    def test_coder_md_tells_the_agent_to_read_it_first_and_post_before_pushing(self):
        from pathlib import Path
        md = (Path(__file__).resolve().parent.parent / 'taskuary' / 'templates' / 'coder.md').read_text(encoding='utf-8')
        self.assertIn('taskuary --board', md)
        self.assertIn('--kind ready', md)
        self.assertIn('Read it first', md)


class TheApiTests(unittest.TestCase):
    def test_the_board_can_read_and_write_the_same_wall(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        c = TestClient(server.app)
        posted = c.post('/api/board/notes', json={'body': 'from the board', 'kind': 'ready'})
        self.assertEqual(posted.status_code, 200)
        got = c.get('/api/board/notes').json()
        self.assertIn('from the board', [n['Body'] for n in got['data']])
        self.assertEqual(got['kinds'], list(bb.KINDS))
        self.assertEqual(c.post('/api/board/notes', json={'body': 'x', 'kind': 'nope'}).status_code, 422)


if __name__ == '__main__':
    unittest.main()

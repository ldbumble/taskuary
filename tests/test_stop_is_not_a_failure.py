"""A general agent the owner stopped is stopped - not failed, and not started again (the overnight run, 2026-11-03).

Stop and save on a general agent mid-turn closed its session, its Claude Code exited, and the turn read as a CLI that died part-way:
the pane said "Claude: the agent stopped in the middle of its turn ... (the CLI exited (1))" and "Couldn't start yet ... - trying
again at 00:38" - the start queue was about to run the agent the owner had just stopped."""
from unittest import mock

from taskuary import blackboard as bb, general, ingest, workerstate as ws
from taskuary.clipool import MID_TURN
from taskuary.store import MemoryStore


def task(s): return s.create_task({'Title': 'Write vendor notes', 'Summary': 'Write the vendor notes.', 'Kind': 'general', 'Status': 'in_progress'}, 'router')


def test_a_start_whose_turn_the_owner_stopped_is_neither_failed_nor_retried():
    s = MemoryStore(); tid = task(s)
    ses = mock.Mock(); ses.send_prompt.side_effect = general.Stopped(MID_TURN)
    with mock.patch.object(general, 'start_session', return_value=ses), mock.patch.object(bb, 'record_failure') as failed:
        assert ingest._start_general(s, tid) is True
    failed.assert_not_called()
    assert not s.get_dispatch(tid)


def test_a_turn_cut_by_close_is_recorded_stopped():
    s = MemoryStore(); tid = task(s)
    with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')):
        ses = general.GeneralSession(s, tid)
    def cut(*a, **k):
        ses.closing = True                                   # Stop and save closed the session under the turn
        raise RuntimeError(f'{MID_TURN} (the CLI exited (1))')
    with mock.patch.object(general.llm_mod, 'build_llm', return_value=cut), mock.patch.object(ses, 'close'):
        try: ses.send_prompt('Write the vendor notes.', brief=True)
        except general.Stopped: pass
        else: raise AssertionError('a stopped turn says so to its caller')
    assert s.last_worker_event(tid, skip=ws.NOTES)['Kind'] == 'stopped'

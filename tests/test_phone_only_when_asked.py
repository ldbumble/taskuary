"""The phone speaks only when spoken to (the owner, 2026-10-23: "why is whatsapp still sending me messages. i never asked it
anything today? ... it should not talk to phone unless it was triggered from there"). A task asked from the phone days before
kept saying each lane its agent passed through while the owner worked at the desktop. Now the owner's own chat hears from
Taskuary only inside a conversation the owner started there - their last word within the window, until they say stop - and
every road to it (remote_assistant.send) is held outside one. Replies to other people are not this road and are untouched."""
import json, time
from unittest import mock

import pytest

from taskuary import asks, concierge, funnel, messengers, outbound, remote_assistant as ra
from taskuary.store import MemoryStore
from tests.test_remote_assistant import JID, armed_store


def _quiet_phone(store): ra.hung_up(store, 'whatsapp', JID)


def _sent(fn):
    with mock.patch.object(messengers, 'wa_send') as out: fn()
    return [c.args[2] for c in out.call_args_list]


# ── the session ────────────────────────────────────────────────────────────────────────────────────
def test_nothing_reaches_the_chat_until_the_owner_writes_there():
    s, c = armed_store(talking=False)
    assert not ra.in_session(s, 'whatsapp', JID)
    assert _sent(lambda: ra.send(s, 'whatsapp', JID, 'TQ-0007 is back: the agent asked you something.', c['ConnectorId'])) == []
    ra.owner_spoke(s, 'whatsapp', JID)
    assert _sent(lambda: ra.send(s, 'whatsapp', JID, 'TQ-0007 is back.', c['ConnectorId']))


def test_the_session_ends_when_the_window_runs_out():
    s, _c = armed_store()
    assert ra.in_session(s, 'whatsapp', JID)
    s.set_setting(ra.SESSION_KEY, json.dumps({f'whatsapp:{JID}': time.time() - (ra.SESSION_MINS + 1) * 60}), 't')
    assert not ra.in_session(s, 'whatsapp', JID)
    s.set_setting('phone_session_minutes', '60', 't')                     # the window is a setting
    assert ra.in_session(s, 'whatsapp', JID)


def test_a_session_is_its_own_chat_only():
    s, _c = armed_store()
    assert ra.in_session(s, 'whatsapp', JID) and not ra.in_session(s, 'telegram', JID) and not ra.in_session(s, 'whatsapp', 'other@s.whatsapp.net')


def test_writing_opens_it_and_stop_ends_it_after_its_answer():
    s, c = armed_store(talking=False)
    with mock.patch.object(concierge, 'brain', return_value=None):
        said = _sent(lambda: ra.respond(s, 'whatsapp', JID, 'stop', c['ConnectorId']))
    assert said and 'Stopped' in said[0]                                     # the answer to "stop" still goes...
    assert not ra.in_session(s, 'whatsapp', JID)                             # ...and nothing after it


def test_held_back_logs_a_debug_line():
    s, _c = armed_store(talking=False)
    with mock.patch.object(ra.logger, 'debug') as dbg:
        assert ra.held_back(s, 'whatsapp', JID, 'a by-the-way')
    assert 'held back a by-the-way' in dbg.call_args.args[0]


# ── every road that used to speak first ────────────────────────────────────────────────────────────
@pytest.fixture
def phone_ask():
    s = MemoryStore()
    with mock.patch('taskuary.concierge._handoff_brief', side_effect=lambda st, tid, job: job), \
         mock.patch('taskuary.concierge._handoff_title', return_value='Check the four tabs'):
        tid = concierge.setup_task(s, 'Check the four tabs', 'owner', kind='general', agent_job=True)['taskId']
    s.update_task(tid, {'AskedVia': 'whatsapp:c1@example.com'}, 'owner')
    yield s, tid
    s.close()


def _lane(s, tid, lane):
    return mock.patch.object(asks, '_rail', return_value=[{'tid': tid, 'lane': lane, 'why': 'the agent asked you which tab'}])


def test_an_ask_made_on_the_phone_days_ago_does_not_follow_the_owner_to_the_desk(phone_ask):
    # what messaged the owner eight times on 2026-10-23: each lane move of a task asked from the phone two days before
    s, tid = phone_ask
    with _lane(s, tid, 'blocked'), mock.patch.object(ra, 'connector_for_chat', return_value={'ConnectorId': 3}), \
         mock.patch.object(ra, 'quiet', return_value=True), mock.patch.object(ra, 'send') as send:
        asks.check(s, tid)
    assert not send.called
    assert s.get_task(tid)['AskedTold'] == 'blocked'                         # the desk's to tell (the rail row): not owed for later


def test_the_same_ask_is_said_while_the_owner_is_talking_there(phone_ask):
    s, tid = phone_ask
    ra.owner_spoke(s, 'whatsapp', 'c1@example.com')
    with _lane(s, tid, 'blocked'), mock.patch.object(ra, 'connector_for_chat', return_value={'ConnectorId': 3}), \
         mock.patch.object(ra, 'quiet', return_value=True), mock.patch.object(ra, 'send') as send:
        asks.check(s, tid)
    assert send.called and send.call_args.args[2] == 'c1@example.com'


def test_a_reminder_set_on_the_phone_comes_due_on_the_desk_when_the_phone_is_quiet(phone_ask):
    from datetime import datetime, timedelta
    from taskuary import remind
    s, tid = phone_ask
    day = datetime.now() + timedelta(days=2)                                   # relative: a fixed date turns into "that day has gone"
    ra._ASKING.chat = {'channel': 'whatsapp', 'chat': 'c1@example.com', 'connector_id': 3}
    try: remind.set_reminder(s, tid, day.strftime('%Y-%m-%d'), 'owner')
    finally: ra._ASKING.chat = None
    with mock.patch.object(ra, 'connector_for_chat', return_value={'ConnectorId': 3}), \
         mock.patch.object(ra, 'quiet', return_value=True), mock.patch.object(ra, 'send') as send:
        remind.due(s, day.replace(hour=9, minute=0))
    assert not send.called and not s.get_task(tid)['RemindOwed']


def test_a_promise_from_a_conversation_that_ended_is_not_kept_on_the_phone():
    s, _c = armed_store()
    tid = s.create_task({'Title': 'Reconcile the March ledger', 'Kind': 'general', 'Status': 'done'}, 'owner')
    s.set_setting(ra.PROMISES_KEY, json.dumps([{'tid': tid, 'channel': 'whatsapp', 'chat': JID, 'at': time.time(), 'lane': 'working',
                                                'armed': True}]), 't')
    _quiet_phone(s)
    with mock.patch.object(funnel, 'pile', return_value={'items': [], 'alerts': []}):
        assert _sent(lambda: ra.keep_promises(s, force=True)) == []
    assert ra._promises(s) == []                                               # dropped: the rail has it, the phone hears nothing later


def test_a_by_the_way_needs_the_owner_in_the_chat_even_with_the_walk_handed_there():
    s, c = armed_store()
    s.set_setting(ra.HANDOFF_KEY, json.dumps({'channel': 'whatsapp', 'chat': JID, 'connector_id': c['ConnectorId'], 'at': 'now'}), 't')
    _quiet_phone(s)
    alert = {'key': 'a1', 'item': 'msg:1', 'text': 'Erin Blake needs the deck in ten minutes', 'kind': 'meeting', 'order_band': 0}
    with mock.patch.object(funnel, 'pile', return_value={'items': [], 'alerts': [alert]}):
        assert _sent(lambda: ra.push_alerts(s, force=True)) == []


def test_the_morning_line_turned_on_does_not_speak_first():
    s, _c = armed_store(talking=False)
    s.set_setting(ra.MORNING_KEY, '1', 't')
    with mock.patch.object(funnel, 'pile', return_value={'items': [{'key': 'msg:1', 'lane': 'approve', 'title': 'Budget'}]}):
        assert _sent(lambda: ra.morning_line(s, force=True)) == []


def test_closing_says_nothing_to_a_chat_nobody_is_talking_in():
    s, _c = armed_store(talking=False)
    tid = s.create_task({'Title': 'Reconcile the March ledger', 'Kind': 'general', 'Status': 'done'}, 'owner')
    s.set_setting(ra.PROMISES_KEY, json.dumps([{'tid': tid, 'channel': 'whatsapp', 'chat': JID, 'at': time.time()}]), 't')
    assert _sent(lambda: ra.promises_closing(s)) == []
    assert ra._promises(s) == []


def test_picking_the_chat_on_the_desktop_is_the_owner_asking_for_its_one_line():
    s, _c = armed_store(talking=False)
    assert _sent(lambda: ra.hello_chat(s, 'whatsapp', JID))


# ── other people are not this road ─────────────────────────────────────────────────────────────────
def test_a_reply_the_owner_approved_to_someone_else_still_goes():
    s, _c = armed_store(talking=False)
    mid = s.add_message({'ExternalId': 'whatsapp:9', 'Channel': 'whatsapp', 'ConversationId': 'whatsapp:15550100200@s.whatsapp.net',
                         'Subject': 'hi', 'BodyText': 'is Thursday still on?', 'FromName': 'Gail Moreno', 'SentAt': '2026-10-23 10:00:00',
                         'Status': 'open'})
    with mock.patch.object(outbound, 'can_reply', return_value=True), mock.patch.object(messengers, 'wa_send') as out:
        outbound.reply_to_message(s, s.get_message(mid), 'Yes - Thursday at 2 still works.')
    assert out.called and out.call_args.args[1] == '15550100200@s.whatsapp.net'


# ── urgent does not break the rule - unless the owner turns it on (2026-10-24) ─────────────────────
def test_an_urgent_task_move_waits_on_the_desk_by_default_and_reaches_the_phone_with_the_switch_on(phone_ask):
    s, tid = phone_ask
    s.update_task(tid, {'Priority': 'urgent'}, 'owner')
    assert s.get_setting(ra.URGENT_KEY) in (None, '', '0')                    # off unless turned on
    patches = lambda: (_lane(s, tid, 'blocked'), mock.patch.object(ra, 'connector_for_chat', return_value={'ConnectorId': 3}),
                       mock.patch.object(ra, 'quiet', return_value=True))
    a, b, c = patches()
    with a, b, c, mock.patch.object(messengers, 'wa_send') as out: asks.check(s, tid)
    assert not out.called
    s._exec('UPDATE task SET AskedTold=NULL WHERE TaskId=?', (tid,)); s.set_setting(ra.URGENT_KEY, '1', 'owner')
    a, b, c = patches()
    with a, b, c, mock.patch.object(messengers, 'wa_send') as out: asks.check(s, tid)
    assert out.called and out.call_args.args[1] == 'c1@example.com'


def test_the_urgent_switch_lets_through_only_what_is_urgent():
    s, c = armed_store(talking=False)
    s.set_setting(ra.URGENT_KEY, '1', 'owner')
    assert _sent(lambda: ra.send(s, 'whatsapp', JID, 'TQ-0007 moved.', c['ConnectorId'])) == []          # a plain line still waits
    assert _sent(lambda: ra.send(s, 'whatsapp', JID, 'TQ-0007 is urgent.', c['ConnectorId'], urgent=True))
    s.set_setting(ra.URGENT_KEY, '0', 'owner')
    assert _sent(lambda: ra.send(s, 'whatsapp', JID, 'TQ-0007 is urgent.', c['ConnectorId'], urgent=True)) == []


def test_an_urgent_by_the_way_goes_unasked_only_with_the_switch_on_and_only_the_urgent_one():
    s, c = armed_store()
    s.set_setting(ra.HANDOFF_KEY, json.dumps({'channel': 'whatsapp', 'chat': JID, 'connector_id': c['ConnectorId'], 'at': 'now'}), 't')
    _quiet_phone(s)
    items = [{'key': 'msg:1', 'lane': 'time', 'title': 'Board call', 'order_band': 1},
             {'key': 'msg:2', 'lane': 'asked', 'title': 'Lunch next week', 'order_band': 2}]
    alerts = [{'key': 'a1', 'item': 'msg:1', 'text': 'Board call with Ray Colton in ten minutes', 'kind': 'meeting', 'order_band': 1},
              {'key': 'a2', 'item': 'msg:2', 'text': 'Omar Keller asked about lunch', 'kind': 'ask', 'order_band': 2}]
    with mock.patch.object(funnel, 'pile', return_value={'items': items, 'alerts': alerts}):
        assert _sent(lambda: ra.push_alerts(s, force=True)) == []
        s.set_setting(ra.URGENT_KEY, '1', 'owner')
        said = _sent(lambda: ra.push_alerts(s, force=True))
    assert len(said) == 1 and 'Board call' in said[0] and 'lunch' not in said[0]


def _report(to):
    return ({'SourceId': 41, 'Address': 'report:41'},
            {'title': 'Ledger check', 'alert': {'channel': 'whatsapp', 'to': [to]}, 'deliver': {'channel': 'whatsapp', 'to': [to], 'gate': 'auto'}})


def test_a_report_alert_to_the_owners_own_chat_waits_unless_urgent_items_may_text():
    from taskuary import reports
    s, _c = armed_store(talking=False)
    src, cfg = _report(JID)
    with mock.patch.object(outbound, 'send_out', return_value={'channel': 'whatsapp'}) as out:
        assert reports.send_alert(s, src, cfg, 'the totals do not match', 'Ledger check', '2 rows').get('held')
        assert not out.called
        s.set_setting(ra.URGENT_KEY, '1', 'owner')
        reports.send_alert(s, src, cfg, 'the totals do not match', 'Ledger check', '2 rows')
    assert out.called and out.call_args.args[2] == [JID]


def test_a_report_sent_by_itself_to_the_owners_own_chat_waits_even_with_the_urgent_switch():
    from taskuary import reports
    s, _c = armed_store(talking=False)
    s.set_setting(ra.URGENT_KEY, '1', 'owner')
    src, cfg = _report(JID)
    with mock.patch.object(outbound, 'send_out', return_value={'channel': 'whatsapp'}) as out:
        assert reports.deliver_report(s, src, cfg, 'Ledger check', '2 rows').get('held')
    assert not out.called


def test_a_report_alert_to_someone_else_is_not_this_road():
    from taskuary import reports
    s, _c = armed_store(talking=False)
    src, cfg = _report('15550100200@s.whatsapp.net')
    with mock.patch.object(outbound, 'send_out', return_value={'channel': 'whatsapp'}) as out:
        reports.send_alert(s, src, cfg, 'the totals do not match', 'Ledger check', '2 rows')
    assert out.called

"""A report is honest about what it could read (the owner, 2026-10-21).

"reports should skip their run if the data source doesn't work and it will show up in error of course. If one source
works and one doesn't it should have a note on the report run of course." A fresh install with no mailbox ran the seeded
End of day checkup at its hour and posted "One more and you're clear." over mail that did not exist.

...and email is not a requirement: a home may be monday.com only, chat only, or nothing but its own tasks. The checkup
covers whatever is connected, and skips only when there is truly nothing to report on.
"""
import json
import sqlite3
from datetime import datetime, timedelta
from unittest import mock

from taskuary import evening, problems, reports
from taskuary.msauth import LAPSED
from taskuary.reports import REGISTRY
from taskuary.store import MemoryStore


def _ago(hours=1): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def _checkup(s): return next(x for x in s.list_sources() if x['Channel'] == 'report' and json.loads(x['ConfigJson'])['type'] == 'evening_inbox')


def _card(s, typ, name, error=None):
    cid = s.save_connector({'Type': typ, 'Name': name, 'ConfigJson': '{}', 'Active': 1, 'Roles': 'trigger'}, 't')
    if error: s.touch_connector(cid, error)
    return cid


def _said(s, channel, subject, who='Erin Blake', hours=1):
    """Something that came in and is now open work - the kind of row a brief lists for tomorrow."""
    tid = s.create_task({'Title': subject, 'Kind': 'task'}, 'triage')
    return s.add_message({'ExternalId': f'{channel}:{subject}', 'Channel': channel, 'Subject': subject, 'FromName': who, 'TaskId': tid,
                          'SentAt': _ago(hours), 'BodyText': f'{subject}, please.', 'Status': 'routed'})


def _run(s, src=None, llm=None):
    src = src or _checkup(s)
    out = reports.run_report_source(s, src, llm)
    return out, s.report_runs(src['SourceId'], 1)[0]


def _rail_rows(s): return [m for m in s._rows("SELECT * FROM message WHERE Channel='report'")]


# ── nothing to read: a FAILED run with the reason, nothing on the rail ─────────────────────────────
def test_a_fresh_home_with_nothing_connected_skips_the_checkup_with_the_reason():
    s = MemoryStore()
    out, run = _run(s)
    assert out['failed'] and out['message_id'] is None
    assert run['failed'] and run['error'].startswith('Skipped: nothing is connected'), run['error']
    assert not _rail_rows(s)                                   # no normal report over nothing
    rung = [p for p in problems.collect(s) if p['key'] == f"report:{_checkup(s)['SourceId']}"]
    assert rung and rung[0]['title'] == 'Report failed: End of day checkup' and 'Skipped' in rung[0]['detail']


def test_a_home_whose_only_mailbox_is_signed_out_skips_and_says_so():
    s = MemoryStore()
    _card(s, 'outlook', 'Outlook', f'{LAPSED} - sign in again')
    out, run = _run(s)
    assert out['failed'] and not _rail_rows(s)
    assert run['error'].startswith('Skipped: Outlook could not be read') and 'signed out' in run['error'], run['error']


# ── some sources work: the run goes on, with the note ──────────────────────────────────────────────
def test_two_sources_one_signed_out_runs_over_the_other_with_a_note():
    s = MemoryStore()
    _card(s, 'outlook', 'Outlook', f'{LAPSED} - sign in again')
    _card(s, 'slack', 'Slack')
    _said(s, 'slack', 'Budget sign-off for Q4')
    seen = {}
    out, run = _run(s, llm=lambda system, user, **kw: seen.update(user=user) or 'Done today: little.\nTomorrow: the budget.')
    assert not out['failed'] and out['message_id']
    assert 'Outlook: FAILED' in run['subject'] and 'Slack' in run['subject']
    assert run['error'].startswith('Not read this run: Outlook') and 'signed out' in run['error'], run['error']
    assert 'COULD NOT READ THIS RUN: Outlook' in seen['user'] and 'Budget sign-off for Q4' in seen['user']
    rung = [p for p in problems.collect(s) if p['key'] == f"report:{_checkup(s)['SourceId']}"]
    assert rung and rung[0]['title'] == 'End of day checkup ran without Outlook' and 'signed out' in rung[0]['detail']


def test_a_data_card_report_with_one_source_down_runs_with_the_note():
    s = MemoryStore()
    REGISTRY['_ok'] = lambda cfg: ('3 rows', 'a\nb\nc')
    REGISTRY['_down'] = lambda cfg: (_ for _ in ()).throw(RuntimeError('login timeout'))
    try:
        sid = s.save_source({'Channel': 'report', 'Address': 'Ledger check', 'Active': 1, 'ConfigJson': json.dumps(
            {'title': 'Ledger check', 'sources': [{'type': '_ok', 'label': 'cash'}, {'type': '_down', 'label': 'the box'}]})}, 't')
        out, run = _run(s, s.get_source(sid))
        assert not out['failed'] and out['message_id']
        assert run['error'] == 'Not read this run: the box - login timeout', run['error']
    finally: REGISTRY.pop('_ok'); REGISTRY.pop('_down')


def test_a_data_card_report_with_every_source_down_is_skipped():
    s = MemoryStore()
    REGISTRY['_down'] = lambda cfg: (_ for _ in ()).throw(RuntimeError('login timeout'))
    try:
        sid = s.save_source({'Channel': 'report', 'Address': 'Ledger check', 'Active': 1, 'ConfigJson': json.dumps(
            {'title': 'Ledger check', 'ai_prompt': 'anything odd?', 'sources': [{'type': '_down', 'label': 'cash'}, {'type': '_down', 'label': 'the box'}]})}, 't')
        llm = mock.Mock(return_value='all clear')
        out, run = _run(s, s.get_source(sid), llm)
        assert out['failed'] and not llm.called                    # no summary paid for over nothing
        assert run['error'] == 'Skipped: no source could be read - cash: login timeout; the box: login timeout', run['error']
    finally: REGISTRY.pop('_down')


def test_a_single_card_report_whose_source_fails_is_skipped_with_the_plain_reason():
    s = MemoryStore()
    REGISTRY['_down'] = lambda cfg: (_ for _ in ()).throw(RuntimeError('getaddrinfo failed'))
    try:
        sid = s.save_source({'Channel': 'report', 'Address': 'Ledger check', 'Active': 1, 'ConfigJson': json.dumps({'title': 'Ledger check', 'type': '_down'})}, 't')
        out, run = _run(s, s.get_source(sid))
        assert out['failed'] and run['error'].startswith('Skipped: _down could not be read - The server\'s address could not be found'), run['error']
    finally: REGISTRY.pop('_down')


def test_own_data_that_cannot_be_read_is_a_skip_naming_it():
    s = MemoryStore()
    with mock.patch.object(evening, 'collect', side_effect=sqlite3.OperationalError('database is locked')):
        out, run = _run(s)
    assert out['failed'] and run['error'] == "Skipped: Taskuary's own data could not be read - database is locked"


# ── every source fine: a normal run, empty or not ──────────────────────────────────────────────────
def test_a_connected_mailbox_with_nothing_in_the_window_is_a_normal_empty_run():
    s = MemoryStore()
    _card(s, 'outlook', 'Outlook')
    out, run = _run(s)
    assert not out['failed'] and out['message_id'] and not run['error']
    assert run['subject'] == 'End of day checkup — the last 8 hours of Outlook and your Taskuary work'


def test_a_monday_only_home_gets_its_end_of_day_over_monday():
    s = MemoryStore()
    _card(s, 'monday', 'monday.com')
    _said(s, 'monday', 'Ship the onboarding board', who='Gail Moreno')
    head, body = evening.brief(s, 8)
    assert head == 'the last 8 hours of monday.com and your Taskuary work'
    assert 'Ship the onboarding board' in body and 'where=monday' in body and 'email' not in head


def test_a_chat_only_home_gets_its_end_of_day_over_chat():
    s = MemoryStore()
    _card(s, 'slack', 'Slack')
    _said(s, 'slack', 'Can you look at the vendor quote', who='Ray Colton')
    s.add_message({'ExternalId': 'mine', 'Channel': 'slack', 'Subject': 'Sent it over', 'FromName': 'Alex Doyle',
                   'SentAt': _ago(), 'BodyText': 'Sent it over.', 'Status': 'context', 'Direction': 'out'})
    head, body = evening.brief(s, 8)
    assert 'Slack' in head and 'Can you look at the vendor quote' in body and 'state=sent' in body


def test_a_home_with_nothing_connected_still_gets_a_brief_over_its_own_tasks():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Draft the Northwind renewal', 'Kind': 'task', 'Priority': 'urgent'}, 'owner')
    rid = s.start_run(tid, 'researcher', 'look into it', 'owner')
    head, body = evening.brief(s, 8)
    assert head == 'the last 8 hours of your Taskuary work'
    assert 'Draft the Northwind renewal' in body and 'agent=researcher' in body
    out, run = _run(s)
    assert not out['failed'] and out['message_id']


def test_a_mail_home_is_read_as_before():
    s = MemoryStore()
    _card(s, 'outlook', 'Outlook')
    _said(s, 'email', 'Renewal decision', who='Paula Vance')
    head, body = evening.brief(s, 8)
    assert head == 'the last 8 hours of Outlook and your Taskuary work'
    line = next(l for l in body.splitlines() if 'subject=Renewal decision' in l)
    assert 'state=open priority' in line and 'where=' not in line          # a mail row reads as it always did


def test_the_seeded_prompt_names_no_channel_and_an_unedited_old_one_is_healed():
    assert 'Inbox Brief' not in evening.PROMPT and 'emails in my Inbox' not in evening.PROMPT
    assert any('Inbox Brief for emails' in p for p in evening.OLD_PROMPTS)

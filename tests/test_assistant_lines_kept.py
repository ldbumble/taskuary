"""The Assistant's own lines, kept, and what the next turn reads of them (the owner, 2026-11-03, after the Assistant stress run): a receipt the
page drew once an act happened came back on a reload; a report opens as Search opens it, read or not; the conversation the model reads names
the item each card line brought up, so "and the other one?" is not a guess. The demo world only - invented people, nobody real."""
import json
from unittest import mock
from taskuary import concierge, general, search, toolcatalog
from tests.assistant_queries import _world


def _dock(s): return general.dock_task(s, 'owner')[0]['TaskId']


def test_a_receipt_the_page_drew_comes_back_a_receipt_after_a_reload():
    s = _world()
    concierge.record(s, _dock(s), 'user', 'open the invoice task')
    concierge.keep_line(s, 'Opened TQ-0004 - Payworth invoice 88213.', 'done')
    last = concierge.history(s, _dock(s))[-1]
    assert (last['role'], last['status'], last['text'], last['card']) == ('receipt', 'done', 'Opened TQ-0004 - Payworth invoice 88213.', None)
    # ...and the next turn's model reads what was done
    assert 'YOU: Opened TQ-0004 - Payworth invoice 88213.' in concierge._turns(s, _dock(s))


def test_an_answers_steps_on_the_page_are_kept_on_its_own_line():
    s = _world()
    concierge.record(s, _dock(s), 'assistant', 'Run now is the one.')
    steps = [{'id': 'view-1', 'kind': 'read', 'summary': 'Opened the Reports page', 'status': 'done'}]
    concierge.keep_line(s, 'Run now is the one.', steps=steps)
    last = concierge.history(s, _dock(s))[-1]
    assert last['text'] == 'Run now is the one.' and last['card']['steps'][0]['summary'] == 'Opened the Reports page'
    assert len([t for t in concierge.history(s, _dock(s)) if t['text'] == 'Run now is the one.']) == 1, 'one line, never a second copy'
    # ...an answer with no words of its own gets a line of its steps
    concierge.keep_line(s, '', steps=steps)
    assert concierge.history(s, _dock(s))[-1]['card']['steps'] == steps


def test_nothing_is_kept_from_nothing():
    s = _world()
    try: concierge.keep_line(s, '  ', 'done'); assert False, 'kept an empty line'
    except ValueError: pass


def test_the_conversation_the_model_reads_names_what_each_card_brought_up():
    # "Next up: a report." said nothing of WHICH report: "and the other one?" was answered off a guess (the stress run, 2026-11-03)
    s = _world()
    run = s.get_message(10)
    card = {'key': 'report:10', 'kind': 'report', 'title': run['Subject'], 'who': 'AP ageing over 30 days, weekly', 'mid': 10}
    concierge.record(s, _dock(s), 'assistant', 'Next up: a report.', card)
    said = concierge._turns(s, _dock(s)).splitlines()[-1]
    assert said.startswith('YOU: Next up: a report. [brought up: m10') and 'AP ageing over 30 days, weekly - 5 rows' in said
    assert '<!--' not in said and '"key"' not in said, 'the card is named, never pasted'
    # ...a batch names each of its rows, and a line with no item adds nothing
    batch = {'key': 'fyis:a,b', 'kind': 'fyis', 'items': [{'key': 'msg:5', 'mid': 5, 'title': 'Newsletter'}, {'key': 'task:2', 'ref': 'TQ-0002', 'title': 'New starter'}]}
    assert concierge._card_said(concierge.MARK + json.dumps(batch) + ' -->') == ' [brought up: m5 · Newsletter; TQ-0002 · New starter]'
    assert concierge._card_said('Done.') == '' and concierge._card_said(concierge.MARK + json.dumps({'kind': 'words', 'key': None}) + ' -->') == ''


def test_a_report_opens_as_search_opens_it_its_newest_run_read_or_not():
    s = _world()
    assert s.get_message(10)['Status'] == 'filed', 'the demo run is read already - that is the point'
    ap = search.places(s, 'AP ageing')[0]
    assert (ap['href'], ap['page']) == ('#msg=10', '#report=5')
    # ...the very card a Search pick puts on the table: its hit is that run
    assert ('report', 10) in [(h['type'], h.get('mid')) for h in search.everything(s, 'AP ageing')['hits']]
    # ...found by what it says, too
    assert search.places(s, 'Kesler Medical')[0]['href'] == '#msg=10'
    # ...and one that never ran opens its page
    assert search.places(s, 'end of day')[0]['href'] == '#report=2'
    told = concierge.read_op(s, 'app.find', {'query': 'AP ageing report'})
    assert '[AP ageing over 30 days, weekly](#msg=10)' in told and 'its page to edit or pause: #report=5' in told


def test_search_finds_a_report_the_owner_read_put_down_or_that_left_the_rail():
    s = _world()
    sid = 5
    mid = s.add_message({'ExternalId': 'report:5:old', 'ConversationId': f'report:{sid}', 'Channel': 'report', 'SourceName': 'AP ageing',
                         'Subject': 'AP ageing over 30 days, weekly - 3 rows', 'FromName': 'AP ageing', 'SentAt': '2026-10-01 08:00:00',
                         'BodyText': '{"vendor": "Quillfeather Paper", "past_due": 512.0}', 'Status': 'done'})
    hits = [(h['type'], h.get('mid')) for h in search.everything(s, 'Quillfeather')['hits']]
    assert hits == [('report', mid)], hits


def test_the_index_says_opened_is_the_pages_word_and_a_message_to_send_is_new():
    b = toolcatalog.block()
    assert len(b) < 7950
    assert 'never "Opening" or a promise' in b.replace('Never', 'never')
    assert 'a message to send kind send' in b and 'never pasted here' in b and 'task.create_from_text(kind, text, channel?, to?)' in b


def test_the_page_guide_says_acts_speak_for_themselves():
    from taskuary import pageview
    assert 'never narrate them ("Opening ...", "I\'ll open ...")' in pageview.GUIDE

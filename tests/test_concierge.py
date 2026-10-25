"""Taskuary, the assistant you talk to (concierge.py): one item out of the pipe per turn, said by a
light model or by the facts when there is none; the conversation lives on the dock task with the
card recorded beside each line; a new chat walks the pipe afresh. The model is a lambda throughout."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import buttons, concierge, funnel, general, server, terminal
from taskuary.store import MemoryStore


def ago(hours=0): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    s = MemoryStore()
    # an install has a coding agent - config.toml seeds it at boot. Without one the assistant now
    # says so instead of receipting a hand-off the dispatch would 422 on (2026-09-03).
    s.upsert_agent('coding', 'coding', 'cli', '{}')
    for k in ('calendar_enabled', 'coding_auto_enabled', 'learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._CACHE.update(cands_at=0.0, cands=[])
    return s


def _verb(d):
    """(verb, text) - the two fields a caller acts on; the rest is the guard's working-out."""
    return (None if d is None else (d.get('verb'), d.get('text')))


# THE PHONE'S ROAD (the owner, 2026-10-19): on the desk a typed act lights its button and proposes nothing (test_assistant_router); a phone
# chat has no buttons, so its words still become the proposal answered yes or no - the proposal semantics are held here, on that road
def phone(): return concierge.delivering(concierge.PHONE)


def decided(s, text, verb, key=None, arg=None, on=None):
    """The model named the decision: its CALL line is the contract, the words are the owner's (PW-121)."""
    line = 'Ok.\n' + 'CALL: ' + json.dumps({'kind': verb, 'params': {k: v for k, v in (('text', arg), ('on', on)) if v}})
    with phone(): return concierge.say(s, text, key=key, llm=lambda *a, **k: line)


def cleared_by(s, text, select):
    """The model named the SET to clear - pipe.clear `select` - the only road to a clear (2026-10-08: no word list sweeps)."""
    line = 'Ok.\n' + 'CALL: ' + json.dumps({'kind': 'pipe.clear', 'params': {'select': select}})
    with phone(): return concierge.say(s, text, llm=lambda *a, **k: line)


def run(s, p, version=None):
    """The confirmation button: the structured proposal by id and version, through the shared execute road (PW-124/125)."""
    with mock.patch.object(server, 'store', s), mock.patch.object(terminal, 'live_sessions', return_value=[]):
        return TestClient(server.app).post(f"/api/operations/{p['id']}/execute", json={'version': version if version is not None else p['version']})


def last_receipt(s):
    rows = [c for c in general.chat_rows(s, general.dock_task(s)[0]['TaskId']) if c.get('ActorType') == general.ASSISTANT_TYPE]
    return concierge._MARK.sub('', rows[-1].get('Body') or '') if rows else ''


def drafted(s, subject='Export still broken', who='Dana', hours=5, draft='Attached.'):
    t = s.create_task({'Title': subject, 'Kind': 'coding', 'Status': 'waiting'}, 'o')
    m = s.add_message({'TaskId': t, 'ExternalId': f'x:{subject}', 'ConversationId': f'c:{subject}', 'Channel': 'email', 'Subject': subject, 'FromName': who,
                       'FromEmail': 'dana@vendor.com', 'SentAt': ago(hours), 'BodyText': 'Can you send the corrected file?', 'Status': 'routed'})
    r = s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': draft, 'Status': 'pending'})
    return t, m, r


class TurnTests(unittest.TestCase):
    def test_todays_brief_card_keeps_the_flag_that_draws_its_calendar(self):
        """The Assistant card must retain the funnel's brief marker.

        ReportCard uses this field to mount TodayMeetingsStrip. Dropping it at the
        public-card boundary left the Morning digest text visible but hid the day's
        calendar timeline above it.
        """
        card = concierge.card_for({
            'key': 'report:7', 'kind': 'report', 'lane': 'report',
            'title': 'Morning digest', 'brief_today': True,
        })
        self.assertIs(card['brief_today'], True)

    def test_surface_says_the_next_item_marks_it_shown_and_records_the_card(self):
        s = store()
        t, m, r = drafted(s)
        seen = {}
        fake = lambda system, user, **kw: seen.update(system=system, user=user) or \
            'Dana wants the corrected file; the draft below says "Attached." - I would send it.\nOPTIONS: send it | redraft it'
        out = concierge.surface(s, llm=fake)
        self.assertEqual(out['item']['key'], f'review:{r}')
        self.assertEqual(out['say'], 'Dana wants the corrected file; the draft below says "Attached." - I would send it.')
        self.assertEqual(out['options'], ['send it', 'redraft it'])
        self.assertEqual(out['left'], 0)
        # the model saw the item, the draft and the pile - and was told what it is
        self.assertIn('I am Taskuary', seen['system']); self.assertIn('One item per turn', seen['system'])   # COUNSEL.md's own words now (PW-248/256), then the contract
        self.assertIn('LEFT IN THE PIPE: 1', seen['user']); self.assertIn('THE DRAFT', seen['user']); self.assertIn('Attached.', seen['user'])
        self.assertIn('Can you send the corrected file?', seen['user'])
        # shown once: a reply for your yes stays in the pipe, marked, and is not straight back on the table
        self.assertEqual([(i['key'], i['surfaced']) for i in funnel.build(s)['items']], [(f'review:{r}', True)])
        self.assertIsNone(funnel.next_item(s))
        self.assertTrue(funnel.next_item(s, f'review:{r}')['surfaced'])
        # the conversation carries the card, without the marker in the words
        hist = concierge.history(s, general.dock_task(s)[0]['TaskId'])
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]['role'], 'assistant'); self.assertNotIn('tq:card', hist[0]['text']); self.assertNotIn('OPTIONS', hist[0]['text'])
        self.assertEqual(hist[0]['options'], ['send it', 'redraft it'])
        self.assertEqual((hist[0]['card']['kind'], hist[0]['card']['rid'], hist[0]['card']['draft']), ('review', r, True))

    def test_task_specific_walkthrough_turns_are_kept_with_that_task(self):
        s = store()
        t, m, r = drafted(s)
        concierge.surface(s, key=f'review:{r}', llm=lambda *a, **k: 'Dana needs the corrected export.')
        concierge.say(s, 'what exactly did she ask?', key=f'review:{r}',
                      llm=lambda *a, **k: 'She asked for the corrected file.')
        discussion = [c for c in s.list_comments(t)
                      if c['ActorType'] in (concierge.DISCUSSION_USER_TYPE, concierge.DISCUSSION_ASSISTANT_TYPE)]
        self.assertEqual([c['ActorType'] for c in discussion],
                         [concierge.DISCUSSION_ASSISTANT_TYPE, concierge.DISCUSSION_USER_TYPE,
                          concierge.DISCUSSION_ASSISTANT_TYPE])
        self.assertIn('corrected export', discussion[0]['Body'])

    def test_a_stopped_answer_is_never_kept(self):
        """Stop cannot kill an API call: its answer came back anyway and landed in the chat later, under another card."""
        import threading
        s = store()
        t, m, r = drafted(s)
        cancel = threading.Event()
        def model(*a, **k): cancel.set(); return 'She asked for the corrected file.'   # Stop pressed mid-call
        with self.assertRaises(concierge.Stopped):
            concierge.say(s, 'what exactly did she ask?', key=f'review:{r}', llm=model, cancel=cancel)
        self.assertNotIn('corrected file', last_receipt(s))
        self.assertFalse([c for c in s.list_comments(t) if 'corrected file' in (c.get('Body') or '')])

    def test_what_is_said_about_an_item_is_kept_against_the_item_not_only_in_the_browser(self):
        """PW-132: the chat's turns about an item lived in the dock conversation and the browser's receipts; the
        durable per-item record (operations.discuss) never saw them."""
        from taskuary import operations
        s = store()
        t, m, r = drafted(s)
        concierge.surface(s, key=f'review:{r}', llm=lambda *a, **k: 'Dana needs the corrected export.')
        concierge.say(s, 'what exactly did she ask?', key=f'review:{r}', llm=lambda *a, **k: 'She asked for the corrected file.')
        concierge.say(s, 'what exactly did she ask?', key=f'review:{r}', llm=lambda *a, **k: 'She asked for the corrected file.')   # a double send
        rows = operations.discussion(s, message_id=m)
        self.assertEqual([(x['Actor'], x['Body']) for x in rows],
                         [('Taskuary', 'Dana needs the corrected export.'), ('owner', 'what exactly did she ask?'),
                          ('Taskuary', 'She asked for the corrected file.')], 'attributed, in order, once')
        self.assertTrue(all(x['TaskId'] == t for x in rows), 'and on its task')
        dock = general.dock_task(s)[0]['TaskId']
        self.assertEqual(operations.discussion(s, task_id=dock), [], 'the dock conversation itself is not an item')

    def test_a_deep_dive_is_proposed_for_a_regular_agent_and_starts_only_on_the_click(self):
        s = store()
        out = decided(s, 'can you do a deep dive on the ECC agent harness?', 'regular_agent', arg='do a deep dive on the ECC agent harness')
        p = out['proposal']
        self.assertEqual((p['kind'], p['params']['kind'], p['label']), ('task.create_from_text', 'general', buttons.label('regular_agent')))
        self.assertIn('deep dive', p['params']['text']); self.assertEqual(s.list_tasks(active_only=True), [])   # nothing started on the words
        session = mock.Mock()
        with mock.patch.object(concierge.general, 'start_session', return_value=session), \
             mock.patch.object(concierge.threading, 'Thread') as thread:
            r = run(s, p).json()
        task = s.get_task(r['outcome']['taskId'])
        self.assertEqual((task['Kind'], task['SourceRef']), ('general', 'assistant:agent'))
        self.assertIn('deep dive', task['Summary'])
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()
        self.assertIn('is being worked on now', r['receipt'])          # the words the phone hears; the desk's chat gets no line

    def test_okay_send_it_is_read_with_the_conversation_and_keeps_the_prior_brief(self):
        s = store()
        dock, _ = general.dock_task(s)
        concierge.record(s, dock['TaskId'], 'user', 'back to GitHub: do a deep dive on the ECC harness')
        concierge.record(s, dock['TaskId'], 'assistant', 'I can dig into the ECC harness. That is reading and analysis work, not a code change.')
        seen = {}
        def model(system, user, **kw):
            seen['user'] = user
            return 'A regular agent, then.\nCALL: {"kind": "regular_agent", "params": {"text": "do a deep dive on the ECC harness"}}'
        with phone(): out = concierge.say(s, 'okay send it', llm=model)
        self.assertIn('CONVERSATION SO FAR', seen['user']); self.assertIn('ECC harness', seen['user'])   # the model has what was offered
        p = out['proposal']
        self.assertIn('ECC harness', p['params']['text']); self.assertIn('ECC harness', p['params']['title'])
        self.assertNotEqual(p['params']['title'].lower(), 'okay send it')
        self.assertEqual(s.list_tasks(active_only=True), [])                                       # a proposal, not a task yet

    def test_without_a_model_the_facts_speak(self):
        s = store()
        t, m, r = drafted(s)
        with mock.patch.object(concierge, 'brain', return_value=None):
            self.assertEqual(concierge.surface(s)['say'], 'Next up: TQ-0001.')   # the desk: the card carries it
        s = store(); drafted(s)
        with mock.patch.object(concierge, 'brain', return_value=None), concierge.delivering(concierge.PHONE):
            out = concierge.surface(s)
        self.assertIn('Dana wrote on email', out['say']); self.assertIn('"Export still broken"', out['say'])
        self.assertIn('Since then: I read it as needing a reply', out['say']); self.assertIn('From you: Send, Redraft, or move on', out['say'])
        self.assertEqual(out['options'], [])

    def test_a_model_that_fails_still_leaves_a_line(self):
        s = store(); drafted(s)
        def boom(*a, **k): raise RuntimeError('quota')
        out = concierge.surface(s, llm=boom)
        self.assertEqual(out['say'], 'Next up: TQ-0001.')

    def test_an_empty_pipe_says_all_done_and_a_missing_key_says_so(self):
        s = store()
        out = concierge.surface(s, llm=lambda *a, **k: 'never called')
        self.assertIsNone(out['item']); self.assertEqual(out['say'], concierge.ALL_DONE)
        concierge.surface(s, llm=lambda *a, **k: 'never called')
        self.assertEqual([h['text'] for h in concierge.history(s, general.dock_task(s)[0]['TaskId'])],
                         [concierge.ALL_DONE])                         # two auto-advances persist one answer
        dock = general.dock_task(s)[0]
        s.add_comment(dock['TaskId'], 'assistant', general.ASSISTANT_TYPE, concierge.ALL_DONE)
        self.assertEqual([h['text'] for h in concierge.history(s, dock['TaskId'])],
                         [concierge.ALL_DONE])                         # legacy duplicate rows render once too
        drafted(s)
        first = concierge.surface(s, llm=lambda *a, **k: 'first')
        again = concierge.surface(s, llm=lambda *a, **k: 'never', leaving=first['item']['key'])      # Next, as the page presses it
        # ...walked past, it is still under Tasks - Next moves on, the task stays, and the next walk starts with it (the owner, 2026-10-21)
        # ...and the desk says no sentence about it: the buttons do the talking (the owner, 2026-10-23: "yes remove the sentence, just the button")
        self.assertIsNone(again['item']); self.assertEqual(again['say'], '')
        # ...and the way to it NOW is a button naming it - a Next under this line only said it again (2026-09-23) - after the walk again
        self.assertEqual([c['verb'] for c in again['chips']], ['walk', 'open'])
        self.assertTrue(again['chips'][1]['label'].startswith('Open TQ-'))
        gone = concierge.surface(s, key='msg:999', llm=lambda *a, **k: 'never')
        self.assertIsNone(gone['item']); self.assertIn("can't find that one", gone['say'])

    def test_words_that_name_a_thing_pull_it_into_the_chat(self):
        s = store()
        t, m, r = drafted(s)                                            # Dana, "Export still broken"
        s.add_message({'ExternalId': 'x:lee', 'Channel': 'teams', 'Subject': 'Teams chat with Lee', 'FromName': 'Lee Park', 'FromEmail': 'lee@ours.com',
                       'SentAt': ago(1), 'BodyText': 'lunch?', 'Status': 'filed'})
        # the model names a row by its HANDLE - TQ ref or m-number off THE RAIL BY NAME - and code only checks it (2026-10-08: a
        # word-overlap lookup of the model's phrase put actions on whatever subject shared its words)
        self.assertEqual(concierge._resolve_named(s, f'TQ-{t:04d}', None), f'task:{t}')
        self.assertEqual(concierge._resolve_named(s, 'm2', None), 'msg:2')
        self.assertEqual(concierge._resolve_named(s, 'TQ-0999', None), '?')
        for words in ('what did Dana send about the export?', 'show me the Lee chat', 'thanks, next'):
            self.assertEqual(concierge._resolve_named(s, words, None), '?', "words are the model's to resolve, never a guess here")
        old = s.create_task({'Title': 'Rename the flag', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        s.add_comment(old, 'claude', 'agent', 'AGENT REPORT\nSummary: renamed it in three places.')
        pulled = concierge.surface(s, key=f'task:{old}', llm=lambda *a, **k: 'That one is renamed in three places.')
        self.assertEqual((pulled['item']['kind'], pulled['item']['tid']), ('task', old)); self.assertIn('renamed it', pulled['item']['summary'])
        concierge.surface(s, llm=lambda *a, **k: 'first')               # Dana's is on the table
        # ...but the owner's WORDS never override the model's answer: a word match replaced it with whatever subject
        # shared half the words - "yes, go ahead" became someone else's message (the 2026-09-24 debug). The model
        # reads the thing itself (message.read, task.read) or names it on a decision (ON:).
        out = concierge.say(s, 'what did Lee say?', key=f'review:{r}', llm=lambda *a, **k: 'Lee asked about lunch.')
        self.assertEqual(out['say'], 'Lee asked about lunch.')
        self.assertNotEqual((out.get('item') or {}).get('who'), 'Lee Park')

    def test_say_records_the_owners_words_and_answers_about_the_item(self):
        s = store()
        t, m, r = drafted(s)
        concierge.surface(s, llm=lambda *a, **k: 'Dana wants the file.')
        seen = {}
        fake = lambda system, user, **kw: seen.update(user=user) or 'She asked for the corrected export file, on Tuesday.'
        out = concierge.say(s, 'what exactly did she ask?', key=f'review:{r}', llm=fake)
        self.assertEqual(out['say'], 'She asked for the corrected export file, on Tuesday.')
        self.assertIn('The owner says: what exactly did she ask?', seen['user'])
        self.assertIn('CONVERSATION SO FAR', seen['user']); self.assertIn('YOU: Dana wants the file.', seen['user'])
        roles = [(h['role'], h['text']) for h in concierge.history(s, general.dock_task(s)[0]['TaskId'])]
        self.assertEqual(roles[1:], [('user', 'what exactly did she ask?'), ('assistant', 'She asked for the corrected export file, on Tuesday.')])
        with self.assertRaises(ValueError): concierge.say(s, '   ')

    def test_main_assistant_can_publish_a_developed_idea_to_the_hub(self):
        """The Hub is a tool like any other (2026-09-25): no envelope taught every turn, a card the owner confirms."""
        s = store()
        params = {'why_earned': 'We compared three recurring failure patterns and worked through the operating tradeoffs.',
                  'topic': 'customer-launch', 'kind': 'new_idea', 'title': 'Make launch dry-runs reversible by default',
                  'body': 'A reversible dry-run exposes ownership gaps before dates are promised.'}
        seen = {}
        def fake(system, user, **kw):
            seen['system'] = system
            return 'Saving that to the Hub.\n' + 'CALL: ' + json.dumps({'kind': 'hub.publish', 'params': params})
        with phone(): out = concierge.say(s, 'Put that launch idea in the Hub', llm=fake)
        self.assertIn('hub.publish', seen['system']); self.assertNotIn('TASKUARY-HUB', seen['system'])
        self.assertEqual(out['proposal']['kind'], 'hub.publish')
        self.assertEqual(s.lore_posts(), [])                                   # nothing until the click
        with mock.patch.object(server, 'store', s):
            r = TestClient(server.app).post(f"/api/operations/{out['proposal']['id']}/execute", json={'version': out['proposal']['version']})
        self.assertEqual(r.status_code, 200, r.text[:200])
        self.assertEqual([(p['Title'], p['Kind'], p['Author']) for p in s.lore_posts()],
                         [('Make launch dry-runs reversible by default', 'new_idea', 'assistant')])

    def test_the_named_item_is_surfaced_even_out_of_order(self):
        s = store()
        drafted(s, 'first', hours=9); t2, m2, r2 = drafted(s, 'second', hours=1)
        out = concierge.surface(s, key=f'review:{r2}', llm=lambda *a, **k: 'the second one')
        self.assertEqual(out['item']['title'], 'second')

    def test_options_parse_only_when_there_are_at_least_two(self):
        self.assertEqual(concierge.parse_options('Hello.\nOPTIONS: a | b | c'), ('Hello.', ['a', 'b', 'c']))
        self.assertEqual(concierge.parse_options('Hello.\nOPTIONS: only one'), ('Hello.', []))
        self.assertEqual(concierge.parse_options('No options here'), ('No options here', []))


class DecisionTests(unittest.TestCase):
    def test_the_owners_words_about_the_item_are_a_decision_the_model_names_and_a_proposal_carries_out(self):
        s = store()
        t, m, r = drafted(s)
        concierge.surface(s, llm=lambda *a, **k: 'Dana wants the file.')
        with phone(): out = concierge.say(s, "it's not my issue, let them sort it out", key=f'review:{r}', llm=lambda sy, u, **k: "Not ours, then.\nCALL: {\"kind\": \"not_ours\", \"params\": {}}")
        self.assertIsNone(out['decision']); p = out['proposal']
        self.assertEqual((p['kind'], p['target'], p['label']), ('message.file', m, buttons.label('not_ours')))
        self.assertEqual(s.get_message(m)['Status'], 'routed')                              # nothing filed on the words
        # ...run at once by the page, just this once - no "are you sure" (owner-approved, 2026-10-21): From now on follows as a chip
        self.assertTrue(p.get('auto')); self.assertNotIn(concierge.WAITS, out['say'])
        # a reply request drafts at once and sends nothing (PW-126): the words ride into the draft
        out = concierge.say(s, 'tell her the file is with the developer, Friday', key=f'review:{r}',
                            llm=lambda sy, u, **k: "I'll draft that.\nCALL: {\"kind\": \"reply\", \"params\": {\"text\": \"the file is with the developer, Friday\"}}")
        self.assertEqual(_verb(out['decision']), ('reply', 'the file is with the developer, Friday')); self.assertIsNone(out.get('proposal'))
        told = lambda sy, u, **k: "I'll draft that.\nCALL: {\"kind\": \"reply\", \"params\": {\"text\": \"mention the Friday delivery\"}}"
        out = concierge.say(s, 'can you mention the Friday delivery in the response', key=f'review:{r}', llm=told)
        self.assertEqual(out['decision'], {'verb': 'reply', 'text': 'mention the Friday delivery'})
        # a remark is not a decision
        out = concierge.say(s, 'who is Dana again?', key=f'review:{r}', llm=lambda *a, **k: 'Dana is the vendor contact on the export.')
        self.assertIsNone(out['decision']); self.assertIsNone(out.get('proposal'))
        # ...and nothing on the table means nothing to decide - the words move the WALK instead
        out = concierge.say(s, 'next', key=None, llm=lambda *a, **k: 'Nothing is on the table.\nCALL: {"kind": "next", "params": {}}')
        self.assertIsNone(out.get('decision'))
        # shown, never walked past with Next: still On you, and its Open says so - no sentence (2026-10-08, 2026-10-23)
        self.assertEqual(out['say'], ''); self.assertEqual([c.get('verb') for c in out['chips']], ['walk', 'open'])

    def test_mine_with_nothing_on_the_table_is_a_new_to_do_in_their_words(self):
        """"remind me to renew the contract" came back as DECIDE: mine - theirs to do - and was answered
        "Nothing is on the table" (2026-09-23). With no item, theirs to do is a new task on their list."""
        s = store()
        with phone(): out = concierge.say(s, 'remind me to renew the Cardinal contract next week', key=None,
                                          llm=lambda *a, **k: 'Noted.\nCALL: {"kind": "mine", "params": {"text": "renew the Cardinal contract next week"}}')
        p = out['proposal']
        self.assertEqual((p['kind'], p['label'], p['params']['kind']), ('task.create_from_text', 'Put it on my list', 'task'))
        self.assertIn('renew the Cardinal contract', p['params']['text']); self.assertNotIn('Nothing is on the table', out['say'])

    def test_the_contract_line_is_parsed_and_the_words_alone_decide_nothing(self):
        self.assertEqual(concierge.parse_decision('On it.\nCALL: {"kind": "coding_agent", "params": {"text": "find out why the fix did not stick, and add an admin login"}}')[1],
                         {'verb': 'coding_agent', 'text': 'find out why the fix did not stick, and add an admin login'})
        # a model still saying the verb's legacy name "coder" is read as the same hand-off (VERB_ALIAS)
        self.assertEqual(concierge.parse_decision('On it.\nCALL: {"kind": "coder", "params": {"text": "x"}}')[1]['verb'], 'coding_agent')
        self.assertEqual(concierge.parse_decision('Filing that one.\nCALL: {"kind": "not_ours", "params": {"on": "payroll portal outage"}}')[1],
                         {'verb': 'not_ours', 'text': '', 'on': 'payroll portal outage'})
        self.assertEqual(concierge.parse_decision('Sure.\nCALL: {"kind": "bogus", "params": {}}'), ('Sure.', None))
        self.assertFalse(hasattr(concierge, 'decide_words'))                                # no phrase table (PW-121)
        s = store(); t, m, r = drafted(s)
        concierge.surface(s, llm=lambda *a, **k: 'Dana wants the file.')
        # the model's claim to have acted is never the receipt: with no DECIDE line nothing is proposed, nothing changes
        out = concierge.say(s, 'I will do this just make it a task', key=f'review:{r}', llm=lambda *a, **k: 'Task created - all set!')
        self.assertIsNone(out.get('proposal')); self.assertEqual(s.get_task(t)['Status'], 'waiting')
        self.assertIn('NEVER use your own task, todo or plan tools', concierge.tools_block(s))
        # ...and with no model at all the plain phrases are not read: the facts are said, nothing is decided
        with mock.patch.object(concierge, 'brain', return_value=None):
            out = concierge.say(s, 'not mine, ignore it', key=f'review:{r}')
        self.assertIsNone(out.get('proposal')); self.assertIn('AI', out['say']); self.assertEqual(s.get_message(m)['Status'], 'routed')
        # a clarification is the model's, as options - nothing started
        out = concierge.say(s, 'send to agent', key=f'review:{r}',
                            llm=lambda *a, **k: 'Which kind should take it? Nothing has been started yet.\nOPTIONS: Coding agent | Regular agent')
        self.assertIsNone(out['decision']); self.assertIsNone(out.get('proposal'))
        self.assertEqual(out['options'], ['Coding agent', 'Regular agent'])
        self.assertIn('Nothing has been started', out['say'])


class BrainTests(unittest.TestCase):
    def test_the_cli_is_the_default_brain_on_its_light_gear_and_picks_its_conversation_back_up(self):
        s = store()
        s.upsert_agent('coding', 'coding', 'cli', '{}')
        patcher = mock.patch('taskuary.agents.default_pick', return_value='cli:claude'); patcher.start(); self.addCleanup(patcher.stop)   # whatever this machine has installed
        self.assertEqual(concierge.pick(s), 'cli:claude'); self.assertTrue(concierge.is_cli(s))
        seen = {}
        def fake_make(store_, name, model=None, cwd=None, trace=None, cancel=None, resume=None, keep=None, extra_args=None, user_settings=True):
            seen.update(name=name, model=model, cwd=cwd, resume=resume, keep=keep, extra=extra_args)
            def llm(system, user, max_tokens=0, images=None):
                seen['system'] = system; llm.session_id = 'sess-1'; return 'Dana wants the file - the draft is below.'
            llm.session_id = resume
            return llm
        t, m, r = drafted(s)
        with mock.patch.object(concierge.llm_mod, 'make_cli_llm', fake_make):
            out = concierge.surface(s)
            # the introduction is the FACTS and it is instant: the model's sentence (PW-153) put a
            # blocking call in front of every Next (the owner, 2026-09-07: "next still take 5 seconds?")
            self.assertEqual(out['say'], 'Next up: TQ-0001.')          # a few words: the card carries the rest (2026-10-21)
            self.assertEqual(seen, {}, 'the introduction asks no model at all, so there is no gear to pick')
            concierge.say(s, 'what did she attach?', key=f'review:{r}')                                 # a question: the model's
            self.assertEqual((seen['name'], seen['model'], seen['resume'], seen['cwd']), ('claude', 'sonnet@low', None, None))   # the Assistant default (haiku broke its contract, 2026-09-24) at low effort, tools off
            self.assertEqual(seen['extra'], ['--include-partial-messages'])     # its words drawn as they are written (agents.spoken)
            self.assertTrue(str(seen['keep']).startswith(f'{concierge.LIVE_KEY}:'))    # one live CLI process per chat (clipool)
            self.assertIn('I am Taskuary', seen['system'])
            concierge.say(s, 'and when did she send it?', key=f'review:{r}')                            # ...and the same conversation, resumed
            self.assertEqual((seen['name'], seen['model'], seen['resume'], seen['cwd']), ('claude', 'sonnet@low', 'sess-1', None))   # tools off
            self.assertNotIn('WHAT YOU CAN DO YOURSELF', seen['system'])                                # ...so it is not told it has any
            tid = general.dock_task(s)[0]['TaskId']
            self.assertEqual(concierge._sid(s, tid), 'sess-1')
            concierge.say(s, 'and who is she again?', key=f'review:{r}')
            self.assertEqual(seen['resume'], 'sess-1')                                                   # the next turn resumes it
            self.assertIsNone(seen['cwd'])                                                               # a typed ask too: tools off, the assistant runs nothing
            self.assertNotIn('WHAT YOU CAN DO YOURSELF', seen['system'])
            self.assertIn('A question gets a look-up first', seen['system'])       # COUNSEL.md's own words (PW-248/256); it said "I have no tools" until 2026-09-24
        s.set_setting('assistant_ai', 'connector:3', 't')
        self.assertTrue(concierge.is_cli(s))                                                            # the old dock's pick is not this page's
        s.set_setting(concierge.AI_KEY, 'connector:3', 't')
        self.assertFalse(concierge.is_cli(s))                                                           # the owner's choice HERE wins
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            c = TestClient(server.app)
            self.assertEqual(c.post('/api/concierge/ai', json={'pick': ''}).json()['pick'], 'cli:claude')   # back to the default
            self.assertEqual(c.get('/api/concierge').json()['model'], 'sonnet')

    def test_codex_gets_medium_effort_and_the_assistant_model_is_its_own_not_triages(self):
        s = store()
        s.upsert_agent('codex', 'coding', 'cli', '{"cmd": "codex"}')
        patcher = mock.patch('taskuary.agents.default_pick', return_value='cli:codex'); patcher.start(); self.addCleanup(patcher.stop)
        seen = {}
        def fake_make(store_, name, model=None, cwd=None, **kw):
            seen['model'] = model; seen['light'] = json.loads(store_.get_agent(name)['Config']).get('light_model')
            return lambda *a, **k: 'x'
        with mock.patch.object(concierge.llm_mod, 'make_cli_llm', fake_make):
            concierge.brain(s)
        self.assertEqual((seen['model'], seen['light']), (None, 'effort:medium'))
        self.assertIsNone(json.loads(s.get_agent('codex')['Config']).get('light_model'))                # never written back
        # the profile's light model is TRIAGE's - the Assistant keeps its own default over it
        s.upsert_agent('codex', 'coding', 'cli', '{"cmd": "codex", "light_model": "gpt-5-mini@low"}')
        with mock.patch.object(concierge.llm_mod, 'make_cli_llm', fake_make):
            concierge.brain(s)
        self.assertEqual((seen['model'], seen['light']), (None, 'effort:medium'))
        s.set_setting(concierge.MODEL_KEY, 'gpt-5.4', 'owner')                                              # ...and its own setting wins
        with mock.patch.object(concierge.llm_mod, 'make_cli_llm', fake_make):
            concierge.brain(s)
        self.assertEqual(seen['model'], 'gpt-5.4')

    def test_the_stream_carries_the_work_then_the_answer_and_a_report_can_be_rerun(self):
        s = store()
        m = s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'SourceName': 'GitHub Trending', 'Subject': 'GitHub Trending — FAILED',
                           'FromName': 'GitHub Trending', 'SentAt': ago(1), 'BodyText': 'rate limited', 'Status': 'feed'})
        sid = s.save_source({'Channel': 'report', 'Address': 'GitHub Trending', 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps({'type': 'digest', 'title': 'GitHub Trending'})}, 'o')
        it = funnel.build(s)['items'][0]
        self.assertEqual((it['kind'], it['source_id']), ('report', sid))
        def fake(system, user, **kw):
            kw.get('trace') and None
            return 'The trending report failed on a rate limit; I reran it - here it is.'
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(concierge, 'brain', lambda st, trace=None, cancel=None, resume=None, fast=False, keep=None: (trace and trace('tool_call', 'curl', {'args': {'command': 'curl /reports/1/rerun'}})) or fake):
            c = TestClient(server.app)
            with c.stream('POST', '/api/concierge/stream', json={'mode': 'next'}) as r:
                lines = [json.loads(l) for l in r.iter_lines() if l.strip()]
            # 'next' asks no model at all now, so there is no tool_call to stream ahead of it: the
            # introduction is the item's own facts, and it is instant (2026-09-07)
            # ...and the rail the press left behind follows the card as its own event (2026-10-20: the card first)
            self.assertEqual([l['type'] for l in lines], ['done', 'pile'])
            self.assertTrue(lines[0]['pile_follows']); self.assertNotIn('pile', lines[0]); self.assertIn('items', lines[1]['pile'])
            self.assertEqual(lines[0]['item']['key'], it['key'])
            self.assertEqual(lines[0]['say'], 'Next up: a report.')
            with c.stream('POST', '/api/concierge/stream', json={'mode': 'say', 'text': 'why did it fail?', 'key': it['key']}) as r:
                lines = [json.loads(l) for l in r.iter_lines() if l.strip()]
            self.assertEqual([l['type'] for l in lines], ['tool_call', 'done'])                          # a question: the model's turn streams
            self.assertIn('I reran it', lines[1]['say'])
            with mock.patch('taskuary.reports.run_report_source', return_value={'ran': True, 'message_id': m}) as ran:
                out = c.post(f'/api/reports/{sid}/rerun').json()
                import time; time.sleep(0.2)
            self.assertEqual((out['queued'], out['title']), (True, 'GitHub Trending')); self.assertTrue(ran.called)   # queued, run in the background
            self.assertEqual(c.post('/api/reports/999/rerun').status_code, 404)


class FyiWalkTests(unittest.TestCase):
    def test_a_batch_the_pile_already_assembled_is_never_its_own_member(self):
        """On a processing store next_item hands surface() the fyis card funnel_selection._batch built.
        Passed to fyi_batch as `first`, that card became member one of a new batch - "someone - 4 fyi"
        above three real rows, on the desktop and on WhatsApp (the owner, 2026-09-18)."""
        s = store()
        s.set_setting('team_domains', 'ours.com', 't')
        for n in range(3):
            m = s.add_message({'ExternalId': f'f{n}', 'ConversationId': f'c{n}', 'Channel': 'email', 'Subject': f'Note {n}', 'FromName': f'Person {n}',
                               'FromEmail': f'p{n}@ours.com', 'SentAt': ago(n), 'BodyText': f'FYI number {n}, done.', 'Status': 'filed'})
            s.add_route(m, None, 'file', None, 'triage: fyi - a colleague keeping you in the loop', [], 'triage')
        settle = lambda: (s.reconcile_processing_membership(fixed_now=ago(0)), funnel.invalidate())
        settle(); s.activate_processing_reads(fixed_now=ago(0), live_state=[]); settle()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            self.assertEqual(funnel.next_item(s)['kind'], 'fyis')                  # the chooser already batched
            out = concierge.surface(s, llm=lambda *a, **k: 'never')
        self.assertEqual(sorted(i['title'] for i in out['item']['items']), ['Note 0', 'Note 1', 'Note 2'])
        self.assertNotIn('fyi;', out['say']); self.assertNotIn('someone', out['say'])

    def test_fyis_come_four_at_a_time_and_a_mail_walk_still_stops_for_a_waiting_agent(self):
        s = store()
        s.set_setting('team_domains', 'ours.com', 't')
        for n in range(5):
            m = s.add_message({'ExternalId': f'f{n}', 'ConversationId': f'c{n}', 'Channel': 'email', 'Subject': f'Note {n}', 'FromName': f'Person {n}',
                               'FromEmail': f'p{n}@ours.com', 'SentAt': ago(n), 'BodyText': f'FYI number {n}, done.', 'Status': 'filed'})
            s.add_route(m, None, 'file', None, 'triage: fyi - a colleague keeping you in the loop', [], 'triage')
        self.assertEqual([i['lane'] for i in funnel.build(s)['items']], ['fyi'] * 5)
        with mock.patch.object(concierge, 'brain', return_value=None):
            out = concierge.surface(s)
        self.assertEqual((out['item']['kind'], out['item']['title'], out['left']), ('fyis', '4 fyi', 1))
        self.assertEqual(len(out['item']['items']), 4)
        self.assertEqual(out['say'], 'Next up: 4 FYIs.')
        self.assertEqual([i['title'] for i in funnel.build(s)['items']], ['Note 0'])
        with mock.patch.object(concierge, 'brain', return_value=None):
            two = concierge.surface(s)
        self.assertEqual((two['item']['kind'], two['item']['title'], two['left']), ('fyis', '1 fyi', 0))
        self.assertEqual(funnel.build(s)['items'], [])
        # a mail-only walk does not step over an agent waiting on you
        t = s.create_task({'Title': 'Pto', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        live = [{'taskId': t, 'agent': 'codex', 'label': 'codex', 'started': ago(0), 'idle': 120, 'waiting': True, 'tail': ['ok?']}]
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            self.assertEqual(funnel.next_item(s, only='mail')['kind'], 'agent')


class StaysOnSubjectTests(unittest.TestCase):
    def test_a_reply_about_another_task_is_replaced_by_the_facts_and_the_prompt_leads_with_the_item(self):
        s = store()
        t, m, r = drafted(s)
        seen = {}
        wander = lambda sy, u, **k: seen.update(u=u) or "Robin asked 13 hours ago to deploy gpt-4.1 (TQ-0312); I'd push it to the coding agent."
        out = concierge.surface(s, llm=wander)
        self.assertEqual(out['item']['rid'], r)
        self.assertEqual(out['say'], 'Next up: TQ-0001.')                                # the card's few words, not Robin
        self.assertTrue(seen['u'].startswith('THE ITEM ON THE TABLE - speak only about this one:'))
        self.assertNotIn('Coming next', seen['u'])                                       # no other items to wander to
        self.assertTrue(concierge.off_subject('TQ-0312 sat untouched', {'tid': 327}))
        self.assertFalse(concierge.off_subject('TQ-0327 is parked', {'tid': 327}))
        self.assertFalse(concierge.off_subject('no refs at all', {'tid': 327}))
        self.assertFalse(concierge.off_subject('TQ-0312', {'tid': None}))
        # no word-overlap half any more (the owner, 2026-10-11): an answer right in other words is not handed back
        self.assertFalse(concierge.off_subject('The export is stuck on her end - one reply unblocks it.', {'tid': 327, 'who': 'Dana', 'title': 'Export still broken'}))
        self.assertFalse(concierge.off_subject('Read it with the button.', {'tid': None, 'who': 'Morning digest', 'title': 'Morning digest'}))

    def test_an_answer_that_mentions_access_or_data_is_never_thrown_away(self):
        """A regex blanked any reply that "talked about its limits" - and blanked correct answers that said Erin needs access
        to the data room. The rule is the prompt's now (IN_PART), and the reply stands (the owner, 2026-10-11)."""
        s = store()
        t, m, r = drafted(s)
        right = "Erin can't access the data room until you approve her request - the draft says so."
        out = concierge.surface(s, llm=lambda sy, u, **k: right)
        self.assertEqual(out['say'], right)
        self.assertFalse(hasattr(concierge, 'in_character'))
        self.assertIn(concierge.IN_PART, concierge.CONTRACT); self.assertIn(concierge.IN_PART, concierge.PHONE_CONTRACT)


class TaskNowTests(unittest.TestCase):
    def test_the_facts_carry_the_task_as_it_is_now(self):
        s = store()
        t, m, r = drafted(s)
        s.add_comment(t, 'claude', 'agent', 'Looked at the export; the escaping is wrong on line 40.')
        it = funnel.build(s)['items'][0]
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            fx = concierge.facts(s, it)
        self.assertIn(f'TASK NOW: TQ-{t:04d} [waiting, coding] Export still broken - no agent on it right now', fx)
        self.assertIn(f"a reply waits for the owner's yes (rv{r})", fx); self.assertIn('the escaping is wrong on line 40', fx)
        s.decide_review(r, 'approved', 'Attached - sorry for the wait.', 'owner')
        self.assertIn('YOU ALREADY REPLIED', concierge.task_now(s, t)); self.assertIn('sorry for the wait', concierge.task_now(s, t))
        working = [{'taskId': t, 'agent': 'codex', 'label': 'codex', 'started': ago(0), 'idle': 3, 'waiting': False, 'tail': ['editing']}]
        with mock.patch('taskuary.terminal.live_sessions', return_value=working):
            self.assertIn('codex is WORKING right now', concierge.task_now(s, t))
        asking = [{'taskId': t, 'agent': 'codex', 'label': 'codex', 'started': ago(0), 'idle': 120, 'waiting': True, 'tail': ['Should I also fix the header? (y/n)']}]
        with mock.patch('taskuary.terminal.live_sessions', return_value=asking):           # the words on the tail ask nothing (2026-10-11)
            self.assertIn('codex is PARKED at its prompt', concierge.task_now(s, t))
        asking[0]['state'] = 'asking'                                                      # ...the session's own reading does
        with mock.patch('taskuary.terminal.live_sessions', return_value=asking):
            self.assertIn('codex is PARKED and ASKING you: Should I also fix the header?', concierge.task_now(s, t))
        s.update_task(t, {'Status': 'done'}, 'o')
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            self.assertIn('CLOSED', concierge.task_now(s, t))
        self.assertEqual(concierge.task_now(s, 999), '')


class ThreadTests(unittest.TestCase):
    def test_every_message_triage_combined_is_handed_to_the_assistant_in_one_item(self):
        s = store()
        t = s.create_task({'Title': 'Reorder the seven steps', 'Kind': 'general', 'Status': 'open'}, 'o')
        mids = []
        for n in range(7):
            mids.append(s.add_message({'TaskId': t, 'ExternalId': f'wa:{n}', 'ConversationId': 'wa:room',
                                       'Channel': 'whatsapp', 'Direction': 'in', 'Subject': 'Reorder the seven steps',
                                       'FromName': 'Tess', 'SentAt': ago(0), 'BodyText': f'combined message {n}',
                                       'Status': 'routed'}))
        # Supporting context belongs in reasoning about whether the owner answered, but it is not an
        # eighth triaged ask and must not inflate the grouped-message count.
        s.add_message({'TaskId': t, 'ExternalId': 'wa:mine', 'ConversationId': 'wa:room', 'Channel': 'whatsapp',
                       'Direction': 'in', 'Subject': 'Reorder the seven steps', 'FromName': 'You',
                       'SentAt': ago(0), 'BodyText': 'I will log it as a spec.', 'Status': 'context'})
        item = {'key': f'msg:{mids[-1]}', 'kind': 'asked', 'lane': 'asked', 'title': 'Reorder the seven steps',
                'who': 'Tess', 'when': ago(0), 'why': 'triage combined the ask', 'mid': mids[-1], 'tid': t}

        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            fx = concierge.facts(s, item)
        self.assertIn('TRIAGE COMBINED THESE 7 MESSAGES INTO THIS ONE TASK', fx)
        for n in range(7): self.assertIn(f'combined message {n}', fx)
        self.assertNotIn('TRIAGE COMBINED THESE 8 MESSAGES', fx)

    def test_the_owner_own_reply_on_the_thread_is_in_the_facts(self):
        """The newest message on a live thread is usually the owner's own answer, read back out of
        Sent - the facts used to drop it, and the assistant said it could not see the reply."""
        s = store()
        t, m, r = drafted(s)
        s.add_message({'TaskId': t, 'ExternalId': 'x:sent', 'ConversationId': 'c:Export still broken', 'Channel': 'email', 'Direction': 'out',
                       'Subject': 'RE: Export still broken', 'FromName': 'Alex', 'FromEmail': 'alex@ours.com', 'SentAt': ago(0),
                       'BodyText': 'Sent it over just now - let me know if it opens.', 'Status': 'filed'})
        it = funnel.build(s)['items'][0]
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            fx = concierge.facts(s, it)
        self.assertIn('YOU ALREADY ANSWERED ON THIS THREAD', fx)
        self.assertIn('let me know if it opens', fx)
        self.assertIn('YOU: Sent it over just now', fx)                     # the chain names the owner's own side
        self.assertIn('never say you cannot see', fx)

    def test_a_polite_request_is_a_hand_off_proposal_not_answered_with_the_mail_it_names(self):
        s = store()
        t, m, r = drafted(s)
        with phone(): out = concierge.say(s, 'can you ask assistant to look into that server and what the file looks like?', key=f'review:{r}',
                                          llm=lambda *a, **k: 'On it.\nCALL: {"kind": "coding_agent", "params": {"text": "look into that server and what the file looks like"}}')
        p = out['proposal']
        self.assertEqual((p['kind'], p['target'], p['params']['kind']), ('task.create_from_message', m, 'coding'))
        self.assertIn('server', p['params']['instructions'])
        self.assertIn('coding agent', out['say'].lower())
        self.assertIsNone(out.get('item'))                                  # not pulled in as "here is the mail you mean"


class FastLaneTests(unittest.TestCase):
    def test_introductions_take_the_fast_lane_and_typed_asks_the_full_cli(self):
        s = store()
        s.upsert_agent('coding', 'coding', 'cli', '{}')
        patcher = mock.patch('taskuary.agents.default_pick', return_value='cli:claude'); patcher.start(); self.addCleanup(patcher.stop)
        calls = []
        def fake_make(store_, name, model=None, cwd=None, trace=None, cancel=None, resume=None, keep=None, extra_args=None, user_settings=True):
            calls.append(cwd); f = lambda *a, **k: 'Dana wrote on email.'; f.session_id = ''; return f
        t, m, r = drafted(s)
        with mock.patch.object(concierge.llm_mod, 'make_cli_llm', fake_make):
            concierge.surface(s)                                             # an introduction: the facts, no model
            concierge.say(s, 'what did she attach?', key=f'review:{r}')       # a question: the model, tools off
            concierge.say(s, 'I think the export is the old one from June', key=f'review:{r}')   # a remark: the model, tools off
        self.assertEqual(calls, [None, None])                               # both typed turns: no cwd = read-only gear, no tools; the introduction asks nothing
        # an API connector configured is NOT a reason to swap the CLI out: which connector exists never decides the
        # voice (the owner, 2026-09-24: "first connected should not matter"); the chat's CLI stays live instead
        c = s.get_connector_by_type('openai')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Secret': 'k', 'Name': 'Fast', 'ConfigJson': '{"model": "gpt-fast"}'}, 'o')
        with mock.patch.object(concierge.llm_mod, 'make_cli_llm', fake_make), mock.patch.object(concierge.llm_mod, 'build_llm', return_value=lambda *a, **k: 'quick') as b:
            self.assertEqual(concierge.brain(s, fast=True)(None, None), 'Dana wrote on email.')
            self.assertFalse(b.called)
        self.assertEqual(concierge.pick(s), 'cli:claude')
        # ...but a CLI the owner CHOSE is not swapped for the connector: the Assistant set to Claude answered on
        # Azure every turn (2026-09-24). The set-up composer rides the same chosen brain.
        s.set_setting(concierge.AI_KEY, 'cli:claude', 'owner')
        calls.clear()
        with mock.patch.object(concierge.llm_mod, 'make_cli_llm', fake_make), mock.patch.object(concierge.llm_mod, 'build_llm', return_value=lambda *a, **k: 'quick') as b:
            self.assertEqual(concierge.brain(s, fast=True)(None, None), 'Dana wrote on email.')
            self.assertEqual(concierge._compose_llm(s)(None, None), 'Dana wrote on email.')
            self.assertFalse(b.called)
        self.assertEqual(calls, [None, None])                               # tools off either way


class ReplyClosesTests(unittest.TestCase):
    def test_a_reply_that_went_out_never_closes_the_task_agent_or_none(self):
        """It closed the task unless an agent still had it; the owner, 2026-10-18: "sending and closing are two steps"."""
        from taskuary import verdicts
        s = store()
        t, m, r = drafted(s)
        sent = {'channel': 'email', 'to': ['dana@vendor.com'], 'cc': []}
        with mock.patch('taskuary.outbound.reply_to_message', return_value=sent):
            out = verdicts.decide(s, s.get_review(r), 'approve', 'Attached.', None, 'owner')
        self.assertTrue(out['ok']); self.assertEqual(s.get_task(t)['Status'], 'waiting')
        self.assertFalse(any('Closed' in c['Body'] for c in s.list_comments(t)))
        t2, m2, r2 = drafted(s, 'second')
        live = [{'taskId': t2, 'agent': 'codex', 'label': 'codex', 'started': ago(0), 'idle': 2, 'waiting': False, 'tail': []}]
        with mock.patch('taskuary.outbound.reply_to_message', return_value=sent), mock.patch('taskuary.terminal.live_sessions', return_value=live):
            verdicts.decide(s, s.get_review(r2), 'approve', 'On it.', None, 'owner')
        self.assertEqual(s.get_task(t2)['Status'], 'waiting')


class SetupAndTroubleTests(unittest.TestCase):
    def test_set_up_opens_a_walk_through_and_starts_no_agent_in_a_checkout(self):
        """Asked to set up the Zoho invoice integration - a connector card and a report, both shipped -
        it used to open a CODING session, which went looking in the wrong repository (the owner,
        2026-09-03: "This was big mistake... it doesn't need coding agent just a regular agent that
        will walk me through it")."""
        s = store()
        with mock.patch('taskuary.ingest._spawn') as spawn:
            out = concierge.setup_task(s, 'set up a report that pulls last month\'s Zoho invoices every Monday')
        t = s.get_task(out['taskId'])
        self.assertEqual((t['Kind'], t['Status'], t['Source']), ('general', 'open', 'assistant'))
        # with no title named, the owner's sentence as said - a regex used to cut the verb off it (the owner, 2026-10-11)
        self.assertEqual(out['title'], "set up a report that pulls last month's Zoho invoices every Monday"); self.assertEqual(t['Title'][:6], 'Set up')
        self.assertIn('Zoho invoices', t['Summary'])
        self.assertEqual([i['text'] for i in s.task_checklist(out['taskId'])],
                         ["set up a report that pulls last month's Zoho invoices every Monday"])
        self.assertIn('needs:browser', t['Tags'])          # the walkthrough owns the visible browser, not a coding agent
        self.assertFalse(spawn.called)                       # nobody is sent into a checkout
        # said in the chat, a set-up is a PROPOSAL: the walk-through opens on the click, never on the words (here the
        # set-up sort says it needs digging - a form-shaped one would be a report proposal instead, test_chat_setup.py)
        n0 = len(s.list_tasks())
        digging = lambda system, user, **k: json.dumps({'kind': 'investigate', 'provider': None, 'why': 'a portal to read first'})
        with mock.patch.object(concierge, '_compose_llm', return_value=digging):
            said = decided(s, 'create a report of open AR by facility', 'setup', arg='create a report of open AR by facility')
        p = said['proposal']; self.assertEqual((p['kind'], p['label']), ('task.setup', 'Open the walk-through'))
        self.assertIsNone(said['decision']); self.assertEqual(len(s.list_tasks()), n0)
        with mock.patch('taskuary.ingest._spawn') as spawn:
            ran = run(s, p).json(); made = ran['outcome']
        self.assertEqual(s.get_task(made['taskId'])['Kind'], 'general'); self.assertFalse(spawn.called)
        self.assertIn('walk-through', ran['receipt']); self.assertIn('nothing built', ran['receipt'])
        # ...and a hand-off the owner asks for by name IS the coding agent, in a checkout
        with mock.patch('taskuary.ingest._spawn') as spawn:
            made = concierge.setup_task(s, 'find out why the export drops inter-company rows', kind='coding')
        self.assertEqual(s.get_task(made['taskId'])['Kind'], 'coding'); self.assertTrue(spawn.called)
        # the card's own road. The walk it opens is live now (server._walk_opens), so its session and
        # its sort are held still here - what they DO is tests/test_setup_walk.py's business.
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch('taskuary.ingest._spawn'), mock.patch.object(general, 'start_session'), \
             mock.patch.object(concierge, 'walk_is_external', return_value=False):
            c = TestClient(server.app)
            self.assertEqual(c.post('/api/concierge/setup', json={'text': 'build an alert when the PTO import fails'}).json()['ref'][:3], 'TQ-')
            self.assertEqual(c.post('/api/concierge/setup', json={'text': ' '}).status_code, 422)

    def test_why_is_it_failing_reads_the_failures_and_a_report_carries_its_last_runs(self):
        s = store()
        sid = s.save_source({'Channel': 'report', 'Address': 'GitHub Trending', 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps({'type': 'digest', 'title': 'GitHub Trending'})}, 'o')
        s.add_report_run(sid, {'at': ago(2), 'type': 'digest', 'title': 'GitHub Trending', 'ms': 10, 'failed': 1, 'error': 'claude exit 1: rate_limit_event five_hour'})
        m = s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'SourceName': 'GitHub Trending', 'Subject': 'GitHub Trending — FAILED',
                           'FromName': 'GitHub Trending', 'SentAt': ago(1), 'BodyText': 'Report error: claude exit 1', 'Status': 'feed'})
        it = funnel.build(s)['items'][0]
        fx = concierge.facts(s, it)
        self.assertIn('LAST RUNS:', fx); self.assertIn('FAILED: claude exit 1: rate_limit_event', fx)
        # what is failing is a tool the model calls (errors.list) - no longer injected when the words sound like trouble
        self.assertFalse(hasattr(concierge, 'trouble'))

    def test_the_no_model_line_points_at_the_page_that_fixes_it(self):
        """"No AI is connected - Connections → AI" named a tab, and the AI CLI agents page inside it
        had no door of its own. Now it has one, and this is the sentence somebody reads at the exact
        moment they need it."""
        said = concierge.fallback(None, False, pile_items=[{'key': 'k', 'lane': 'fyi', 'title': 't'}])
        self.assertIn('cli-agents', said)


class SweepTests(unittest.TestCase):
    def test_remove_all_the_reports_from_a_sender_is_a_proposal_that_sweeps_them_read_on_the_click(self):
        s = store()
        s.set_setting('team_domains', 'ours.com', 't')
        for n in range(3):
            m = s.add_message({'ExternalId': f'n{n}', 'ConversationId': f'n{n}', 'Channel': 'email', 'Subject': f'Northwind Financial Report - .0{n}', 'FromName': 'Paula Vance',
                               'FromEmail': 'pvance@ours.com', 'SentAt': ago(n), 'BodyText': 'attached', 'Status': 'filed'})
            s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        m = s.add_message({'ExternalId': 'k', 'ConversationId': 'k', 'Channel': 'email', 'Subject': 'RE: Payworth', 'FromName': 'Omar Keller',
                           'FromEmail': 'omar@vendor.example', 'SentAt': ago(1), 'BodyText': 'please respond', 'Status': 'filed'})
        s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        self.assertEqual(len(funnel.build(s)['items']), 4)
        out = cleared_by(s, "all the reports for paula vance you can remove. I don't need them", {'sender': 'Paula Vance'})
        p = out['proposal']; self.assertEqual((p['kind'], p['label']), ('pipe.clear', 'Mark 3 items read'))
        self.assertIn('Northwind Financial Report', p['summary'], 'the card names which ones before the yes')
        # ...and the line over the card says only what the card does not (the owner, 2026-10-12: "there should not be text and a card")
        self.assertNotIn('Northwind Financial Report', p['say_card']); self.assertNotIn(p['label'], p['say_card'])
        self.assertIn('nothing is deleted', p['say_card'])
        self.assertEqual(len(funnel.build(s)['items']), 4)                                       # nothing swept on the words
        ran = run(s, p).json(); o = ran['outcome']
        self.assertEqual(o['cleared'], 3)
        line = ran['receipt']
        self.assertIn('Marked 3 items read - ', line); self.assertIn('Read, not deleted', line)
        self.assertEqual((funnel.mutes(s), s.list_memories(active_only=True)), ([], []))   # clearing is all it does (R8)
        self.assertEqual([i['who'] for i in funnel.build(s)['items']], ['Omar Keller'])                # Omar stays
        again = cleared_by(s, 'same for all resident refunds', {'contains': 'resident refund'})
        self.assertIsNone(again.get('proposal')); self.assertIn('No items about resident refund are waiting, so there is nothing to clear', again['say'])
        al = funnel.alerts(s, funnel.build(s)['items'])
        self.assertEqual([(a['kind'], a['text']) for a in al], [('asked', 'Omar Keller asked you: RE: Payworth')] if any(i['lane'] == 'asked' for i in funnel.build(s)['items']) else [])


class SweepPronounTests(unittest.TestCase):
    def test_skip_all_the_x_sweeps_and_remove_them_resolves_against_what_was_said_before(self):
        """Two tries in the owner's own words, both of which used to be answered with a promise and no
        sweep (2026-09-03: "not removing the northwind financial reports in funnel?")."""
        s = store()
        s.set_setting('team_domains', 'ours.com', 't')
        for n in range(3):
            m = s.add_message({'ExternalId': f'r{n}', 'ConversationId': f'r{n}', 'Channel': 'email', 'Subject': f'Northwind Financial Report - .0{n} P&L',
                               'FromName': 'Paula Vance', 'FromEmail': 'pvance@vendor.example', 'SentAt': ago(n + 1), 'BodyText': 'generated by Intacct', 'Status': 'filed'})
            s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        keep = s.add_message({'ExternalId': 'k', 'ConversationId': 'k', 'Channel': 'email', 'Subject': 'RE: Payworth', 'FromName': 'Omar Keller',
                              'FromEmail': 'omar@vendor.example', 'SentAt': ago(1), 'BodyText': 'please respond', 'Status': 'filed'})
        s.add_route(keep, None, 'file', None, 'triage: fyi', [], 'triage')
        first = cleared_by(s, 'skip all the northwind financial reports. Those are part of the financials process, taken care of.',
                           {'contains': 'Northwind Financial Report'})
        self.assertEqual(first['proposal']['kind'], 'pipe.clear'); self.assertEqual(funnel.mutes(s), [])      # no rule on the words
        ran = run(s, first['proposal']).json()
        self.assertEqual(ran['outcome']['cleared'], 3)
        line = ran['receipt']
        self.assertIn('Marked 3 items read - ', line)
        self.assertEqual([i['who'] for i in funnel.build(s)['items']], ['Omar Keller'])


class ClosingTests(unittest.TestCase):
    """"close it" is a proposal like any other decision; the click runs the shared task.complete road and
    the receipt is the fact. It used to be the page's job, and a page that could not find the card did
    nothing while the chat had already said the task was closed (the owner, 2026-09-03: "I told the ai
    to close it but it did not")."""

    def _wrapped(self, s):
        t, m, r = drafted(s)
        s.decide_review(r, 'approved', 'Attached.', 'owner')          # the reply went out; the task stayed open
        return t, funnel.build(s)['items'][0]['key']

    def test_close_it_is_a_proposal_and_the_receipt_after_the_click_is_the_fact(self):
        s = store()
        t, key = self._wrapped(s)
        out = decided(s, 'close it', 'close', key=key)
        self.assertEqual((out['proposal']['kind'], out['proposal']['target']), ('task.complete', t))
        self.assertEqual(s.get_task(t)['Status'], 'waiting')                        # not closed on the words
        self.assertEqual(run(s, out['proposal']).json()['status'], 'done')
        self.assertEqual(s.get_task(t)['Status'], 'done')
        # no card of the item in this chat to wear the press (concierge._stamp_pressed), so its line is said
        self.assertIn(f'Done - Mark done · TQ-{t:04d}', last_receipt(s))
        self.assertEqual([i for i in funnel.build(s)['items'] if i.get('tid') == t], [])

    def test_a_close_made_outside_this_chat_says_nothing_in_it(self):
        """The owner closed TQ-0384 on the Tasks page and the chat opened itself to announce it (the
        owner, 2026-09-07: "no one asked you to do that"). Only what THIS chat proposed is its news."""
        from taskuary import operations
        s = store()
        t, _m, _r = drafted(s)
        p = operations.propose(s, 'task.complete', t, {}, 'owner')      # the Tasks page's own road: no chat turn
        self.assertEqual(run(s, p).json()['status'], 'done')
        self.assertEqual(s.get_task(t)['Status'], 'done')
        self.assertIsNone(s.get_settings().get('assistant_dock_task_id') or None, 'no chat was opened to say it in')
        self.assertEqual(last_receipt(s), '')

    def test_a_todo_with_a_task_behind_it_offers_mark_done(self):
        """A promise made in a chat is a to-do on your list; its card offered Send to agent, Remind me and Next, and Next
        read as done - the owner walked past two promises believing they were closed (2026-10-15)."""
        s = store()
        t = s.create_task({'Title': 'Run the tests', 'Kind': 'task', 'Status': 'open', 'Source': 'whatsapp'}, 'promise')
        verbs = lambda item: [c['verb'] for c in concierge.chips_for(s, item)]
        self.assertEqual(verbs({'key': 'k', 'kind': 'todo', 'lane': 'yours', 'tid': t, 'ref': f'TQ-{t:04d}'}),
                         ['close', 'regular_agent', 'defer', 'next'])
        self.assertNotIn('close', verbs({'key': 'k', 'kind': 'todo', 'lane': 'yours', 'mid': 5}))   # no task yet: nothing to mark done

    def test_closing_dismisses_a_draft_that_was_still_waiting(self):
        s = store()
        t, m, r = drafted(s)
        self.assertTrue(concierge.close_task(s, t, 'owner'))
        self.assertEqual(s.get_task(t)['Status'], 'done')
        self.assertIsNone(s.pending_review(t))                        # no reply left waiting on a closed task
        self.assertFalse(concierge.close_task(s, t, 'owner'))          # already closed

class OpeningTests(unittest.TestCase):
    def test_a_new_chat_opens_with_the_day_once_and_the_walk_starts_on_a_button(self):
        s = store()
        t, m, r = drafted(s)
        s.add_comment(t, 'claude', 'agent', 'AGENT REPORT\nSummary: regenerated the export; rows now match.')
        seen = {}
        fake = lambda system, user, **kw: seen.update(user=user) or "Let's go through what we have today: one reply waiting for your yes, nothing on the calendar."
        out = concierge.open_day(s, llm=fake)
        self.assertTrue(out['opened']); self.assertEqual(out['card']['kind'], 'brief'); self.assertEqual((out['card']['n'], out['card']['mail']), (1, 1))
        self.assertIn('THE DAY', seen['user']); self.assertIn('LEFT IN THE PIPE: 1', seen['user']); self.assertIn('AGENTS HAVE', seen['user'])
        self.assertFalse(concierge.open_day(s, llm=fake)['opened'])          # said once per chat
        self.assertEqual(funnel.build(s)['items'][0]['key'], f'review:{r}')  # nothing was surfaced by the opening
        # the walk: the agent's findings are said before the yes is asked
        nxt = concierge.surface(s, llm=lambda sy, u, **k: seen.update(walk=u) or 'The agent regenerated the export; the reply below says so - I would send it.', only='mail')
        self.assertEqual(nxt['item']['rid'], r); self.assertIn('THE AGENT FOUND: regenerated the export', seen['walk'])

    def test_the_opening_speaks_without_a_model(self):
        s = store(); drafted(s)
        with mock.patch.object(concierge, 'brain', return_value=None):
            out = concierge.open_day(s)
        self.assertTrue(out['say'].startswith("Let's go through what we have today. 1 thing waiting"))
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            c = TestClient(server.app)
            self.assertFalse(c.post('/api/concierge/open').json()['opened'])
            self.assertEqual(c.post('/api/concierge/next', json={'only': 'mail'}).json()['item']['kind'], 'review')


class AgentGotThereFirstTests(unittest.TestCase):
    def test_an_item_an_agent_now_holds_stays_a_task_in_its_place(self):
        s = store()
        t = s.create_task({'Title': 'Pto', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        m = s.add_message({'TaskId': t, 'ExternalId': 'x:pto', 'ConversationId': 'c:pto', 'Channel': 'email', 'Subject': 'PTO', 'FromName': 'Erin',
                           'FromEmail': 'c@ours.com', 'SentAt': ago(3), 'BodyText': 'Can you import PTO for Aug 9-22?', 'Status': 'routed'})
        t2, m2, r2 = drafted(s, 'second', hours=1)
        # one level for every task, oldest first: the in-progress todo (3h) is ahead of the draft (1h) - it was below it, in a
        # band of its own, while its status said an agent had it (the owner, 2026-10-21)
        todo, first = funnel.build(s)['items']
        self.assertEqual(first['key'], f'review:{r2}')
        self.assertEqual((todo['kind'], todo['coding']), ('todo', True))
        # codex starts on TQ-0001 between the pile being built and the pull
        live = [{'taskId': t, 'agent': 'codex', 'label': 'codex', 'started': ago(0), 'idle': 3, 'waiting': False, 'tail': []}]
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            out = concierge.surface(s, key=todo['key'], llm=lambda *a, **k: 'never')
        # PICKED BY NAME it goes on the table, agent and all - the owner wants to see it (2026-09-30: "task should pull up")
        self.assertEqual((out['item']['tid'], out['item']['lane']), (t, 'working'))
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            # a task, under the agent's key, in its place among the tasks - the older first (the owner, 2026-10-21)
            self.assertEqual([(i['key'], i['lane']) for i in funnel.build(s)['items']], [(f'agent:{t}', 'working'), (f'review:{r2}', 'approve')])
            self.assertEqual([funnel.level_of(i) for i in funnel.build(s)['items']], ['task', 'task'])
            self.assertEqual(funnel.next_item(s)['key'], f'review:{r2}')   # ...and NEXT from it, on the table, takes the next row


    def test_an_agent_that_is_asking_is_not_shown_as_working(self):
        """TQ-0887: codex finished its turn with a question; the task's message row, held as 'working' under the SAME agent:<tid>
        key, came first and won the dedup - the rail said "Agents working" over a pane waiting on the owner (2026-09-30)."""
        s = store()
        t = s.create_task({'Title': 'Pto', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        s.add_message({'TaskId': t, 'ExternalId': 'x:pto', 'ConversationId': 'c:pto', 'Channel': 'email', 'Subject': 'PTO', 'FromName': 'Erin',
                       'FromEmail': 'c@ours.com', 'SentAt': ago(3), 'BodyText': 'Can you import PTO for Aug 9-22?', 'Status': 'routed'})
        live = [{'taskId': t, 'agent': 'codex', 'label': 'codex', 'started': ago(1), 'idle': 600, 'waiting': True, 'sid': 's1',
                 'tail': ['Can you send the PTO file for Aug 9-22?']}]
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            rows = [(i['key'], i['kind'], i['lane']) for i in funnel.build(s)['items'] if i.get('tid') == t]
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0][1], 'agent')
        self.assertNotEqual(rows[0][2], 'working')


class ActTests(unittest.TestCase):
    def _idea(self):
        s = store()
        m = s.add_message({'ExternalId': 'x:q', 'ConversationId': 'c9', 'Channel': 'email', 'Subject': 'Q3 ledger', 'FromName': 'Erin Blake',
                           'FromEmail': 'erin@vendor.example', 'SentAt': ago(100), 'BodyText': 'Here is the ledger.', 'Status': 'filed'})
        i = s.upsert_idea({'key': 'followup:c9', 'kind': 'followup', 'text': 'No answer from Erin in 4 days - follow up?', 'sig': 'x',
                           'action': {'type': 'followup', 'mid': m, 'why': 'you asked on Monday'}}, ago(1))
        return s, i, funnel.build(s)['items'][0]['key']

    def test_done_and_later_go_to_the_pile_and_done_puts_the_idea_down(self):
        """I4 (2026-09-27): the rail's Done wrote only the rail's state, and the Advisor went on reading the idea as open."""
        s, i, key = self._idea()
        self.assertEqual(concierge.act(s, key, 'later', hours=1)['verb'], 'later')
        self.assertEqual(funnel.build(s)['items'], [])
        self.assertEqual(s.get_idea(i['IdeaId'])['Status'], 'open')             # Later is not a verdict on the idea
        s.set_funnel_state(key, 'surfaced')
        concierge.act(s, key, 'done')
        self.assertEqual(s.get_idea(i['IdeaId'])['Status'], 'done')
        for gone in ('followup', 'task', 'juggle'):
            with self.assertRaises(ValueError): concierge.act(s, key, gone)

    def test_not_ours_puts_the_idea_down_not_the_mail_it_was_about(self):
        s, i, key = self._idea()
        concierge.act(s, key, 'dismiss')
        self.assertEqual(s.get_idea(i['IdeaId'])['Status'], 'dismissed')
        self.assertEqual(funnel.build(s)['items'], [])

    def test_an_idea_offers_the_five_words_and_routes_them_to_the_idea(self):
        """C5: Make a task, Send to agent, Not ours, Remind me, Next - and Not ours is the idea's, never message.file."""
        s, i, key = self._idea()
        item = funnel.next_item(s, key)
        self.assertEqual([c['verb'] for c in concierge.chips_for(s, item)], ['mine', 'regular_agent', 'not_ours', 'defer', 'next'])
        prop = concierge.propose_direct(s, 'not_ours', key, table=True)
        self.assertEqual((prop['kind'], prop['target'], prop['params']), ('idea.act', i['IdeaId'], {'verb': 'dismiss'}))


class ApiTests(unittest.TestCase):
    def test_the_page_reads_the_pile_pulls_the_next_and_lists_its_chats(self):
        s = store()
        t, m, r = drafted(s)
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(concierge, 'brain', return_value=lambda *a, **k: 'Dana wants the file - the draft is below.'):
            c = TestClient(server.app)
            pile = c.get('/api/funnel/pile').json()
            self.assertEqual([i['key'] for i in pile['items']], [f'review:{r}'])
            # nine lanes now: 'broken' was added between approve and asked, so a failed check ranks
            # above a person's ask instead of behind every report (funnel.LANES)
            self.assertEqual([l['n'] for l in pile['lanes']], [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])   # fifteen since 'theirs' (2026-09-25)
            nxt = c.post('/api/concierge/next', json={}).json()
            self.assertEqual(nxt['item']['rid'], r)
            self.assertEqual(nxt['say'], 'Next up: TQ-0001.')      # instant, and the card carries the facts (2026-10-21)
            # The browser's walk resumes unresolved rows it already showed; a shown card is not read.
            resumed = c.post('/api/concierge/next', json={'include_surfaced': True}).json()
            self.assertEqual(resumed['item']['rid'], r)
            state = c.get('/api/concierge').json()
            self.assertEqual(state['messages'][0]['card']['kind'], 'review'); self.assertIn('providers', state)
            said = c.post('/api/concierge/say', json={'text': 'what did she attach?', 'key': nxt['item']['key']}).json()
            self.assertEqual(said['say'], 'Dana wants the file - the draft is below.')                  # a question: the (patched) model answers
            self.assertEqual(c.post('/api/funnel/settle', json={'key': nxt['item']['key'], 'verb': 'later'}).json()['verb'], 'later')
            # put away, it waits in For later on the rail (the canvas redesign, 2026-09-29) - never offered before its time
            self.assertEqual([(i['key'], i.get('deferred')) for i in c.get('/api/funnel/pile?force=1').json()['items']], [(nxt['item']['key'], True)])
            chats = c.get('/api/concierge/chats').json()['data']
            self.assertEqual(len(chats), 1); self.assertEqual(chats[0]['title'], 'what did she attach?'); self.assertTrue(chats[0]['open'])
            one = c.get(f"/api/concierge/chats/{chats[0]['taskId']}").json()
            self.assertEqual(len(one['messages']), 3)
            self.assertEqual(c.get('/api/concierge/chats/999').status_code, 404)
            self.assertEqual(c.post('/api/funnel/settle', json={'key': 'x', 'verb': 'burn'}).status_code, 422)

    def test_a_new_chat_archives_the_old_one_and_read_stays_read(self):
        s = store()
        t, m, r = drafted(s)
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(concierge, 'brain', return_value=lambda *a, **k: 'first look'):
            c = TestClient(server.app)
            c.post('/api/concierge/next', json={})
            self.assertTrue(c.get('/api/funnel/pile?force=1').json()['items'][0]['surfaced'])   # a reply for your yes stays, marked
            fresh = c.post('/api/assistant/dock/new').json()
            self.assertTrue(c.get('/api/funnel/pile?force=1').json()['items'][0]['surfaced'])   # ...and read stays read across chats
            chats = c.get('/api/concierge/chats').json()['data']
            self.assertEqual([x['open'] for x in chats], [True, False])
            self.assertEqual(chats[0]['taskId'], fresh['task']['TaskId'])
            self.assertEqual(c.get('/api/concierge').json()['messages'], [])


class WhenTests(unittest.TestCase):
    def test_the_day_has_no_leading_zero(self):
        self.assertEqual(concierge._when('2026-09-04 09:05:00'), 'Fri 4 Sep, 9:05am')
        self.assertEqual(concierge._when('2026-09-14 13:30:00'), 'Mon 14 Sep, 1:30pm')
        self.assertEqual(concierge._when('2026-09-06 00:00:00'), 'Sun 6 Sep, 12:00am')


if __name__ == '__main__':
    unittest.main()


class FyiHandOffTests(unittest.TestCase):
    """The owner, 2026-09-24: "Don't see button to send to agent or coding agent?" - a notification can be the
    start of a job ("make this job stop emailing me every time"), and the fyi card offered only filing it or
    the owner's own list."""
    def test_an_fyi_card_offers_both_agents_and_the_coding_one_proposes_from_the_message(self):
        s = store()
        s.upsert_agent('coding', 'coding', 'cli', '{}')
        mid = s.add_message({'ExternalId': 'n1', 'Channel': 'email', 'Subject': 'Nightly job - 0 created, 1 NOT created',
                             'FromName': 'Nightly job', 'FromEmail': 'jobs@northwind.example', 'SentAt': '2026-09-24 13:00:00',
                             'BodyText': 'NOT created (1): already exists', 'Status': 'filed'})
        item = {'kind': 'fyi', 'lane': 'fyi', 'mid': mid, 'key': f'msg:{mid}', 'title': 'Nightly job - 0 created, 1 NOT created'}
        with mock.patch.object(concierge, 'no_agent', return_value=''):
            verbs = [c['verb'] for c in concierge.chips_for(s, item)]
            # ONE button now, Send to agent (2026-09-25): the card's own question picks coding or not
            self.assertIn('regular_agent', verbs); self.assertNotIn('coding_agent', verbs)
            dock = general.dock_task(s, 'owner')[0]['TaskId']
            prop = concierge.propose_for(s, dock, {'verb': 'coding_agent', 'text': 'stop it emailing on every run'}, item,
                                         'send this to the coding agent')
        self.assertEqual((prop['kind'], prop['target']), ('task.create_from_message', mid))
        self.assertEqual(prop['params']['kind'], 'coding')
        self.assertEqual([(x['verb'], x['current']) for x in prop['alts']], [('coding_agent', True), ('regular_agent', False)])

    def test_send_to_agent_goes_where_triage_would_send_it(self):
        s = store()
        s.upsert_agent('coding', 'coding', 'cli', '{}')
        t = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 'o')
        self.assertEqual(concierge.triage_agent(s, {'tid': t}), 'coding_agent')
        s.update_task(t, {'Kind': 'general'}, 'o')
        self.assertEqual(concierge.triage_agent(s, {'tid': t}), 'regular_agent')


class NextBadge(unittest.TestCase):
    """NEXT READS A REPORT, IT PASSES A TASK (the owner, 2026-10-23: "should show read on reports if you go pass them when you hit next"):
    the card Next left wears "Read" where Next settled it read and "Next" where it stays yours - stamped here, so a reload draws it."""
    def test_the_badge_says_what_next_did(self):
        read, nxt = buttons.label('next', 'read'), buttons.label('next')
        self.assertEqual(read, 'Read')
        for c in ({'kind': 'report', 'lane': 'report'}, {'kind': 'report', 'lane': 'report', 'dashboard': True}, {'kind': 'report', 'lane': 'broken', 'bad': True},
                  {'kind': 'agentdone', 'lane': 'report', 'tid': 8}, {'kind': 'fyi', 'lane': 'fyi'}):
            self.assertEqual(concierge.next_badge(c), read, c)
        for c in ({'kind': 'task', 'lane': 'yours', 'tid': 7}, {'kind': 'review', 'lane': 'approve', 'tid': 3}, {'kind': 'meeting', 'lane': 'time'},
                  {'kind': 'connection', 'lane': 'broken'}, None):
            self.assertEqual(concierge.next_badge(c), nxt, c)
        self.assertEqual(concierge.next_badge({'kind': 'fyis', 'lane': 'fyi'}), buttons.label('next', 'batch'))

    def test_the_card_next_left_is_stamped_once_and_never_over_another_press(self):
        s = MemoryStore(); dock = general.dock_task(s)[0]['TaskId']
        cards = lambda: [json.loads(m.group(1)) for c in s.list_comments(dock) if (m := concierge._MARK.search(c.get('Body') or ''))]
        concierge.record(s, dock, 'assistant', 'Next up: a report.', {'key': 'report:4', 'kind': 'report', 'lane': 'report', 'title': 'Weekly spend'})
        concierge.record(s, dock, 'assistant', 'Next up: a task.', {'key': 'task:7', 'kind': 'task', 'lane': 'yours', 'tid': 7, 'title': 'Renew the lease',
                                                                    'pressed': buttons.label('close')})
        concierge.record(s, dock, 'assistant', 'Next up: a task.', {'key': 'task:8', 'kind': 'task', 'lane': 'yours', 'tid': 8, 'title': 'Quarter plan'})
        for k in ('report:4', 'task:7', 'task:8'): concierge._stamp_next(s, dock, k)
        self.assertEqual([c.get('pressed') for c in cards()], ['Read', buttons.label('close'), 'Next'])
        self.assertFalse(concierge._stamp_next(s, dock, 'report:99'))      # nothing drawn, nothing stamped


class ForLaterLine(unittest.TestCase):
    def test_the_line_counts_what_the_rail_holds_for_later_and_says_when_each_is_back(self):
        """The rail held two For later - one shown and put down for 2h, one put away until tomorrow with Remind me - and the
        line said "1 thing you've already seen" (the owner, 2026-10-01: "why does it say one thing when there are 2?")."""
        from unittest import mock
        soon, tomorrow = [(datetime.now() + timedelta(hours=h, minutes=5)).strftime('%Y-%m-%d %H:%M:%S') for h in (2, 19)]
        # For later is Remind me's since 2026-10-21 - a row Next walked past stays under Tasks (below)
        rows = [{'key': 'task:14', 'ref': 'TQ-0014', 'title': 'Compliance follow-up', 'lane': 'asked', 'deferred': True, 'back_at': soon},
                {'key': 'task:8', 'ref': 'TQ-0008', 'title': 'Raise approval', 'lane': 'asked', 'deferred': True, 'back_at': tomorrow}]
        s = MemoryStore()
        with mock.patch.object(concierge.funnel, 'pile', return_value={'items': rows}), \
             mock.patch.object(concierge.funnel, 'next_item', return_value=None):
            out = concierge.surface(s, llm=lambda *a, **k: 'never')
        # the desk says nothing - the Opens are the line (the owner, 2026-10-23: "yes remove the sentence, just the button") - and the
        # phone, which has no row, one short status
        self.assertEqual(out['say'], '')
        self.assertEqual([c.get('key') for c in out['chips']], [None, 'task:14', 'task:8'])
        with concierge.delivering(concierge.PHONE), mock.patch.object(concierge.funnel, 'pile', return_value={'items': rows}), \
             mock.patch.object(concierge.funnel, 'next_item', return_value=None):
            self.assertEqual(concierge.surface(s, llm=lambda *a, **k: 'never')['say'], "That's everything for now - 2 things are under For later.")
        rows[0] = rows[0] | {'deferred': False, 'surfaced': True, 'put_down': True}       # ...walked past with Next: still a task
        with mock.patch.object(concierge.funnel, 'pile', return_value={'items': rows}), \
             mock.patch.object(concierge.funnel, 'next_item', return_value=None):
            out = concierge.surface(s, llm=lambda *a, **k: 'never')
        self.assertEqual(out['say'], '')
        with concierge.delivering(concierge.PHONE), mock.patch.object(concierge.funnel, 'pile', return_value={'items': rows}), \
             mock.patch.object(concierge.funnel, 'next_item', return_value=None):
            self.assertEqual(concierge.surface(s, llm=lambda *a, **k: 'never')['say'], "That's everything for now - 2 things you already saw still wait on you.")

    def test_the_line_and_its_buttons_keep_the_rails_order(self):
        """A sort of the line's own named TQ-0001, TQ-0003, TQ-0004 over a rail reading TQ-0001, TQ-0002, TQ-0003 - a to-do is
        not on_you() - and the Open buttons followed the line, not the rail (the walk click-through, 2026-10-17)."""
        from unittest import mock
        soon = (datetime.now() + timedelta(hours=2, minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
        rows = [{'key': f'task:{n}', 'ref': f'TQ-000{n}', 'title': t, 'lane': lane, 'surfaced': True, 'put_down': True, 'back_at': soon}
                for n, t, lane in ((1, 'Month-end close', 'approve'), (2, 'New starter kit', 'yours'), (3, 'Overnight import', 'approve'))]
        with mock.patch.object(concierge.funnel, 'pile', return_value={'items': rows}),              mock.patch.object(concierge.funnel, 'next_item', return_value=None):
            out = concierge.surface(MemoryStore(), llm=lambda *a, **k: 'never')
        self.assertEqual(out['say'], '')                                     # the buttons name them, in the rail's order
        self.assertEqual([c.get('key') for c in out['chips']], [None, 'task:1', 'task:2', 'task:3'])

    def test_the_end_of_a_walk_offers_the_walk_again_as_a_button_not_a_sentence(self):
        """The end of a walk offered only Open TQ-... (the owner, 2026-10-22: "just have ... button on bottom on top of the prompt
        box"): the day card's own Walk me through my tasks leads the row, its words from buttons.json - and the line says no more.
        The phone has its own Walk, so its poll keeps only the Opens."""
        from unittest import mock
        rows = [{'key': 'task:4', 'ref': 'TQ-0004', 'title': 'Quarter plan', 'lane': 'yours', 'surfaced': True, 'put_down': True}]
        with mock.patch.object(concierge.funnel, 'pile', return_value={'items': rows}), mock.patch.object(concierge.funnel, 'next_item', return_value=None):
            out = concierge.surface(MemoryStore(), llm=lambda *a, **k: 'never')
            self.assertTrue(out['over'])
            self.assertEqual(out['chips'][0], {'verb': 'walk', 'label': 'Walk me through my tasks', 'hint': buttons.hint('walk')})
            self.assertEqual([c['verb'] for c in out['chips']], ['walk', 'open'])
            self.assertNotIn('Walk me through', out['say'])
            with concierge.delivering(concierge.PHONE):
                self.assertEqual([c['verb'] for c in concierge.surface(MemoryStore(), llm=lambda *a, **k: 'never')['chips']], ['open'])
        # ...and a walk that ends with nothing waiting offers no walk to start
        with mock.patch.object(concierge.funnel, 'pile', return_value={'items': []}), mock.patch.object(concierge.funnel, 'next_item', return_value=None):
            self.assertFalse(any(c.get('verb') == 'walk' for c in concierge.surface(MemoryStore(), llm=lambda *a, **k: 'never')['chips']))


class NonCoderWordsTests(unittest.TestCase):
    """The 2026-10-17 audit: every line and button the Assistant draws is one a non-coder can act on."""
    def test_a_failed_report_leads_with_run_it_again(self):
        """B7: the line said "run it again" over a card with no such button."""
        it = {'key': 'report:5', 'kind': 'report', 'title': 'Weekly AR', 'bad': True, 'source_id': 3, 'mid': 5, 'when': ago(1)}
        self.assertEqual(concierge.chips_for(MemoryStore(), it)[0]['verb'], 'rerun')
        self.assertIn('Run it again, or move on.', concierge.fallback(it, False, store=MemoryStore()))
        fine = {**it, 'bad': False}
        self.assertNotEqual(concierge.chips_for(MemoryStore(), fine)[0]['verb'], 'rerun')
        self.assertNotIn('make it a task', concierge.fallback(fine, False, store=MemoryStore()).lower())     # U11: read and passed

    def test_an_agent_asking_is_answered_in_its_pane_and_its_row_leads_with_stop_and_save(self):
        """U7 put "Answer it" first on an asking agent's card; the owner took the button away (2026-10-20: "we don't need that
        button") - the question is answered in the agent's own pane, and the live agent's row leads with Stop and save."""
        it = {'key': 'agent:7', 'kind': 'agent', 'lane': 'blocked', 'tid': 7, 'title': 'Totals', 'asking': True, 'agent': 'the assistant', 'tail': ['Which month?']}
        for item in (it, {**it, 'asking': False, 'request_kind': 'stalled'}, {**it, 'lane': 'working', 'asking': False}):
            chips = concierge.chips_for(None, item)
            self.assertNotIn('answer_agent', [c['verb'] for c in chips])
            self.assertEqual((chips[0]['verb'], chips[0]['label']), ('stop_agent', 'Stop and save'))
        # ...and its line still says where the answer goes: a typed answer in the box below reaches it (decide), a stopped one has nobody
        self.assertIn('answer it below', concierge.fallback(it, False))
        self.assertNotIn('answer it below', concierge.fallback({**it, 'lane': 'stopped'}, False))

    def test_the_waiting_count_says_goals_in_words_and_it_follows_the_count(self):
        """B14: "1 goal_slipped" and "them" over one thing."""
        self.assertEqual(concierge.waiting_line([{'kind': 'goal_slipped'}, {'kind': 'goal_fresh'}, {'kind': 'agent'}]),
                         '3 waiting: 1 goal that slipped, 1 goal not started yet, 1 agent question.')
        one = concierge.fallback(None, False, [{'kind': 'asked'}])
        self.assertIn("take you through it,", one)

    def test_no_ai_is_said_once_with_the_link_on_the_desk_and_in_words_on_the_phone(self):
        """U3: "set one up" twice in one reply, the second a raw "#cli-agents"."""
        desk = concierge.fallback(None, False, [{'kind': 'asked'}])
        self.assertEqual(desk.count('Connect an AI'), 1); self.assertIn('](#cli-agents)', desk)
        with concierge.delivering(concierge.PHONE):
            self.assertNotIn('#cli-agents', concierge.fallback(None, False, [{'kind': 'asked'}]))

    def test_the_line_names_only_buttons_the_item_has(self):
        """U2: "Prep me" over a meeting whose only button is Next; "continue it now" with no Continue."""
        meet = concierge.fallback({'key': 'meeting:1', 'kind': 'meeting', 'title': 'Budget review', 'why': 'at 2:00 PM'}, False)
        self.assertNotIn('Prep me', meet)
        goal = concierge.fallback({'key': 'goal:1', 'kind': 'goal_slipped', 'title': 'Close Q3', 'tid': 4, 'ref': 'TQ-0004'}, False)
        self.assertNotIn('Move the date', goal); self.assertIn('Mark done', goal)

    def test_a_finished_agent_line_ends_its_sentence_and_the_phone_is_not_sent_to_a_card(self):
        """B19: "...Updated the totals Its full report is on the card." - and a phone has no card."""
        it = {'key': 'done:1', 'kind': 'agentdone', 'title': 'Totals', 'ref': 'TQ-0001', 'who': 'Erin', 'summary': 'Updated the totals'}
        self.assertEqual(concierge.fallback(it, False), 'Erin finished TQ-0001: Updated the totals. Its full report is on the card.')
        with concierge.delivering(concierge.PHONE):
            self.assertTrue(concierge.fallback(it, False).endswith('Open it to read the full report.'))

    def test_remind_me_says_where_the_task_waits_now(self):
        """B8: "Upcoming in Tasks" was a tab that no longer exists."""
        said = concierge.away_line({'remindAt': '2026-10-20 08:00:00', 'when': 'Tuesday'})
        self.assertEqual(said, 'Away until Tuesday - it is under For later on your rail, and back in front of you that morning.')
        self.assertNotIn('Tasks', concierge.CHIP_HINTS['defer'])

    def test_nothing_drafted_offers_draft_with_ai(self):
        it = {'key': 'review:1', 'kind': 'review', 'rid': 1, 'mid': 2, 'tid': 3, 'title': 'Lease', 'draft': ''}
        self.assertIn('Draft with AI', [c['label'] for c in concierge.chips_for(None, it)])
        self.assertIn(buttons.label('redraft'), [c['label'] for c in concierge.chips_for(None, {**it, 'draft': 'Hi Gail'})])

    def test_with_no_coding_tool_a_coding_hand_off_is_send_to_agent(self):
        """B3: Coding agent was offered, then refused with "There is no coding agent on this computer"."""
        from taskuary import agents
        s = MemoryStore()
        with mock.patch.object(agents, 'coding_ready', return_value=False):
            self.assertEqual(concierge.handoff_verb(s, 'coding_agent'), 'regular_agent')
            self.assertNotIn('coding agent', concierge.tools_block(s).split('NEVER use')[0].replace('Never mention or offer a coding agent', ''))
        with mock.patch.object(agents, 'coding_ready', return_value=True):
            self.assertEqual(concierge.handoff_verb(s, 'coding_agent'), 'coding_agent')


class ClearTheFyiTests(unittest.TestCase):
    """F23: "clear all the FYI" right after the FYI batch was shown - the batch is read because it was shown, and the count must
    still hold it (concierge._pipe); the words were the selector's own ("kind: fyi") and "From Unknown Sender."."""
    def setUp(self):
        self.s = store()
        for n in range(4):
            self.s.add_message({'ExternalId': f'd{n}', 'ConversationId': f'd{n}', 'Channel': 'email', 'Subject': f'Weekly digest {n}',
                                'FromName': 'Unknown Sender' if n == 0 else 'Payworth', 'FromEmail': f'news{n}@vendor.example',
                                'SentAt': ago(n + 1), 'BodyText': 'Your weekly digest.', 'Status': 'filed'})
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            shown = concierge.surface(self.s, llm=lambda *a, **k: 'never')
        self.assertEqual(len((shown.get('item') or {}).get('items') or []), 4, 'the batch is on the table')

    def clear(self, where):
        call = 'CALL: ' + json.dumps({'kind': 'pipe.clear', 'params': {'select': {'kind': 'fyi'}}})
        tid = general.dock_task(self.s, 'owner')[0]['TaskId']
        with mock.patch.object(terminal, 'live_sessions', return_value=[]), concierge.delivering(where):
            return concierge.say(self.s, 'clear all the FYI', key=concierge.current_key(self.s, tid) or None, llm=lambda *a, **k: call)

    def test_the_desk_counts_the_batch_on_the_table(self):
        self.assertIn('Marked 4 FYI read.', self.clear(concierge.DESK)['say'])

    def test_the_phone_card_says_it_in_words(self):
        p = self.clear(concierge.PHONE)['proposal']
        self.assertEqual(p['label'], 'Mark 4 FYI read')
        self.assertNotIn('kind: fyi', p['say'])
        self.assertNotIn('Unknown Sender', concierge.pipe_holds(self.s))


class PhoneReceiptTests(unittest.TestCase):
    """F13: on the phone a receipt says what happened, in plain past tense, once - the desk keeps its own words."""
    def setUp(self):
        self.s = MemoryStore()
        self.t = self.s.create_task({'Title': 'Confirm Thursday', 'Kind': 'reply', 'Status': 'open'}, 'owner')
        mid = self.s.add_message({'TaskId': self.t, 'Channel': 'email', 'Subject': 'Thursday?', 'FromName': 'Gail Moreno',
                                  'FromEmail': 'gail@northwind.example', 'BodyText': 'Are we on?', 'Status': 'open'})
        self.rid = self.s.add_review({'TaskId': self.t, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Yes.'})

    def line(self, op, where=concierge.PHONE):
        with concierge.delivering(where): return concierge.receipt_turn(self.s, op)['say']

    def test_a_send_names_who_it_went_to(self):
        op = {'kind': 'review.approve', 'targetKind': 'review', 'target': self.rid, 'status': 'done',
              'outcome': {'sent': {'to': ['gail@northwind.example']}}}
        self.assertEqual(self.line(op), f'Sent to Gail Moreno · TQ-{self.t:04d}.')
        self.assertTrue(self.line(op, concierge.DESK).startswith('Done - '), 'the desk keeps its receipt')

    def test_a_close_is_the_task_closed(self):
        op = {'kind': 'task.complete', 'targetKind': 'task', 'target': self.t, 'status': 'done', 'outcome': {}}
        self.assertEqual(self.line(op), f'TQ-{self.t:04d} closed.')

    def test_an_error_is_one_clean_sentence(self):
        for err in ('unknown agent: ', 'the bridge failed.'):
            said = self.line({'kind': 'task.complete', 'targetKind': 'task', 'target': self.t, 'status': 'error', 'error': err})
            self.assertNotIn(': .', said); self.assertNotIn('..', said)


class SettleBadge(unittest.TestCase):
    """A CARD'S OWN WAY ON KEEPS ITS BADGE (the owner, 2026-10-24: "If we hit next let's show that as well on the task on the canvas"):
    "All read, next" on an fyi batch walks on by the settle road, not Next's, and its badge was drawn on the page and gone on reload."""
    def test_the_press_a_settle_carries_is_stamped_on_its_card_and_only_a_buttons_word(self):
        s = MemoryStore(); dock = general.dock_task(s)[0]['TaskId']
        cards = lambda: {(d := json.loads(m.group(1)))['key']: d.get('pressed') for c in s.list_comments(dock)
                         if (m := concierge._MARK.search(c.get('Body') or ''))}
        for k in ('fyis:msg:1,msg:2', 'fyis:msg:3'):
            concierge.record(s, dock, 'assistant', '', {'key': k, 'kind': 'fyis', 'lane': 'fyi', 'title': '2 fyi'})
        with mock.patch.object(server, 'store', s), mock.patch.object(funnel, 'settle', return_value={}),              mock.patch.object(server, '_pile_along', return_value=None):
            c = TestClient(server.app)
            self.assertEqual(c.post('/api/funnel/settle', json={'key': 'fyis:msg:1,msg:2', 'pressed': buttons.label('next', 'batch')}).status_code, 200)
            c.post('/api/funnel/settle', json={'key': 'fyis:msg:3', 'pressed': 'Anything I like'})
        self.assertEqual(cards(), {'fyis:msg:1,msg:2': 'All read, next', 'fyis:msg:3': None})

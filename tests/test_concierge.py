"""Taskuary, the assistant you talk to (concierge.py): one item out of the pipe per turn, said by a
light model or by the facts when there is none; the conversation lives on the dock task with the
card recorded beside each line; a new chat walks the pipe afresh. The model is a lambda throughout."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, funnel, general, server, terminal
from taskuary.store import MemoryStore


def ago(hours=0): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    s = MemoryStore()
    # an install has a coding agent - config.toml seeds it at boot. Without one the assistant now
    # says so instead of receipting a hand-off the dispatch would 422 on (2026-09-03).
    s.upsert_agent('coder', 'coding', 'cli', '{}')
    for k in ('calendar_enabled', 'coder_auto_enabled', 'learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._CACHE.update(cands_at=0.0, cands=[])
    return s


def _verb(d):
    """(verb, text) - the two fields a caller acts on; the rest is the guard's working-out."""
    return (None if d is None else (d.get('verb'), d.get('text')))


def drafted(s, subject='Export still broken', who='Dana', hours=5, draft='Attached.'):
    t = s.create_task({'Title': subject, 'Kind': 'coding', 'Status': 'waiting'}, 'o')
    m = s.add_message({'TaskId': t, 'ExternalId': f'x:{subject}', 'ConversationId': f'c:{subject}', 'Channel': 'email', 'Subject': subject, 'FromName': who,
                       'FromEmail': 'dana@vendor.com', 'SentAt': ago(hours), 'BodyText': 'Can you send the corrected file?', 'Status': 'routed'})
    r = s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': draft, 'Status': 'pending'})
    return t, m, r


class TurnTests(unittest.TestCase):
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
        self.assertIn('I am Taskuary', seen['system']); self.assertIn('ONE item per turn', seen['system'])   # COUNSEL.md, then the contract
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

    def test_a_deep_dive_is_dispatched_to_a_regular_agent_instead_of_merely_offered(self):
        s = store()
        session = mock.Mock()
        with mock.patch.object(concierge.general, 'start_session', return_value=session), \
             mock.patch.object(concierge.threading, 'Thread') as thread:
            out = concierge.say(s, 'can you do a deep dive on the ECC agent harness?')
        task = s.get_task(out['decision']['taskId'])
        self.assertEqual((task['Kind'], task['SourceRef']), ('general', 'assistant:agent'))
        self.assertIn('deep dive', task['Summary'])
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()
        self.assertIn('regular agent now', out['say'])

    def test_okay_send_it_accepts_the_regular_work_offer_and_keeps_the_prior_brief(self):
        s = store()
        dock, _ = general.dock_task(s)
        concierge.record(s, dock['TaskId'], 'user', 'back to GitHub: do a deep dive on the ECC harness')
        concierge.record(s, dock['TaskId'], 'assistant', 'I can dig into the ECC harness. That is reading and analysis work, not a code change.')
        session = mock.Mock()
        with mock.patch.object(concierge.general, 'start_session', return_value=session), \
             mock.patch.object(concierge.threading, 'Thread') as thread:
            out = concierge.say(s, 'okay send it')
        task = s.get_task(out['decision']['taskId'])
        self.assertIn('ECC harness', task['Summary'])
        self.assertNotEqual(task['Title'].lower(), 'okay send it')
        self.assertEqual(task['SourceRef'], 'assistant:agent')
        thread.return_value.start.assert_called_once()

    def test_without_a_model_the_facts_speak(self):
        s = store()
        t, m, r = drafted(s)
        with mock.patch.object(concierge, 'brain', return_value=None):
            out = concierge.surface(s)
        self.assertIn('Dana wrote on email', out['say']); self.assertIn('"Export still broken"', out['say'])
        self.assertIn('Since then: triage judged it a reply to write', out['say']); self.assertIn('From you: approve the draft below', out['say'])
        self.assertEqual(out['options'], [])

    def test_a_model_that_fails_still_leaves_a_line(self):
        s = store(); drafted(s)
        def boom(*a, **k): raise RuntimeError('quota')
        out = concierge.surface(s, llm=boom)
        self.assertIn('Dana wrote on email', out['say'])

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
        concierge.surface(s, llm=lambda *a, **k: 'first')
        again = concierge.surface(s, llm=lambda *a, **k: 'never')
        self.assertIsNone(again['item']); self.assertEqual(again['say'], "1 unread thing still waits. Say next and I'll take them one at a time.")
        s.add_message({'ExternalId': 'r9', 'Channel': 'report', 'SourceName': 'Nightly', 'Subject': 'Nightly report', 'FromName': 'Nightly', 'SentAt': ago(1), 'BodyText': '5 rows', 'Status': 'feed'})
        mail_out = concierge.surface(s, llm=lambda *a, **k: 'never', only='mail')
        self.assertIsNone(mail_out['item']); self.assertEqual(mail_out['exhausted'], 'mail'); self.assertIn("That's all the mail. 2 other things still wait", mail_out['say'])
        gone = concierge.surface(s, key='msg:999', llm=lambda *a, **k: 'never')
        self.assertIsNone(gone['item']); self.assertIn("can't find that one", gone['say'])

    def test_words_that_name_a_thing_pull_it_into_the_chat(self):
        s = store()
        t, m, r = drafted(s)                                            # Dana, "Export still broken"
        s.add_message({'ExternalId': 'x:lee', 'Channel': 'teams', 'Subject': 'Teams chat with Lee', 'FromName': 'Lee Park', 'FromEmail': 'lee@ours.com',
                       'SentAt': ago(1), 'BodyText': 'lunch?', 'Status': 'filed'})
        self.assertEqual(concierge.lookup(s, 'what did Dana send about the export?'), f'review:{r}')
        self.assertEqual(concierge.lookup(s, 'show me the Lee chat'), 'msg:2')
        self.assertIsNone(concierge.lookup(s, 'thanks, next'))
        self.assertEqual(concierge.lookup(s, f'what about TQ-{t:04d}?'), f'task:{t}')          # a task by its reference
        self.assertIsNone(concierge.lookup(s, 'what about TQ-0999?'))
        old = s.create_task({'Title': 'Rename the flag', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        s.add_comment(old, 'claude', 'agent', 'CODER REPORT\nSummary: renamed it in three places.')
        pulled = concierge.surface(s, key=f'task:{old}', llm=lambda *a, **k: 'That one is renamed in three places.')
        self.assertEqual((pulled['item']['kind'], pulled['item']['tid']), ('task', old)); self.assertIn('renamed it', pulled['item']['summary'])
        self.assertIsNone(concierge.lookup(s, 'what about the invoice from Marcus'))
        concierge.surface(s, llm=lambda *a, **k: 'first')               # Dana's is on the table
        out = concierge.say(s, 'what did Lee say?', key=f'review:{r}', llm=lambda *a, **k: 'Lee asked about lunch.')
        self.assertEqual(out['item']['title'], 'Teams chat with Lee'); self.assertEqual(out['say'], 'Lee asked about lunch.')
        roles = [(h['role'], bool(h['card'])) for h in concierge.history(s, general.dock_task(s)[0]['TaskId'])]
        self.assertEqual(roles[-3:], [('assistant', True), ('user', False), ('assistant', True)])

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
        s = store()
        payload = {'earned': True,
                   'why_earned': 'We compared three recurring failure patterns and worked through the operating tradeoffs.',
                   'topic': 'customer-launch', 'kind': 'new_idea',
                   'title': 'Make launch dry-runs reversible by default',
                   'body': 'A reversible dry-run exposes ownership gaps before dates are promised.'}
        seen = {}
        def fake(system, user, **kw):
            seen['system'], seen['user'] = system, user
            return 'I put the developed idea in the Hub.\n<TASKUARY-HUB>' + json.dumps(payload) + '</TASKUARY-HUB>'
        out = concierge.say(s, 'Put that launch idea in the Hub', llm=fake)
        self.assertEqual(out['say'], 'I put the developed idea in the Hub.')
        self.assertIn('company Hub', seen['system'])
        self.assertNotIn('TASKUARY-HUB', concierge.history(s, general.dock_task(s)[0]['TaskId'])[-1]['text'])
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
    def test_the_owners_words_about_the_item_are_a_decision_the_model_names_and_the_page_carries_out(self):
        s = store()
        t, m, r = drafted(s)
        concierge.surface(s, llm=lambda *a, **k: 'Dana wants the file.')
        fake = lambda sy, u, **k: "Not ours, then - I'll file it and move on.\nDECIDE: not_ours"
        never = lambda sy, u, **k: (_ for _ in ()).throw(AssertionError('a clear decision must not call the model'))
        out = concierge.say(s, "it's not my issue, let them sort it out", key=f'review:{r}', llm=never)
        self.assertEqual(_verb(out['decision']), ('not_ours', ''))
        self.assertEqual(out['say'], 'Not ours, then - filed. Moving on.')            # the receipt, instantly, no model
        out = concierge.say(s, 'tell her the file is with the coder, Friday', key=f'review:{r}', llm=never)
        self.assertEqual(_verb(out['decision']), ('reply', 'the file is with the coder, Friday'))   # the words ride into the draft
        told = lambda sy, u, **k: "I'll draft that.\nDECIDE: reply: mention the Friday delivery"
        out = concierge.say(s, 'can you mention the Friday delivery in the response', key=f'review:{r}', llm=told)
        self.assertEqual(out['decision'], {'verb': 'reply', 'text': 'mention the Friday delivery'})   # a softer phrasing: the model names it
        # a remark is not a decision
        out = concierge.say(s, 'who is Dana again?', key=f'review:{r}', llm=lambda *a, **k: 'Dana is the vendor contact on the export.')
        self.assertIsNone(out['decision'])
        # ...and nothing on the table means nothing to decide - the words move the WALK instead,
        # which is what "next" and "done" typed into an empty table always meant (2026-09-03)
        out = concierge.say(s, 'done', key=None, llm=lambda *a, **k: 'Nothing is on the table.\nDECIDE: done')
        self.assertIsNone(out.get('decision'))
        self.assertIn('still wait', out['say'])

    def test_plain_phrases_decide_without_a_model(self):
        # decide_words also hands back what was SAID and what is left of it once every verb phrase is
        # taken out - the subject guard reads that, so the shape is checked by field, not by equality
        self.assertEqual(_verb(concierge.decide_words("it's not my issue so let them respond if they still need it")), ('not_ours', ''))
        self.assertEqual(_verb(concierge.decide_words('reply: we are on it, expect the file Friday')), ('reply', 'we are on it, expect the file Friday'))
        self.assertEqual(concierge.decide_words('tell them the import runs tonight')['verb'], 'reply')
        self.assertEqual(concierge.decide_words('send it to the coding agent')['verb'], 'coder')
        self.assertEqual(_verb(concierge.decide_words('coding agent')), ('coder', ''))
        self.assertEqual(_verb(concierge.decide_words('regular agent')), ('regular_agent', ''))
        self.assertEqual(concierge.decide_words('send to agent')['verb'], 'agent_choice')
        self.assertEqual(concierge.decide_words('send to codex to review')['verb'], 'coder')
        self.assertEqual(concierge.decide_words('rerun please')['verb'], 'rerun')
        self.assertEqual(concierge.decide_words('approve')['verb'], 'approve')
        self.assertEqual(concierge.decide_words('looks good, send it')['verb'], 'approve')
        self.assertEqual(concierge.decide_words('this sender is garbage, never again')['verb'], 'not_ours_sender')
        self.assertEqual(concierge.decide_words('remember that Marcus owns the AP cutover'), {'verb': 'remember', 'text': 'Marcus owns the AP cutover'})
        self.assertEqual(concierge.decide_words('remember that this sender is junk')['verb'], 'not_ours_sender')
        self.assertEqual(concierge.decide_words('can you run it again')['verb'], 'rerun')
        self.assertEqual(concierge.decide_words('claude should look at this')['verb'], 'coder')
        coder = concierge.decide_words("send it to the coding agent and figure out why this wasn't updated - we did this before")
        self.assertEqual(coder['text'], "send it to the coding agent and figure out why this wasn't updated - we did this before")   # every word rides along
        self.assertEqual(concierge.parse_decision('On it.\nDECIDE: coder: find out why the fix did not stick, and add an admin login')[1],
                         {'verb': 'coder', 'text': 'find out why the fix did not stick, and add an admin login'})
        self.assertEqual(concierge.decide_words("I'll do it myself")['verb'], 'mine')
        self.assertEqual(concierge.decide_words('I will do this just make it a task')['verb'], 'mine')
        # a decision is receipted, not narrated: the model's claim gives way to the plain fact of what happens now
        s2 = store(); t2, m2, r2 = drafted(s2)
        concierge.surface(s2, llm=lambda *a, **k: 'Dana wants the file.')
        out = concierge.say(s2, 'I will do this just make it a task', key=f'review:{r2}', llm=lambda *a, **k: 'Task created - all set!')
        self.assertEqual((out['decision']['verb'], out['say']), ('mine', 'On your list. Moving on.'))
        self.assertIn('NEVER use your own task, todo or plan tools', concierge.tools_block(s2))
        self.assertEqual(concierge.decide_words('later')['verb'], 'later')
        self.assertEqual(concierge.decide_words('just close task')['verb'], 'close')
        self.assertEqual(concierge.decide_words('I did it next')['verb'], 'done')
        self.assertEqual(concierge.decide_words('ok that one is fine, next')['verb'], 'next')
        self.assertIsNone(concierge.decide_words('did you respond yet on this, it was responded to?'))   # a question is a question
        self.assertEqual(concierge.decide_words('it was responded to already')['verb'], 'done')
        self.assertEqual(concierge.decide_words('next')['verb'], 'next')
        self.assertIsNone(concierge.decide_words('what did she attach?'))
        s = store(); t, m, r = drafted(s)
        concierge.surface(s, llm=lambda *a, **k: 'Dana wants the file.')
        with mock.patch.object(concierge, 'brain', return_value=None):
            out = concierge.say(s, 'not mine, ignore it', key=f'review:{r}')
        self.assertEqual(out['decision']['verb'], 'not_ours'); self.assertIn('filed', out['say'])
        out = concierge.say(s, 'send to agent', key=f'review:{r}', llm=lambda *a, **k: 'must not be asked')
        self.assertIsNone(out['decision'])
        self.assertEqual(out['options'], ['Coding agent', 'Regular agent'])
        self.assertIn('Nothing has been started', out['say'])
        self.assertEqual(concierge.parse_decision('Sure.\nDECIDE: bogus'), ('Sure.', None))


class BrainTests(unittest.TestCase):
    def test_the_cli_is_the_default_brain_on_its_light_gear_and_picks_its_conversation_back_up(self):
        s = store()
        s.upsert_agent('coder', 'coding', 'cli', '{"cmd": "claude", "model": "opus"}')
        patcher = mock.patch('taskuary.agents.default_agent', return_value='coder'); patcher.start(); self.addCleanup(patcher.stop)   # whatever this machine has installed
        self.assertEqual(concierge.pick(s), 'cli:coder'); self.assertTrue(concierge.is_cli(s))
        seen = {}
        def fake_make(store_, name, model=None, cwd=None, trace=None, cancel=None, resume=None):
            seen.update(name=name, model=model, cwd=cwd, resume=resume)
            def llm(system, user, max_tokens=0, images=None):
                seen['system'] = system; llm.session_id = 'sess-1'; return 'Dana wants the file - the draft is below.'
            llm.session_id = resume
            return llm
        t, m, r = drafted(s)
        with mock.patch.object(concierge.llm_mod, 'make_cli_llm', fake_make):
            out = concierge.surface(s)
            self.assertIn('Dana wrote on email', out['say']); self.assertEqual(seen, {})                 # 'next' is the facts: no model call at all
            concierge.say(s, 'what did she attach?', key=f'review:{r}')                                 # a question: the model, on its quick gear
            self.assertEqual((seen['name'], seen['model'], seen['resume'], seen['cwd']), ('coder', 'haiku', None, None))   # tools off
            self.assertNotIn('WHAT YOU CAN DO YOURSELF', seen['system'])                                # ...so it is not told it has any
            tid = general.dock_task(s)[0]['TaskId']
            self.assertEqual(concierge._sid(s, tid), 'sess-1')
            concierge.say(s, 'and who is she again?', key=f'review:{r}')
            self.assertEqual(seen['resume'], 'sess-1')                                                   # the next turn resumes it
            self.assertIsNone(seen['cwd'])                                                               # a typed ask too: tools off, the assistant runs nothing
            self.assertNotIn('WHAT YOU CAN DO YOURSELF', seen['system']); self.assertIn('You have NO tools and run nothing yourself', seen['system'])
        s.set_setting('assistant_ai', 'connector:3', 't')
        self.assertTrue(concierge.is_cli(s))                                                            # the old dock's pick is not this page's
        s.set_setting(concierge.AI_KEY, 'connector:3', 't')
        self.assertFalse(concierge.is_cli(s))                                                           # the owner's choice HERE wins
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            c = TestClient(server.app)
            self.assertEqual(c.post('/api/concierge/ai', json={'pick': ''}).json()['pick'], 'cli:coder')   # back to the default
            self.assertEqual(c.get('/api/concierge').json()['model'], 'haiku')

    def test_codex_gets_low_effort_and_a_profile_light_model_is_respected(self):
        s = store()
        s.upsert_agent('codex', 'coding', 'cli', '{"cmd": "codex"}')
        patcher = mock.patch('taskuary.agents.default_agent', return_value='codex'); patcher.start(); self.addCleanup(patcher.stop)
        seen = {}
        def fake_make(store_, name, model=None, cwd=None, **kw):
            seen['model'] = model; seen['light'] = json.loads(store_.get_agent(name)['Config']).get('light_model')
            return lambda *a, **k: 'x'
        with mock.patch.object(concierge.llm_mod, 'make_cli_llm', fake_make):
            concierge.brain(s)
        self.assertEqual((seen['model'], seen['light']), (None, 'effort:low'))
        self.assertIsNone(json.loads(s.get_agent('codex')['Config']).get('light_model'))                # never written back
        s.upsert_agent('codex', 'coding', 'cli', '{"cmd": "codex", "light_model": "gpt-5-mini@low"}')
        with mock.patch.object(concierge.llm_mod, 'make_cli_llm', fake_make):
            concierge.brain(s)
        self.assertEqual((seen['model'], seen['light']), (None, 'gpt-5-mini@low'))

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
             mock.patch.object(concierge, 'brain', lambda st, trace=None, cancel=None, resume=None, fast=False: (trace and trace('tool_call', 'curl', {'args': {'command': 'curl /reports/1/rerun'}})) or fake):
            c = TestClient(server.app)
            with c.stream('POST', '/api/concierge/stream', json={'mode': 'next'}) as r:
                lines = [json.loads(l) for l in r.iter_lines() if l.strip()]
            self.assertEqual([l['type'] for l in lines], ['done'])                                       # 'next' asks no model: one event, the item
            self.assertEqual(lines[0]['item']['key'], it['key']); self.assertIn('landed', lines[0]['say'])
            with c.stream('POST', '/api/concierge/stream', json={'mode': 'say', 'text': 'why did it fail?', 'key': it['key']}) as r:
                lines = [json.loads(l) for l in r.iter_lines() if l.strip()]
            self.assertEqual([l['type'] for l in lines], ['tool_call', 'done'])                          # a question: the model's turn streams
            self.assertIn('I reran it', lines[1]['say'])
            with mock.patch('taskuary.server.run_report_source', return_value={'ran': True, 'message_id': m}) as ran:
                out = c.post(f'/api/reports/{sid}/rerun').json()
                import time; time.sleep(0.2)
            self.assertEqual((out['queued'], out['title']), (True, 'GitHub Trending')); self.assertTrue(ran.called)   # queued, run in the background
            self.assertEqual(c.post('/api/reports/999/rerun').status_code, 404)


class FyiWalkTests(unittest.TestCase):
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
        self.assertIn('4 things people told you', out['say'])
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
        wander = lambda sy, u, **k: seen.update(u=u) or "Mindy asked 13 hours ago to deploy gpt-4.1 (TQ-0312); I'd push it to the coder."
        out = concierge.surface(s, llm=wander)
        self.assertEqual(out['item']['rid'], r)
        self.assertIn('Dana wrote on email', out['say']); self.assertNotIn('Mindy', out['say'])   # the facts, not Mindy
        self.assertTrue(seen['u'].startswith('THE ITEM ON THE TABLE - speak only about this one:'))
        self.assertNotIn('Coming next', seen['u'])                                       # no other items to wander to
        self.assertTrue(concierge.off_subject('TQ-0312 sat untouched', {'tid': 327}))
        self.assertFalse(concierge.off_subject('TQ-0327 is parked', {'tid': 327}))
        self.assertFalse(concierge.off_subject('no refs at all', {'tid': 327}))
        self.assertFalse(concierge.off_subject('TQ-0312', {'tid': None}))
        digest = {'tid': None, 'who': 'Morning digest', 'title': 'Morning digest — yesterday and today so far, distilled'}
        self.assertTrue(concierge.off_subject('Ayush pushed a commit this morning on the WebSocket PR that fixes the flake.', digest))
        self.assertFalse(concierge.off_subject('The Morning digest landed at 8:08 - read it with the button.', digest))
        self.assertFalse(concierge.off_subject('Dana wrote asking for the export.', {'tid': None, 'who': 'Dana', 'title': 'Export still broken'}))


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
                                       'FromName': 'Gabi', 'SentAt': ago(0), 'BodyText': f'combined message {n}',
                                       'Status': 'routed'}))
        # Supporting context belongs in reasoning about whether the owner answered, but it is not an
        # eighth triaged ask and must not inflate the grouped-message count.
        s.add_message({'TaskId': t, 'ExternalId': 'wa:mine', 'ConversationId': 'wa:room', 'Channel': 'whatsapp',
                       'Direction': 'in', 'Subject': 'Reorder the seven steps', 'FromName': 'You',
                       'SentAt': ago(0), 'BodyText': 'I will log it as a spec.', 'Status': 'context'})
        item = {'key': f'msg:{mids[-1]}', 'kind': 'asked', 'lane': 'asked', 'title': 'Reorder the seven steps',
                'who': 'Gabi', 'when': ago(0), 'why': 'triage combined the ask', 'mid': mids[-1], 'tid': t}

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
                       'Subject': 'RE: Export still broken', 'FromName': 'Uri', 'FromEmail': 'uri@ours.com', 'SentAt': ago(0),
                       'BodyText': 'Sent it over just now - let me know if it opens.', 'Status': 'filed'})
        it = funnel.build(s)['items'][0]
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            fx = concierge.facts(s, it)
        self.assertIn('YOU ALREADY ANSWERED ON THIS THREAD', fx)
        self.assertIn('let me know if it opens', fx)
        self.assertIn('YOU: Sent it over just now', fx)                     # the chain names the owner's own side
        self.assertIn('never say you cannot see', fx)

    def test_a_polite_request_is_carried_out_not_answered_with_the_mail_it_names(self):
        s = store()
        t, m, r = drafted(s)
        out = concierge.say(s, 'can you ask assistant to look into that server and what the file looks like?',
                            key=f'review:{r}', llm=lambda *a, **k: 'never asked')
        self.assertEqual(out['decision']['verb'], 'coder')
        self.assertIn('coding agent', out['say'])
        self.assertIsNone(out.get('item'))                                  # not pulled in as "here is the mail you mean"


class FastLaneTests(unittest.TestCase):
    def test_introductions_take_the_fast_lane_and_typed_asks_the_full_cli(self):
        s = store()
        s.upsert_agent('coder', 'coding', 'cli', '{"cmd": "claude"}')
        patcher = mock.patch('taskuary.agents.default_agent', return_value='coder'); patcher.start(); self.addCleanup(patcher.stop)
        calls = []
        def fake_make(store_, name, model=None, cwd=None, trace=None, cancel=None, resume=None):
            calls.append(cwd); f = lambda *a, **k: 'Dana wrote on email.'; f.session_id = ''; return f
        t, m, r = drafted(s)
        with mock.patch.object(concierge.llm_mod, 'make_cli_llm', fake_make):
            concierge.surface(s)                                             # an introduction: the facts, no model
            concierge.say(s, 'what did she attach?', key=f'review:{r}')       # a question: the model, tools off
            concierge.say(s, 'I think the export is the old one from June', key=f'review:{r}')   # a remark: the model, tools off
        self.assertEqual(calls, [None, None])                                # both model turns: no cwd = read-only gear, no tools
        # with an API connector configured, the fast lane is that connector - a second, not a launch
        c = s.get_connector_by_type('openai')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Secret': 'k', 'Name': 'Fast', 'ConfigJson': '{"model": "gpt-fast"}'}, 'o')
        with mock.patch.object(concierge.llm_mod, 'make_cli_llm', fake_make), mock.patch.object(concierge.llm_mod, 'build_llm', return_value=lambda *a, **k: 'quick') as b:
            self.assertEqual(concierge.brain(s, fast=True)(None, None), 'quick')
            self.assertTrue(b.called)
        self.assertEqual(concierge.pick(s), 'cli:coder')                     # the default voice is still the CLI


class ReplyClosesTests(unittest.TestCase):
    def test_a_reply_that_went_out_closes_the_task_unless_an_agent_still_has_it(self):
        from taskuary import verdicts
        s = store()
        t, m, r = drafted(s)
        sent = {'channel': 'email', 'to': ['dana@vendor.com'], 'cc': []}
        with mock.patch('taskuary.outbound.reply_to_message', return_value=sent):
            out = verdicts.decide(s, s.get_review(r), 'approve', 'Attached.', None, 'owner')
        self.assertTrue(out['ok']); self.assertEqual(s.get_task(t)['Status'], 'done')
        self.assertTrue(any('Closed - the reply went out' in c['Body'] for c in s.list_comments(t)))
        t2, m2, r2 = drafted(s, 'second')
        live = [{'taskId': t2, 'agent': 'codex', 'label': 'codex', 'started': ago(0), 'idle': 2, 'waiting': False, 'tail': []}]
        with mock.patch('taskuary.outbound.reply_to_message', return_value=sent), mock.patch('taskuary.terminal.live_sessions', return_value=live):
            verdicts.decide(s, s.get_review(r2), 'approve', 'On it.', None, 'owner')
        self.assertEqual(s.get_task(t2)['Status'], 'waiting')                # the agent's close-out comes first


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
        self.assertEqual(out['title'], "report that pulls last month's Zoho invoices every Monday"); self.assertEqual(t['Title'][:6], 'Report')
        self.assertIn('Zoho invoices', t['Summary'])
        self.assertIn('needs:browser', t['Tags'])          # the walkthrough owns the visible browser, not a coder
        self.assertFalse(spawn.called)                       # nobody is sent into a checkout
        self.assertEqual(concierge.decide_words('please set up a connection to Sage Intacct')['verb'], 'setup')
        self.assertEqual(concierge.decide_words('set up a monthly invoice workflow in Zoho')['verb'], 'setup')
        self.assertIsNone(concierge.decide_words('set it aside'))
        with mock.patch('taskuary.ingest._spawn') as spawn:
            said = concierge.say(s, 'create a report of open AR by facility', key=None, llm=lambda *a, **k: 'never')
        self.assertEqual(said['decision']['verb'], 'walkthrough')
        self.assertIn('walk you through it', said['say']); self.assertIn('no repository is touched', said['say'])
        self.assertEqual(s.get_task(said['decision']['taskId'])['Kind'], 'general')
        self.assertFalse(spawn.called)
        # ...and a hand-off the owner asks for by name IS the coder, in a checkout
        with mock.patch('taskuary.ingest._spawn') as spawn:
            made = concierge.setup_task(s, 'find out why the export drops inter-company rows', kind='coding')
        self.assertEqual(s.get_task(made['taskId'])['Kind'], 'coding'); self.assertTrue(spawn.called)
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch('taskuary.ingest._spawn'):
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
        self.assertEqual(concierge.trouble(s, 'what did she attach?'), '')
        block = concierge.trouble(s, 'why is my github report not working?')
        self.assertIn('WHAT IS FAILING RIGHT NOW', block); self.assertIn('Report failed: GitHub Trending', block)


class SweepTests(unittest.TestCase):
    def test_remove_all_the_reports_from_a_sender_sweeps_them_read_and_remembers_when_asked(self):
        s = store()
        s.set_setting('team_domains', 'ours.com', 't')
        for n in range(3):
            m = s.add_message({'ExternalId': f'n{n}', 'ConversationId': f'n{n}', 'Channel': 'email', 'Subject': f'MFA Financial Report - .0{n}', 'FromName': 'Nechama Ozur',
                               'FromEmail': 'nozur@ours.com', 'SentAt': ago(n), 'BodyText': 'attached', 'Status': 'filed'})
            s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        m = s.add_message({'ExternalId': 'k', 'ConversationId': 'k', 'Channel': 'email', 'Subject': 'RE: PointClickCare', 'FromName': 'Kishan Patel',
                           'FromEmail': 'kishan@vendor.com', 'SentAt': ago(1), 'BodyText': 'please respond', 'Status': 'filed'})
        s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        self.assertEqual(len(funnel.build(s)['items']), 4)
        out = concierge.say(s, "all the reports for nechama ozur you can remove. I don't need them", key=None, llm=lambda *a, **k: 'never')
        self.assertEqual(out['decision']['verb'], 'clear'); self.assertEqual(out['decision']['cleared']['cleared'], 3); self.assertTrue(out['decision']['cleared']['remember'])
        self.assertIn('Cleared 3 from the pipe', out['say']); self.assertIn('Read, not deleted', out['say']); self.assertIn('remembered', out['say'])
        self.assertEqual([i['who'] for i in funnel.build(s)['items']], ['Kishan Patel'])                # Kishan stays
        again = concierge.say(s, 'same for all resident refunds', key=None, llm=lambda *a, **k: 'never')
        self.assertEqual(again['decision']['cleared']['cleared'], 0); self.assertIn('Nothing in the pipe matches', again['say'])
        # a polite request is an ORDER, question mark and all (the owner, 2026-09-03: "it should be being brought in on a task")
        self.assertEqual(concierge.decide_words('can you look into that server and what the file looks like?')['verb'], 'coder')
        self.assertEqual(concierge.decide_words('can you ask assistant to look into that server?')['verb'], 'coder')
        self.assertEqual(concierge.decide_words('look into that server and tell me what the file looks like')['verb'], 'coder')
        self.assertEqual(concierge.decide_words('I responded. do you see the response?'), None)          # a real question stays a question
        self.assertEqual(concierge.decide_words('what did Kishan send?'), None)
        al = funnel.alerts(s, funnel.build(s)['items'])
        self.assertEqual([(a['kind'], a['text']) for a in al], [('asked', 'Kishan Patel asked you: RE: PointClickCare')] if any(i['lane'] == 'asked' for i in funnel.build(s)['items']) else [])


class SweepPronounTests(unittest.TestCase):
    def test_skip_all_the_x_sweeps_and_remove_them_resolves_against_what_was_said_before(self):
        """Two tries in the owner's own words, both of which used to be answered with a promise and no
        sweep (2026-09-03: "not removing the mfa financial reports in funnel?")."""
        s = store()
        s.set_setting('team_domains', 'ours.com', 't')
        for n in range(3):
            m = s.add_message({'ExternalId': f'r{n}', 'ConversationId': f'r{n}', 'Channel': 'email', 'Subject': f'MFA Financial Report - .0{n} P&L',
                               'FromName': 'Nechama Ozur', 'FromEmail': 'nozur@hrtgcs.com', 'SentAt': ago(n + 1), 'BodyText': 'generated by Intacct', 'Status': 'filed'})
            s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        keep = s.add_message({'ExternalId': 'k', 'ConversationId': 'k', 'Channel': 'email', 'Subject': 'RE: PointClickCare', 'FromName': 'Kishan Patel',
                              'FromEmail': 'kishan@vendor.com', 'SentAt': ago(1), 'BodyText': 'please respond', 'Status': 'filed'})
        s.add_route(keep, None, 'file', None, 'triage: fyi', [], 'triage')
        first = concierge.say(s, 'skip all the mfa financial reports. Those are part of the financials process, taken care of.',
                              key=None, llm=lambda *a, **k: 'never')
        self.assertEqual(first['decision']['verb'], 'clear'); self.assertEqual(first['decision']['cleared']['cleared'], 3)
        self.assertIn('Cleared 3 from the pipe', first['say'])
        self.assertIn('remembered as a rule: financial mfa from nozur@hrtgcs.com', first['say'])
        self.assertIn('still reaches you', first['say'])
        notes = [n['Note'] for n in s.list_memories(active_only=True)]                       # the reason is kept, in the owner's words
        self.assertTrue(any('financials process' in n for n in notes), notes)
        self.assertEqual([m['Scope'] for m in s.list_memories(active_only=True)], ['sender'])
        self.assertEqual([i['who'] for i in funnel.build(s)['items']], ['Kishan Patel'])
        # ...and the rule it left behind is what keeps the NEXT batch out - a sweep alone only marked
        # the ones in front of them read (the owner, 2026-09-03: "was it one time dismiss not a memory")
        self.assertEqual([(r['sender'], 'mfa' in r['words']) for r in funnel.mutes(s)], [('nozur@hrtgcs.com', True)])
        for n in range(3, 5):
            m = s.add_message({'ExternalId': f'r{n}', 'ConversationId': f'r{n}', 'Channel': 'email', 'Subject': f'MFA Financial Report - .0{n} Banks',
                               'FromName': 'Nechama Ozur', 'FromEmail': 'nozur@hrtgcs.com', 'SentAt': ago(1), 'BodyText': 'generated by Intacct', 'Status': 'filed'})
            s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        funnel.invalidate()
        p = funnel.build(s)
        self.assertEqual([i['who'] for i in p['items']], ['Kishan Patel'])
        self.assertEqual(p['muted'], 2)                       # held back, not deleted: they are on the Timeline
        # ...and a real ask from that same sender still reaches them
        t = s.create_task({'Title': 'Re-run .02', 'Kind': 'coding', 'Status': 'waiting'}, 'o')
        s.add_message({'TaskId': t, 'ExternalId': 'ask', 'ConversationId': 'ask', 'Channel': 'email', 'FromName': 'Nechama Ozur',
                       'Subject': 'MFA Financial Report - can you re-run .02?', 'FromEmail': 'nozur@hrtgcs.com', 'SentAt': ago(0),
                       'BodyText': 'please re-run it', 'Status': 'routed'})
        funnel.invalidate()
        asked = [(i['title'], i['lane']) for i in funnel.build(s)['items'] if i.get('tid') == t]
        self.assertEqual(asked, [('MFA Financial Report - can you re-run .02?', 'asked')])


class ClosingTests(unittest.TestCase):
    """"close it" is the one verb Taskuary honours itself. It used to be the page's job, and a page
    that could not find the card did nothing while the chat had already said the task was closed
    (the owner, 2026-09-03: "I told the ai to close it but it did not")."""

    def _wrapped(self, s):
        t, m, r = drafted(s)
        s.decide_review(r, 'approved', 'Attached.', 'owner')          # the reply went out; the task stayed open
        return t, funnel.build(s)['items'][0]['key']

    def test_close_it_closes_the_task_and_the_receipt_is_the_fact(self):
        s = store()
        t, key = self._wrapped(s)
        out = concierge.say(s, 'close it', key=key, llm=lambda *a, **k: 'never asked')
        self.assertEqual(s.get_task(t)['Status'], 'done')
        self.assertEqual(out['decision'], {'verb': 'closed', 'taskId': t, 'ref': f'TQ-{t:04d}'})
        self.assertIn(f'TQ-{t:04d} closed', out['say'])
        self.assertEqual([i for i in funnel.build(s)['items'] if i.get('tid') == t], [])

    def test_closing_dismisses_a_draft_that_was_still_waiting(self):
        s = store()
        t, m, r = drafted(s)
        self.assertTrue(concierge.close_task(s, t, 'owner'))
        self.assertEqual(s.get_task(t)['Status'], 'done')
        self.assertIsNone(s.pending_review(t))                        # no reply left waiting on a closed task
        self.assertFalse(concierge.close_task(s, t, 'owner'))          # already closed

    def test_being_told_a_fact_is_wrong_is_never_answered_by_moving_on(self):
        s = store()
        t, m, r = drafted(s)
        key = f'review:{r}'
        # the model itself said "move on" - which is the one answer a correction may not get
        out = concierge.say(s, "that's not a fail, it says all clear?", key=key,
                            llm=lambda *a, **k: 'Fair enough - the run says all clear.\nDECIDE: next')
        self.assertIsNone(out['decision'])
        self.assertNotEqual(out['say'].strip(), 'Next.')
        self.assertIn('all clear', out['say'])


class TwoRulesInOneSentenceTests(unittest.TestCase):
    """The owner's own words, with a card open - which is where it broke twice: the sweep only ran when
    nothing was on the table, so the chat said "Cleared. Moving on." and swept nothing; and one rule
    carrying both senders' words would have muted whichever came first (2026-09-03)."""

    ASK = ("next. Can you make rules to not surface mfa financials reports from Nechama and resident "
           "refunds stuff from elisheva. Don't need to see them")

    def _pile(self, s):
        s.set_setting('team_domains', 'ours.com', 't')
        for n in range(3):
            m = s.add_message({'ExternalId': f'n{n}', 'ConversationId': f'n{n}', 'Channel': 'email', 'FromName': 'Nechama Ozur',
                               'Subject': f'MFA Financial Report - .{n}0 P&L', 'FromEmail': 'nozur@hrtgcs.com', 'SentAt': ago(n + 1),
                               'BodyText': 'from Intacct', 'Status': 'filed'})
            s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        for n in range(2):
            m = s.add_message({'ExternalId': f'e{n}', 'ConversationId': f'e{n}', 'Channel': 'email', 'FromName': 'Elisheva M',
                               'Subject': f'RE: Resident Refund Request - Case {n}', 'FromEmail': 'elisheva@mfaheritage.net',
                               'SentAt': ago(n + 1), 'BodyText': 'approved', 'Status': 'filed'})
            s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        keep = s.add_message({'ExternalId': 'k', 'ConversationId': 'k', 'Channel': 'email', 'FromName': 'Kishan Patel',
                              'Subject': 'RE: PointClickCare', 'FromEmail': 'kishan@vendor.com', 'SentAt': ago(1),
                              'BodyText': 'please respond', 'Status': 'filed'})
        s.add_route(keep, None, 'file', None, 'triage: fyi', [], 'triage')

    def test_it_clears_the_ones_here_and_remembers_one_rule_per_sender(self):
        s = store()
        self._pile(s)
        on_the_table = funnel.build(s)['items'][0]['key']          # a card IS open, as it was for the owner
        out = concierge.say(s, self.ASK, key=on_the_table, llm=lambda *a, **k: 'never asked')
        self.assertEqual(out['decision']['verb'], 'clear')
        self.assertEqual(out['decision']['cleared']['cleared'], 5)          # the ones in front of them, now
        self.assertIn('remembered as 2 rules', out['say'])
        self.assertEqual([(r['sender'], sorted(r['words'])) for r in funnel.mutes(s)],
                         [('nozur@hrtgcs.com', ['financials', 'mfa', 'nechama']),
                          ('elisheva@mfaheritage.net', ['refunds', 'resident'])])
        self.assertEqual([i['who'] for i in funnel.build(s)['items']], ['Kishan Patel'])
        # ...and the next batch of both never enters, from either sender
        for n in (9, 10):
            m = s.add_message({'ExternalId': f'n{n}', 'ConversationId': f'n{n}', 'Channel': 'email', 'FromName': 'Nechama Ozur',
                               'Subject': f'MFA Financial Report - .{n}0 Banks', 'FromEmail': 'nozur@hrtgcs.com', 'SentAt': ago(0),
                               'BodyText': 'from Intacct', 'Status': 'filed'})
            s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        m = s.add_message({'ExternalId': 'e9', 'ConversationId': 'e9', 'Channel': 'email', 'FromName': 'Elisheva M',
                           'Subject': 'RE: Resident Refund Request - Case 9', 'FromEmail': 'elisheva@mfaheritage.net',
                           'SentAt': ago(0), 'BodyText': 'approved', 'Status': 'filed'})
        s.add_route(m, None, 'file', None, 'triage: fyi', [], 'triage')
        funnel.invalidate()
        p = funnel.build(s)
        self.assertEqual([i['who'] for i in p['items']], ['Kishan Patel'])
        self.assertEqual(p['muted'], 3)
        # ...and a rule never becomes "everything from that person": the sender's own words are dropped
        self.assertNotIn('nozur', sum([r['words'] for r in funnel.mutes(s)], []))
        # ...nor a second, broader verdict on the sender - the rule is the whole mechanism
        self.assertFalse(out['decision']['cleared']['remember'] and not out['decision']['cleared']['rules'])


class OpeningTests(unittest.TestCase):
    def test_a_new_chat_opens_with_the_day_once_and_the_walk_starts_on_a_button(self):
        s = store()
        t, m, r = drafted(s)
        s.add_comment(t, 'claude', 'agent', 'CODER REPORT\nSummary: regenerated the export; rows now match.')
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
    def test_an_item_an_agent_now_holds_is_put_back_with_a_word_and_the_walk_moves_on(self):
        s = store()
        t = s.create_task({'Title': 'Pto', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        m = s.add_message({'TaskId': t, 'ExternalId': 'x:pto', 'ConversationId': 'c:pto', 'Channel': 'email', 'Subject': 'PTO', 'FromName': 'Chana',
                           'FromEmail': 'c@ours.com', 'SentAt': ago(3), 'BodyText': 'Can you import PTO for Aug 9-22?', 'Status': 'routed'})
        t2, m2, r2 = drafted(s, 'second', hours=1)
        first = funnel.build(s)['items'][0]
        self.assertEqual(first['key'], f'review:{r2}')                    # the draft outranks the todo
        todo = funnel.build(s)['items'][1]
        self.assertEqual((todo['kind'], todo['coding']), ('todo', True))
        # codex starts on TQ-0001 between the pile being built and the pull
        live = [{'taskId': t, 'agent': 'codex', 'label': 'codex', 'started': ago(0), 'idle': 3, 'waiting': False, 'tail': []}]
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            out = concierge.surface(s, key=todo['key'], llm=lambda *a, **k: 'never')
        self.assertIsNone(out['item']); self.assertIn("is with codex right now - nothing for you until it stops or asks", out['say'])
        with mock.patch('taskuary.terminal.live_sessions', return_value=live):
            self.assertEqual([(i['key'], i['lane']) for i in funnel.build(s)['items']], [(f'review:{r2}', 'approve'), (f'agent:{t}', 'working')])   # in hand, at the top, under the agent's key
            self.assertEqual(funnel.next_item(s)['key'], f'review:{r2}')


class ActTests(unittest.TestCase):
    def test_done_and_later_go_to_the_pile_and_a_follow_up_drafts_the_chase(self):
        s = store()
        m = s.add_message({'ExternalId': 'x:q', 'ConversationId': 'c9', 'Channel': 'email', 'Subject': 'Q3 ledger', 'FromName': 'Dana',
                           'FromEmail': 'dana@vendor.com', 'SentAt': ago(100), 'BodyText': 'Here is the ledger.', 'Status': 'filed'})
        s.upsert_idea({'key': 'followup:c9', 'kind': 'followup', 'text': 'No answer from Dana in 4 days - follow up?', 'sig': 'x',
                       'action': {'type': 'followup', 'mid': m, 'why': 'you asked on Monday'}}, ago(1))
        key = funnel.build(s)['items'][0]['key']
        self.assertEqual(concierge.act(s, key, 'later', hours=1)['verb'], 'later')
        self.assertEqual(funnel.build(s)['items'], [])
        s.set_funnel_state(key, 'surfaced')                       # back on the table
        with mock.patch('taskuary.responder.write_draft'):
            out = concierge.act(s, key, 'followup')
        self.assertIn('reviewId', out)
        self.assertEqual(s.get_review(out['reviewId'])['Status'], 'pending')
        # the line itself is done - and the chase it drafted is now the thing waiting for a yes
        self.assertEqual([(i['lane'], i['kind']) for i in funnel.build(s)['items']], [('approve', 'review')])
        with self.assertRaises(ValueError): concierge.act(s, key, 'juggle')


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
            self.assertEqual([l['n'] for l in pile['lanes']], [0, 0, 1, 0, 0, 0, 0, 0, 0])
            nxt = c.post('/api/concierge/next', json={}).json()
            self.assertEqual(nxt['item']['rid'], r); self.assertIn('Dana wrote on email', nxt['say'])   # the facts, no model
            # The browser's walk resumes unresolved rows it already showed; a shown card is not read.
            resumed = c.post('/api/concierge/next', json={'include_surfaced': True}).json()
            self.assertEqual(resumed['item']['rid'], r)
            state = c.get('/api/concierge').json()
            self.assertEqual(state['messages'][0]['card']['kind'], 'review'); self.assertIn('providers', state)
            said = c.post('/api/concierge/say', json={'text': 'what did she attach?', 'key': nxt['item']['key']}).json()
            self.assertEqual(said['say'], 'Dana wants the file - the draft is below.')                  # a question: the (patched) model answers
            self.assertEqual(c.post('/api/funnel/settle', json={'key': nxt['item']['key'], 'verb': 'later'}).json()['verb'], 'later')
            self.assertEqual(c.get('/api/funnel/pile?force=1').json()['items'], [])
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


if __name__ == '__main__':
    unittest.main()

"""Narrow synthetic source edits, installed only by the disposable browser server."""
import os
from datetime import datetime, timedelta

from fastapi import HTTPException


def install_processing_changes(app, store):
    if os.environ.get('TASKUARY_DEMO') != '1' or not os.environ.get('TASKUARY_HOME'):
        raise RuntimeError('processing changes require the isolated demo fixture')
    from taskuary import demo
    refuse = demo.refuse
    fixture_paths = frozenset({
        '/api/fixture/processing/source', '/api/fixture/processing/member',
        '/api/fixture/processing/draft',
        '/api/fixture/processing/context',
        '/api/fixture/processing/background',
        '/api/fixture/processing/ordering',
        '/api/fixture/processing/unread-activate',
        '/api/fixture/processing/unread-arrivals',
        '/api/fixture/processing/sync-phase',
        '/api/fixture/task/agent-closed',
        '/api/fixture/task/tracker-closeout',
        '/api/fixture/task/coding-saved',
        '/api/fixture/task/chat-burst',
        '/api/fixture/task/chat-saved',
        '/api/fixture/task/closed-asked',
        '/api/fixture/task/playbook-failed',
        '/api/fixture/general/canvas',
        '/api/fixture/general/rest',
        '/api/fixture/signin/link',
        '/api/fixture/signin/terminal-ask',
        '/api/fixture/browser/last-frame',
        '/api/fixture/processing/arrive-during-next',
        '/api/fixture/task/closed-elsewhere',
        '/api/fixture/advisor/world',
        '/api/fixture/advisor/say',
        '/api/fixture/intake/arrive',
        '/api/fixture/task/matrix',
        '/api/fixture/task/advisor-raised',
        '/api/fixture/task/long-chat',
    })

    def fixture_refuse(method, path):
        # Only these test-installed, bounded database edits are extra allowances.
        # Every production route retains the original demo guard and socket guard.
        if method == 'POST' and path in fixture_paths:
            return ''
        # the one-time fill page's own form: its POST is what Chrome refused with Origin null (signin.HEADERS, 2026-10-25)
        if method == 'POST' and path.startswith('/signin/'):
            return ''
        # ...and the answer to the terminal stand-in's sign-in ask, for that task only: its press is the thing under test
        if method == 'POST' and path in answer_paths:
            return ''
        # ...and Keep / Wrong / Forget pressed from the Advisor's Why? on a task: that press reaching the task is what the Advisor test checks
        if method == 'POST' and path == '/api/learned/mark':
            return ''
        return refuse(method, path)

    demo.refuse = fixture_refuse
    answer_paths = set()

    sync_token = [None]

    @app.post('/api/fixture/task/agent-closed')
    def agent_closed(body: dict):
        """A general task from a scheduled run's failure notice, answered by its agent, which then closed it itself - through the
        real ending (selfclose.declare), the one a [[TASKUARY-DONE]] line runs. Nobody is owed a reply."""
        if set(body) != {'answer', 'said'} or not all(isinstance(body[k], str) and len(body[k]) < 2000 for k in body):
            raise HTTPException(422, 'exact answer and said are required')
        from taskuary import general, selfclose
        tid = store.create_task({'Title': 'Check the failed nightly run', 'Kind': 'general', 'Status': 'in_progress', 'Source': 'report'}, 'router')
        store.add_message({'TaskId': tid, 'Channel': 'report', 'ExternalId': f'fixture-nightly-{tid}', 'ConversationId': f'fixture-nightly-{tid}',
                           'FromName': 'Nightly report', 'Subject': 'Nightly run failed - org/app', 'BodyText': 'The nightly run failed.',
                           'Status': 'routed'})
        store.add_comment(tid, 'owner', general.USER_TYPE, 'Check why the nightly run failed.')
        store.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, body['answer'])
        out = selfclose.declare(store, tid, body['said'], 'assistant')
        if not out.get('closed'): raise HTTPException(409, f"the agent's close was refused: {out.get('why')}")
        return {'taskId': tid}

    tracker_writes = []

    @app.post('/api/fixture/task/tracker-closeout')
    def tracker_closeout(body: dict):
        """A task from a Jira item whose agent finished: its close-out proposes "comment and move to Done", read from a Jira that lives in
        this process (no socket leaves the fixture). Invented site, item and people. GET /api/fixture/tracker/writes is what reached it."""
        if set(body) != {'comment'} or not isinstance(body['comment'], str) or len(body['comment']) > 2000:
            raise HTTPException(422, 'exactly a comment is required')
        from taskuary import proposals, trackers
        def jira(c, method, path, payload=None):
            if method != 'GET': tracker_writes.append({'method': method, 'path': path, 'body': payload}); return {}
            if path.endswith('/transitions'):
                return {'transitions': [{'id': '31', 'name': 'Ship it', 'to': {'name': 'Done', 'statusCategory': {'key': 'done'}}}]}
            return {'key': 'NW-12', 'fields': {'summary': 'Nightly export is empty', 'status': {'name': 'In Review', 'statusCategory': {'key': 'indeterminate'}}}}
        trackers._jira = jira
        c = store.get_connector_by_type('jira')
        store.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Secret': 'fixture-not-a-token',
                              'ConfigJson': '{"base_url": "https://northwind.example", "email": "alex@northwind.example"}'}, 'fixture')
        tid = store.create_task({'Title': 'NW-12 Nightly export is empty', 'Kind': 'general', 'Status': 'waiting', 'Source': 'jira'}, 'router')
        store.add_message({'TaskId': tid, 'Channel': 'jira', 'ExternalId': f'jira:NW-12@{tid}', 'ConversationId': 'jira:NW-12',
                           'FromName': 'Paula Vance', 'Subject': 'NW-12 Nightly export is empty',
                           'BodyText': '[Jira NW-12 - status In Review - assigned to you]\nThe nightly export came back empty.', 'Status': 'routed'})
        store.add_comment(tid, 'general', 'agent', 'AGENT REPORT\nDetermination: the export read a renamed view.\n'
                          f"Actions: pointed it at the new view.\nSummary: {body['comment']}")
        due = trackers.closeout_due(store, tid)
        if not due or not proposals.closeout(store, tid, due, body['comment'], 'router'): raise HTTPException(409, 'no close-out was raised')
        return {'taskId': tid}

    @app.get('/api/fixture/tracker/writes')
    def tracker_writes_seen(): return {'writes': tracker_writes}

    @app.post('/api/fixture/task/closed-asked')
    def closed_asked(body: dict):
        """A finished email task, and a day later its sender asking the owner a question on the same thread - ingested through the real
        door with triage scripted (reply_only, asks_owner true). The owner, 2026-10-25: it stayed closed, off the rail, with no draft."""
        if body: raise HTTPException(422, 'this fixed fixture accepts only an empty object')
        import json
        from unittest import mock
        from taskuary import ingest
        conv, then = 'fixture-closed-asked', datetime.now() - timedelta(hours=1)
        tid = store.create_task({'Title': 'Investigate the missing ledger accounts', 'Kind': 'task', 'Status': 'done', 'Source': 'email'}, 'router')
        store.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': f'{conv}-1', 'ConversationId': conv, 'FromName': 'Erin Blake',
                           'FromEmail': 'erin@northwind.example', 'Subject': 'Missing ledger accounts', 'BodyText': 'Some accounts are missing from the pull.',
                           'SentAt': (then - timedelta(days=1)).isoformat(' '), 'Status': 'routed'})
        said = {'intent': 'reply_only', 'why': 'Erin asks Alex directly', 'title': 'Erin asks what separates the 4100 accounts',
                'summary': 'Erin Blake wants the difference between the 4100 accounts explained.', 'asks_owner': True}
        with mock.patch.object(ingest, '_spawn'):          # the draft is its own job; this fixture shows the row, not the drafter
            out = ingest.ingest_message(store, {'external_id': f'{conv}-2', 'channel': 'email', 'from_email': 'erin@northwind.example',
                                                'from_name': 'Erin Blake', 'conversation_id': conv, 'subject': 'RE: Missing ledger accounts',
                                                'body': 'Can you explain the difference between the 4100 accounts?', 'sent_at': then.isoformat(' ')},
                                         llm=lambda system, user, **k: json.dumps(said))
        if out.get('task_id') != tid: raise HTTPException(409, f'the question did not join its task: {out}')
        return {'taskId': tid, 'status': store.get_task(tid)['Status']}

    @app.post('/api/fixture/task/advisor-raised')
    def advisor_raised(body: dict):
        """Erin's mail filed as fyi and her follow-up, then an Advisor idea saying the reply is still owed - judged through the real
        door (assistant.triage_ideas, triage scripted), which opens the task. The owner, 2026-10-28: its Came from showed only the
        Advisor's own line, "Advisor · Advisor", with "whose move: ..." in its words, and never Erin's mail."""
        if body: raise HTTPException(422, 'this fixed fixture accepts only an empty object')
        import json
        from unittest import mock
        from taskuary import assistant, ingest
        conv, now = 'fixture-advisor-raised', datetime.now()
        mail = lambda i, ago, words: store.add_message({'Channel': 'email', 'ExternalId': f'{conv}-{i}', 'ConversationId': conv, 'Direction': 'in',
                                                        'FromName': 'Erin Blake', 'FromEmail': 'erin@vendor.example', 'Subject': 'Year-end statements',
                                                        'BodyText': words, 'SentAt': (now - ago).isoformat(' ', 'seconds'), 'Status': 'filed'})
        first = mail(1, timedelta(days=2), 'Could you send the year-end statements for the donor list when you have them?')
        again = mail(2, timedelta(hours=3), 'Following up on the year-end statements - our board meets Friday and we still need them.')
        i = store.upsert_idea({'key': f'idea:{conv}', 'kind': 'idea', 'sig': conv,
                               'text': "Triage filed Erin's mail as fyi, but her follow-up shows the year-end statements are still outstanding - I'd send them today.",
                               'action': {'type': 'message', 'mid': first, 'whose': 'the owner', 'suggest': 'Send the year-end statements and the donor summary.',
                                          'why': f'Erin Blake mid {first} asked; her follow-up mid {again} says the board meets Friday.'}},
                              (now - timedelta(minutes=5)).isoformat(' ', 'seconds'))
        said = {'intent': 'task', 'kind': 'task', 'why': 'The Advisor says Erin is still waiting on the year-end statements from Alex.',
                'title': 'Send Erin the year-end statements', 'summary': 'Erin Blake still needs the year-end statements before Friday.'}
        with mock.patch.object(ingest, '_spawn'):
            assistant.triage_ideas(store, [i], lambda system, user, **k: json.dumps(said))
        tid = json.loads(store.get_idea(i['IdeaId'])['ActionJson'] or '{}').get('tid')
        if not tid: raise HTTPException(409, 'the idea opened no task')
        return {'taskId': tid, 'mails': [first, again]}

    @app.post('/api/fixture/task/long-chat')
    def long_chat(body: dict):
        """A WhatsApp group's fifteen lines and a 22-item to-do, six ticked, on one task. The owner, 2026-10-28: "I want to be able to see
        what came in actual chat without going to the bottom ... show all 15 does nothing" - the chat sat under the whole to-do."""
        if body: raise HTTPException(422, 'this fixed fixture accepts only an empty object')
        import json
        tid = store.create_task({'Title': 'Site ops: the move to the new building', 'Kind': 'task', 'Status': 'open', 'Source': 'whatsapp',
                                 'Summary': 'The site team needs the move to the new building planned and signed off.'}, 'router')
        start, who = datetime.now() - timedelta(hours=2), ('Ray Colton', 'Gail Moreno', 'Paula Vance')
        for i in range(15):
            store.add_message({'TaskId': tid, 'Channel': 'whatsapp', 'SourceName': 'Site ops', 'ExternalId': f'fixture-long-{tid}-{i}',
                               'FromName': who[i % 3], 'BodyText': f'Move note {i + 1}: ' + ('the crates for floor two' if i % 2 else 'keys and the lift booking'),
                               'SentAt': (start + timedelta(minutes=7 * i)).isoformat(' ', 'seconds'), 'Status': 'routed'})
        todo = [{'id': f't{i}', 'text': f'Move step {i + 1}: ' + ('label the crates' if i % 2 else 'book the lift'), 'done': i < 6} for i in range(22)]
        store._exec('UPDATE task SET Checklist=? WHERE TaskId=?', (json.dumps(todo), tid))
        return {'taskId': tid}

    @app.post('/api/fixture/task/chat-burst')
    def chat_burst(body: dict):
        """A WhatsApp group's burst - six lines from two people in a quarter of an hour - on one task: what From lists newest on top."""
        if body: raise HTTPException(422, 'this fixed fixture accepts only an empty object')
        tid = store.create_task({'Title': 'Site ops: Thursday walk-through', 'Kind': 'reply', 'Status': 'open', 'Source': 'whatsapp'}, 'router')
        start = datetime.now() - timedelta(minutes=30)
        for i, (who, words) in enumerate((('Ray Colton', 'Morning all'), ('Gail Moreno', 'Walk-through is Thursday'), ('Ray Colton', 'Keys are at reception from 7'),
                                          ('Gail Moreno', 'Alex, can you be there at 9:30?'), ('Ray Colton', 'Also need someone to sign the snag list'),
                                          ('Gail Moreno', 'and bring the floor plan please'))):
            store.add_message({'TaskId': tid, 'Channel': 'whatsapp', 'SourceName': 'Site ops', 'ExternalId': f'fixture-burst-{tid}-{i}',
                               'FromName': who, 'BodyText': words, 'SentAt': (start + timedelta(minutes=3 * i)).isoformat(' '), 'Status': 'routed'})
        return {'taskId': tid}

    @app.post('/api/fixture/task/chat-saved')
    def chat_saved(body: dict):
        """A WhatsApp group's ask whose general agent the owner stopped and saved (Stop and save): its transcript and AGENT REPORT
        filed, nothing sent. The browser test then presses Reply and holds the draft - the row the owner saw wrap onto two lines
        (2026-10-23): the agent's session over, its WhatsApp reply drafting. Invented people. `draft`: a reply already drafted and
        waiting on the owner - Close out open on it under the Result (the owner's 2026-10-26 screen, its first row cut in half).
        `todo`: one long to-do, ticked - a short Result under a Came from drawer that holds more (the owner's 2026-10-26 screen).
        `made`: the file name of a plan it wrote into the task's outputs folder and showed in its chat - the same file twice, the way a
        general agent leaves a document (the owner's 2026-10-27 screen: "where is the plan?")."""
        import re
        if set(body) - {'draft', 'todo', 'made'} or not all(isinstance(body.get(k, ''), str) and len(body.get(k, '')) <= 4000 for k in ('draft', 'todo', 'made')):
            raise HTTPException(422, 'only draft, todo and made strings are accepted')
        if body.get('made') and not re.fullmatch(r'[\w-]{1,60}\.md', body['made']): raise HTTPException(422, 'made is a plain .md file name')
        from taskuary import terminal
        tid = store.create_task({'Title': 'Site ops: who signs the snag list on Thursday', 'Kind': 'general', 'Status': 'in_progress', 'Source': 'whatsapp',
                                 'Assignee': 'agent:general', 'Tags': terminal.SAVED}, 'router')
        store.add_message({'TaskId': tid, 'Channel': 'whatsapp', 'SourceName': 'Site ops', 'ExternalId': f'fixture-saved-{tid}', 'ConversationId': f'fixture-saved-{tid}',
                           'FromName': 'Gail Moreno', 'BodyText': 'Alex, can you find out who signs the snag list on Thursday and tell the group?',
                           'SentAt': (datetime.now() - timedelta(minutes=20)).isoformat(' '), 'Status': 'routed'})
        store.add_transcript(tid, f'fixture-{tid}', "Looking for who signs the snag list.\nThe handover sheet names Ray Colton for Thursday.",
                             agent='general', cwd='C:/work', brain='claude')
        store.add_comment(tid, 'general', 'agent', 'AGENT REPORT\nDetermination: Ray Colton signs the snag list on Thursday.\n'
                          'Actions: Read the handover sheet.\nSummary: Ray Colton signs it; the group should be told.')
        if body.get('todo'):
            import json
            store._exec('UPDATE task SET Checklist=? WHERE TaskId=?', (json.dumps([{'id': 'a', 'text': body['todo'], 'done': True}]), tid))
        if body.get('draft'):
            mid = store.list_messages(tid)[0]['MessageId']
            store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': body['draft'], 'Reason': 'needs a reply: Gail asks Alex'})
        if body.get('made'):
            from taskuary import outputs, session_artifacts
            out = outputs.folder(tid); out.mkdir(parents=True, exist_ok=True)
            (out / body['made']).write_text('# Snag list sign-off\n\n1. Ray Colton signs on Thursday.\n2. Keys are at reception from 7.\n', encoding='utf-8')
            session_artifacts.shown(store, tid, out / body['made'])
        return {'taskId': tid}

    @app.post('/api/fixture/task/coding-saved')
    def coding_saved(body: dict):
        """A coding task whose agent the owner stopped and saved (Stop and save): its session's screen filed as the transcript, its
        AGENT REPORT written, and the run's own diff kept - what the Result in the work column reads. Invented people and paths.
        `mine`: a task the owner made in the Assistant - nobody sent it, so nobody is owed a reply. `writing`: its write-up still running."""
        if set(body) - {'mine', 'writing'} or not all(isinstance(v, bool) for v in body.values()):
            raise HTTPException(422, 'only the booleans mine and writing are accepted')
        from taskuary import terminal, writeup
        mine = body.get('mine', False)
        tid = store.create_task({'Title': 'org/app#398 census sync fails when a site has no manager', 'Kind': 'coding', 'Status': 'in_progress',
                                 'Source': 'assistant' if mine else 'github', 'Assignee': 'agent:coding', 'Tags': f'repo:org/app,{terminal.SAVED}'}, 'router')
        if mine: store.add_message({'TaskId': tid, 'Channel': 'assistant', 'ExternalId': f'fixture-asst-398-{tid}', 'FromName': 'You',
                                    'BodyText': 'Find out why the census sync stops at a site with no manager.', 'Status': 'context'})
        else: store.add_message({'TaskId': tid, 'Channel': 'github', 'ExternalId': f'fixture-gh-398-{tid}', 'ConversationId': f'fixture-gh-398-{tid}',
                                 'FromName': 'Ray Colton', 'Subject': 'census sync fails when a site has no manager',
                                 'BodyText': 'Third night in a row the census sync stops at a site with no manager.', 'Status': 'routed'})
        if body.get('writing'):
            with writeup._LOCK: writeup._STATE[tid] = {'job': f'fixture-{tid}', 'stage': 'report', 'running': True, 'error': None, 'close': False}
        store.add_transcript(tid, f'fixture-{tid}', "I'll take #398. Reading the census sync first.\n> pytest tests/test_census_sync.py -q\n9 passed",
                             agent='coding', cwd='C:/work/org-app', brain='claude')
        store.add_comment(tid, 'coding', 'agent', 'AGENT REPORT\nDetermination: A site with no manager stopped the whole census run.\n'
                          'Actions: Skip that row and log it once; a test for a site with no manager.\n'
                          'Summary: Census sync no longer stops on a site with no manager.\n\nLAST MESSAGE\n'
                          'Skipped the row with no manager and logged it once. 9 passed. Not pushed - yours to approve.')
        rid = store.start_run(tid, 'coding', 'Fix #398', 'fixture')
        store.update_run(rid, {'Status': 'done', 'DiffText': 'diff --git a/app/census/sync.py b/app/census/sync.py\n--- a/app/census/sync.py\n'
                               '+++ b/app/census/sync.py\n@@ -1,2 +1,4 @@\n def sync(site):\n+    if not site.manager:\n+        continue\n-    pass\n'}, finished=True)
        return {'taskId': tid}

    @app.post('/api/fixture/task/playbook-failed')
    def playbook_failed(body: dict):
        """A playbook set up in the owner's own words whose general agent could not start - its run FAILED with the reason, and a
        restart then cut it off - with a long mail beside it in From. The owner's 2026-10-26 laptop screen: the title said twice, the
        reason at the foot of a scroller inside a scroller, the dock a third of the height. Invented words and people."""
        if body: raise HTTPException(422, 'this fixed fixture accepts only an empty object')
        from taskuary import general, origin, playbooks, terminal, workerstate as ws
        text = ('most group chats are fyi, but if a message asks me for something by name, put it on my list and draft a short reply '
                'I can send as it is')
        tid = playbooks.setup_task(store, text, None, '', 'owner')['taskId']
        para = 'Gail asked the site group who signs the snag list, then the thread moved on to parking and the floor plan. '
        store.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': f'fixture-pb-{tid}', 'ConversationId': f'fixture-pb-{tid}',
                           'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'Subject': 'Site ops digest',
                           'BodyText': '\n\n'.join(para * 3 for _ in range(14)), 'SentAt': (datetime.now() - timedelta(hours=4)).isoformat(' '),
                           'Status': 'routed'})
        why = f'Playbook setup could not start: {origin.no_reviewer(store)}. You can retry in this conversation.'
        sid = f'fixture-pb-{tid}'
        ws.record(store, tid, sid, 'working', source='fixture')
        store.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, why)
        ws.record(store, tid, sid, 'failed', text=why, source='fixture')
        store.tag_task(tid, terminal.INTERRUPTED, True, 'startup')
        store.add_comment(tid, 'startup', 'agent', 'Taskuary restarted after the agent session ended. The task is open again - nobody is working it.')
        return {'taskId': tid}

    @app.post('/api/fixture/processing/sync-phase')
    def sync_phase(body: dict):
        from taskuary import server
        phases = {'fetching': 'reading synthetic sources', 'triaging': 'processing synthetic messages',
                  'checking': 'checking synthetic work', 'running_reports': 'running synthetic reports', 'idle': ''}
        if set(body) != {'phase'} or body['phase'] not in phases:
            raise HTTPException(422, 'one fixed synthetic phase is required')
        phase = body['phase']
        if phase == 'idle':
            if sync_token[0] is not None:
                server._status_end(store, sync_token[0])
                sync_token[0] = None
                server._POLL_BUSY.release()
        else:
            if sync_token[0] is None:
                if not server._POLL_BUSY.acquire(blocking=False):
                    raise HTTPException(409, 'fixture sync already owned')
                sync_token[0] = server._status_begin(store, 'full', phases[phase])
            server._status_progress(store, sync_token[0], phases[phase], phase=phase)
            store.set_setting('triage_last_error', 'Synthetic triage error remains visible', 'fixture')
        return {'phase': phase}

    @app.post('/api/fixture/processing/unread-activate')
    def activate_unread(body: dict):
        if body:
            raise HTTPException(422, 'empty fixture input required')
        from taskuary import concierge, funnel, terminal
        from taskuary.processing_startup import initialize
        result = initialize(store, live_state=terminal.live_sessions(tail=6))
        # This explicit disposable-fixture activation supplies one deterministic
        # model decision; every other prompt keeps the normal offline demo voice.
        # Exercise the real say/decision/guarded-next path without a model service.
        def fixture_brain(target_store, **kwargs):
            if target_store is not store:
                raise RuntimeError('synthetic navigation model belongs to the fixture store')
            fallback = demo.brain()

            def model(system, user, **options):
                if 'The owner says: Next' in str(user).splitlines():
                    return 'Next.\nCALL: {"kind": "next", "params": {}}'     # one line since 2026-09-25: CALL, never DECIDE
                return fallback(system, user, **options)

            return model

        concierge.brain = fixture_brain
        funnel.invalidate()
        return result

    @app.post('/api/fixture/processing/unread-arrivals')
    def unread_arrivals(body: dict):
        if body:
            raise HTTPException(422, 'empty fixture input required')
        if not store.processing_reads_active():
            raise HTTPException(409, 'activate synthetic read boundary first')
        from taskuary import funnel
        ids = []
        for index in range(507):
            ids.append(store.add_message({'Channel': 'email', 'SourceName': 'unread-fixture@example.test',
                'ExternalId': f'unread-arrival-{index}', 'ConversationId': f'unread-arrival-{index}',
                'FromName': 'Unread fixture', 'FromEmail': 'fixture@example.test',
                'Subject': f'Shared arrival {index:03}', 'BodyText': f'Fixture information {index:03}',
                'SentAt': '2020-01-01 12:00:00' if index == 506 else datetime.now().isoformat(' '),
                'Status': 'triaging' if index == 505 else 'ignored' if index % 2 else 'filed'}))
        store.reconcile_processing_membership()
        funnel.invalidate()
        store._poke('feed-changed')
        return {'ids': ids}

    @app.post('/api/fixture/processing/background')
    def background_card(body: dict):
        if set(body) != {'task_id'} or type(body['task_id']) is not int:
            raise HTTPException(422, 'exact task_id is required')
        from taskuary import concierge, funnel, general
        item = funnel.next_item(store, f"agent:{body['task_id']}")
        if not item or item.get('kind') != 'agent':
            raise HTTPException(404, 'synthetic agent missing')
        card = {**concierge.card_for(item), 'background_event': True}
        # The native watcher producer has separate service coverage. This fixture
        # exercises persisted passive-card ingestion and restoration in the browser.
        dock, _ = general.dock_task(store, 'fixture')
        concierge.record(store, dock['TaskId'], 'assistant', 'Synthetic passive worker notice', card)
        store._poke('feed-changed', task_id=body['task_id'])
        return {'ok': True, 'key': card['key']}

    @app.post('/api/fixture/processing/context')
    def add_context(body: dict):
        if set(body) != {'task_id', 'body'} or type(body['task_id']) is not int:
            raise HTTPException(422, 'exact task_id and body are required')
        if not isinstance(body['body'], str) or len(body['body']) > 50000:
            raise HTTPException(422, 'body must be a bounded string')
        if not store.get_task(body['task_id']):
            raise HTTPException(404, 'synthetic task missing')
        store.add_comment(body['task_id'], 'fixture', 'user', body['body'])
        return {'ok': True}

    @app.post('/api/fixture/processing/draft')
    def change_draft(body: dict):
        if set(body) != {'review_id', 'body'} or type(body['review_id']) is not int:
            raise HTTPException(422, 'exact review_id and body are required')
        if not isinstance(body['body'], str) or len(body['body']) > 50000:
            raise HTTPException(422, 'body must be a bounded string')
        review = store.get_review(body['review_id'])
        if not review or review.get('Status') not in ('pending', 'held'):
            raise HTTPException(404, 'synthetic pending review missing')
        store.save_review_draft(body['review_id'], body['body'])
        return {'ok': True, 'draft': body['body']}

    @app.post('/api/fixture/processing/source')
    def change_source(body: dict):
        if set(body) != {'message_id', 'body'} or type(body['message_id']) is not int:
            raise HTTPException(422, 'exact message_id and body are required')
        if not isinstance(body['body'], str) or len(body['body']) > 50000:
            raise HTTPException(422, 'body must be a bounded string')
        mid = body['message_id']
        if not store.get_message(mid):
            raise HTTPException(404, 'synthetic message missing')
        store.update_message_body(mid, body['body'])
        # Exercise the actual websocket consumer after a synthetic source update.
        store._poke('feed-changed', message_id=mid)
        return {'ok': True, 'message_id': mid}

    @app.post('/api/fixture/processing/member')
    def add_older_member(body: dict):
        if set(body) != {'message_id', 'body'} or type(body['message_id']) is not int:
            raise HTTPException(422, 'exact message_id and body are required')
        if not isinstance(body['body'], str) or len(body['body']) > 50000:
            raise HTTPException(422, 'body must be a bounded string')
        original = store.get_message(body['message_id'])
        if not original or not original.get('TaskId'):
            raise HTTPException(404, 'synthetic task member missing')
        sent = datetime.fromisoformat(original['SentAt']) - timedelta(days=1)
        mid = store.add_message({
            'TaskId': original['TaskId'], 'Channel': original['Channel'],
            'Status': 'filed', 'Subject': 'Synthetic older context member',
            'SentAt': sent.isoformat(sep=' '), 'BodyText': body['body'],
        })
        return {'ok': True, 'message_id': mid}

    @app.post('/api/fixture/processing/arrive-during-next')
    def arrive_during_next(body: dict):
        """A WhatsApp task lands while the next Next is being made - after its admission, before its commit check (the owner,
        2026-10-23: Next drew the row below, then the table jumped back). Armed once; the press after it runs as it always does."""
        if body: raise HTTPException(422, 'this fixed fixture accepts only an empty object')
        from taskuary import concierge, funnel
        real, fired = concierge.chips_for, []
        def chips_while_a_row_arrives(st, *a, **k):
            if not fired:
                fired.append(True); concierge.chips_for = real
                tid = store.create_task({'Title': 'Fix the gate code on the side door', 'Kind': 'general', 'Status': 'open', 'Source': 'whatsapp'}, 'router')
                store.add_message({'TaskId': tid, 'Channel': 'whatsapp', 'Status': 'routed', 'ExternalId': f'arrive-during-next:{tid}',
                                   'FromName': 'Ray Colton', 'Subject': 'Side door', 'BodyText': 'The side door code stopped working.',
                                   'SentAt': datetime.now().isoformat(' ')})
                store.reconcile_processing_membership()
                funnel.invalidate()
            return real(st, *a, **k)
        concierge.chips_for = chips_while_a_row_arrives
        return {'armed': True}

    @app.post('/api/fixture/task/closed-elsewhere')
    def closed_elsewhere(body: dict):
        """The task on the table closed somewhere else - the phone, the Tasks page - so the rail's next read says it is gone and the
        table clears under whatever the page was doing (the owner, 2026-10-26: Next said "The list moved while that was loading")."""
        if set(body) != {'task_id'} or type(body['task_id']) is not int: raise HTTPException(422, 'exact task_id is required')
        from taskuary import concierge, funnel
        if not concierge.close_task(store, body['task_id'], 'owner'): raise HTTPException(409, 'that task was not open')
        store.reconcile_processing_membership(); funnel.invalidate()
        return {'closed': body['task_id']}

    @app.post('/api/fixture/processing/ordering')
    def ordering_arrivals(body: dict):
        if body:
            raise HTTPException(422, 'this fixed ordering fixture accepts only an empty object')
        from taskuary import funnel
        now = datetime.now()
        titles = {}
        for name, priority, minutes in (('urgent', 'urgent', 1), ('high', 'high', 2),
                                        ('old', 'normal', 60), ('new', 'normal', 3)):
            title = 'ORDERING ' + name.upper()
            tid = store.create_task({'Title': title, 'Kind': 'general', 'Status': 'open', 'Priority': priority}, 'fixture')
            store.add_message({'TaskId': tid, 'Channel': 'email', 'Status': 'routed',
                               'ExternalId': 'ordering:' + name, 'SourceName': 'ordering@example.test',
                               'FromEmail': 'sender@example.test', 'FromName': 'Ordering fixture',
                               'Subject': title, 'BodyText': 'Please handle this synthetic request.',
                               'SentAt': (now - timedelta(minutes=minutes)).isoformat(' ')})
            titles[name] = title
        funnel.invalidate()
        store._poke('feed-changed')
        return {'titles': titles}

    @app.post('/api/fixture/signin/link')
    def signin_link(body: dict):
        """A task whose agent asked to be signed in to northwind.example - the ask the [[TASKUARY-SIGNIN]] marker records - and a fresh
        one-time fill link for it. No browser runs, so a fill gets as far as "the task's browser is not open": past the Origin check."""
        if body:
            raise HTTPException(422, 'this fixed sign-in fixture accepts only an empty object')
        from taskuary import signin, workerstate as ws
        tid = store.create_task({'Title': 'Pay the Payworth invoice', 'Kind': 'general', 'Status': 'in_progress'}, 'fixture')
        ws.record(store, tid, 'fixture-sid', 'input_needed', request_id=f'{signin.PREFIX}northwind.example',
                  text='Sign in to northwind.example to continue', source='api')
        return {'taskId': tid, **signin.link(store, tid)}

    @app.post('/api/fixture/general/canvas')
    def general_canvas(body: dict):
        """A research task one email brought, whose general agent already finished a turn: the recorded claude trace from
        tests/fixtures/agent_steps (invented people and paths) on a session that ran no CLI."""
        if body:
            raise HTTPException(422, 'this fixed canvas fixture accepts only an empty object')
        import json
        from pathlib import Path
        from taskuary import general, terminal
        rec = Path(__file__).resolve().parents[2] / 'tests' / 'fixtures' / 'agent_steps' / 'claude.trace.json'
        trace = json.loads(rec.read_text(encoding='utf-8'))
        answer = next(e['detail'] for e in reversed(trace) if e['type'] == 'progress')
        tid = store.create_task({'Title': 'Budget review status', 'Kind': 'research', 'Status': 'open'}, 'fixture')
        store.add_message({'TaskId': tid, 'Channel': 'email', 'Status': 'routed', 'ExternalId': 'canvas:budget',
                           'FromEmail': 'gail@northwind.example', 'FromName': 'Gail Moreno', 'Subject': 'Budget review',
                           'BodyText': 'Where does the budget review stand?', 'SentAt': datetime.now().isoformat(' ')})
        store.add_comment(tid, 'owner', general.USER_TYPE, 'What is the budget review waiting on?')
        store.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, answer)
        sess = general.GeneralSession(store, tid)
        sess.trace, sess.trace_revision = [{'type': 'start', 'session': {'provider': 'Claude Code'}}, *trace], 1
        terminal.SESSIONS[sess.sid] = sess
        return {'taskId': tid}

    @app.post('/api/fixture/general/rest')
    def general_rest(body: dict):
        """A research ask whose general agent finished and is gone: its chat at rest under the Result, a two-box To do, and a title
        that is the whole ask - what a short laptop drew as three scrollers fighting over one column (TQ-1215). Invented people."""
        if body: raise HTTPException(422, 'this fixed fixture accepts only an empty object')
        from taskuary import general
        ask = ('I need you to find every commercial building within a 3 mile radius of 1 Example Way. Then I want you to find the direct '
               'email of the owners or decision makers for each property. We are looking to buy a property, so I want to contact each of them.')
        tid = store.create_task({'Title': ask, 'Kind': 'research', 'Status': 'open', 'Source': 'whatsapp'}, 'router')
        store.add_message({'TaskId': tid, 'Channel': 'whatsapp', 'Status': 'routed', 'ExternalId': f'fixture-rest-{tid}', 'ConversationId': f'fixture-rest-{tid}',
                           'FromName': 'Gail Moreno', 'BodyText': ask, 'SentAt': (datetime.now() - timedelta(minutes=40)).isoformat(' ')})
        store.set_task_checklist(tid, ['Find every commercial building within a 3-mile radius of 1 Example Way.',
                                       'Find direct email addresses for the owners or decision makers for each property.'], 'router')
        store.add_comment(tid, 'owner', general.USER_TYPE, 'Run it again with the county parcel file.')
        found = (('1,184 parcel records,', 'with recorded owners and mailing addresses.'), ('36 published emails:', '25 named contacts, 8 general inboxes.'),
                 ('12 owners', 'with no public email - a mailing address only.'), ('3 duplicates', 'merged by owner name.'))
        store.add_comment(tid, 'assistant', general.ASSISTANT_TYPE,
                          'The rerun produced:\n\n' + '\n'.join(f'- **{n}** {w}' for n, w in found) + '\n\nThe sheet is in the task folder.')
        store.add_comment(tid, 'general', 'agent', 'AGENT REPORT\nDetermination: 1,184 commercial parcels lie within the radius; 36 owners publish an email.\n'
                          "Actions: Read the county parcel file and each owner's public site.\nSummary: A sheet of parcels, owners and the emails found.")
        return {'taskId': tid}

    from taskuary import demo as _demo

    class TypedPane(_demo.Replay):
        "A terminal CLI that keeps what is typed into it - the demo's Replay takes no dictation."
        def __init__(self, store, tid):
            super().__init__(store, tid, 'Claude Code', lines=[('Claude Code is waiting on a sign-in', 0)])
            self.got, self.n = [], 0
        def write(self, data): self.got.append(data); self.n += 1

    panes = {}

    @app.post('/api/fixture/signin/terminal-ask')
    def signin_terminal_ask(body: dict):
        """A general task whose agent works in a terminal pane (no conversation session) and asked to be signed in to
        northwind.example: the ask a pty's Stop hook records - no choices, since a pty's are a chooser (signin.needs)."""
        if body:
            raise HTTPException(422, 'this fixed sign-in fixture accepts only an empty object')
        from taskuary import signin, terminal, workerstate as ws
        tid = store.create_task({'Title': 'Pay the Payworth invoice', 'Kind': 'general', 'Status': 'in_progress', 'Tags': 'needs:browser'}, 'fixture')
        pane = panes[tid] = TypedPane(store, tid)
        terminal.SESSIONS[pane.sid] = pane
        ws.record(store, tid, pane.sid, 'input_needed', request_id=f'{signin.PREFIX}northwind.example',
                  text='Sign in to northwind.example to continue', source='api')
        answer_paths.add(f'/api/tasks/{tid}/worker/answer')
        return {'taskId': tid, 'sid': pane.sid}

    @app.get('/api/fixture/signin/typed/{tid}')
    def signin_typed(tid: int): return {'typed': ''.join(panes[tid].got) if tid in panes else ''}

    # a frame the screencast would have relayed: a 1x1 JPEG
    JPEG = ('/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////'
            'wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=')

    @app.post('/api/fixture/browser/last-frame')
    def browser_last_frame(body: dict):
        """A general task whose browser session ends - on an act held for the owner, on one that failed when approved, or normally -
        through the real close (browserview.close -> keep_last). Then the agent's answer, so the picture sits under it."""
        if set(body) != {'end'} or body['end'] not in ('held', 'failed', 'normal'):
            raise HTTPException(422, "end must be 'held', 'failed' or 'normal'")
        import json
        from unittest import mock
        from taskuary import browsergate, browserview, general, proposals
        tid = store.create_task({'Title': 'Pay the Payworth invoice', 'Kind': 'general', 'Status': 'in_progress', 'Tags': 'needs:browser'}, 'fixture')
        store.add_comment(tid, 'owner', general.USER_TYPE, 'Pay the Payworth invoice on the vendor portal.')
        sid, page = f'fixture-frame-{tid}', 'https://billing.vendor.example/invoices/1001'
        browserview.LAST[sid] = {'frame': json.dumps({'type': 'frame', 'data': JPEG}), 'url': page, 'at': 0}
        if body['end'] != 'normal':
            p = {'action': 'browser_act', 'sid': sid, 'args': ['click', '@e12'], 'command': 'agent-browser click @e12', 'url': page,
                 'site': 'vendor.example', 'what': 'click the "Pay $412.50" button on billing.vendor.example', 'why': 'it pays'}
            proposals.queue(store, tid, p, 'agent')
            browserview.ended_on(sid, 'held', store, tid)
            if body['end'] == 'failed':
                # Approve pressed with the browser already gone: the real perform refuses it and marks the session
                with mock.patch.object(browserview, 'state', return_value={'open': False}):
                    try: browsergate.perform(store, tid, p)
                    except RuntimeError: pass
        browserview.close(sid)
        store.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, {'held': 'The invoice page is open, waiting on your Approve.',
                          'failed': 'The Pay button on the invoice page did not go through.', 'normal': 'I read the invoice page.'}[body['end']])
        return {'taskId': tid}

    # ── THE STATE MATRIX (browser/state-matrix, 2026-10-28): the task states the demo world lacks, each one task, invented people ──────────
    MATRIX = ('sent', 'working', 'coding_working', 'asked', 'stopped', 'finished', 'done', 'note', 'deferred', 'todo', 'idea', 'news',
              'fyi_thread', 'idea_mail')

    @app.post('/api/fixture/task/matrix')
    def matrix_state(body: dict):
        """{state}: one task in that state, built the way the app leaves it. `sent` a reply that went, the task still open; `working` a
        general agent's terminal at work, `coding_working` a coding one's; `asked` an agent at its prompt with a question for the owner;
        `stopped` a coding run cut off mid-work - its screen kept, no write-up; `finished` a general agent whose run said it finished;
        `done` / `note` closed by the owner, bare or with a note; `deferred` put away with Remind me; `todo` the owner's own to-do list;
        `idea` an Advisor find on the rail; `news` a saved agent result and then the sender writing again; `fyi_thread` three FYI mails on
        one email thread with no task (one rail row, trust audit P2); `idea_mail` an Advisor find about an FYI mail with no task (P1)."""
        if set(body) != {'state'} or body['state'] not in MATRIX: raise HTTPException(422, f'state is one of {MATRIX}')
        from taskuary import concierge, general, remind, terminal, workerstate as ws
        s, now = body['state'], datetime.now()
        at = lambda **k: (now - timedelta(**k)).isoformat(' ', timespec='seconds')
        def task(title, kind, status='open', **kw): return store.create_task({'Title': title, 'Kind': kind, 'Status': status, 'Source': 'email', **kw}, 'router')
        def mail(tid, who, words, ago=40, subject=None):
            return store.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': f'matrix-{s}-{tid}-{ago}', 'ConversationId': f'matrix-{s}-{tid}',
                                      'FromName': who, 'FromEmail': f"{who.split()[0].lower()}@northwind.example", 'Subject': subject or f'About {s}',
                                      'BodyText': words, 'SentAt': at(minutes=ago), 'Status': 'routed'})
        def pane(tid, lines, label='Claude Code'):
            p = _demo.Replay(store, tid, label, lines=lines); terminal.SESSIONS[p.sid] = p; return p
        if s == 'sent':
            tid = task('Can you send the signed Trainly order form?', 'reply')
            mid = mail(tid, 'Erin Blake', 'Can you send the signed Trainly order form back today?')
            rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Attached - signed this morning.',
                                    'Reason': 'needs a reply: Erin asks Alex'})
            store.decide_review(rid, 'approved', 'Attached - signed this morning.', 'owner')
        elif s in ('working', 'coding_working'):
            coding = s == 'coding_working'
            tid = task('org/app#402 export drops the last row' if coding else 'Reconcile the Payworth October export', 'coding' if coding else 'general',
                       'in_progress', Assignee=f"agent:{'coding' if coding else 'general'}", **({'Tags': 'repo:org/app'} if coding else {}))
            mail(tid, 'Paula Vance', 'The export drops the last row every night.' if coding else 'The October export does not tie out to the bank feed.')
            if coding: p = pane(tid, [('Reading the export and the bank feed side by side...', 0), ('', 3600)], 'coding')
            else:      # a general agent works in its conversation, mid-answer
                store.add_comment(tid, 'owner', general.USER_TYPE, 'Reconcile the October export against the bank feed.')
                p = general.GeneralSession(store, tid); p.busy = True; terminal.SESSIONS[p.sid] = p
            ws.record(store, tid, str(p.sid), 'working', source='fixture')
        elif s == 'asked':
            tid = task('Close the Spendly cards for the leavers', 'general', 'in_progress', Assignee='agent:general')
            mail(tid, 'Gail Moreno', 'Two leavers still have Spendly cards - can they be closed?')
            p = pane(tid, [('Found two leavers with open cards.', 0)]); p.agent = 'general'
            ws.record(store, tid, str(p.sid), 'input_needed', text='Should I close both cards today, or wait for their last expense claims?', source='fixture')
        elif s == 'stopped':
            tid = task('org/app#405 ledger import skips weekends', 'coding', 'in_progress', Assignee='agent:coding', Tags='repo:org/app')
            mail(tid, 'Ray Colton', 'The ledger import skips Saturday and Sunday rows.')
            store.add_transcript(tid, f'matrix-{tid}', "Reading the ledger import.\n> pytest tests/test_import.py -q\n2 failed", agent='coding', cwd='C:/work/org-app', brain='claude')
            ws.record(store, tid, f'matrix-{tid}', 'working', source='fixture')
            ws.record(store, tid, f'matrix-{tid}', 'stopped', text='Stopped by you.', source='fixture')
        elif s == 'finished':
            tid = task('Who is missing the Trainly safety module?', 'general', 'in_progress')
            mail(tid, 'Gail Moreno', 'Who is still missing the safety module?', ago=90)
            store.add_comment(tid, 'owner', general.USER_TYPE, 'Who is still missing the safety module?')
            store.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Three people are missing the safety module: Erin Blake, Omar Keller and Ray Colton.')
            store.add_comment(tid, 'general', 'agent', 'AGENT REPORT\nDetermination: three people are missing the safety module.\n'
                              'Actions: Read the Trainly completion report.\nSummary: The three names, with their sites.')
            ws.record(store, tid, f'matrix-{tid}', 'working', source='fixture')
            ws.record(store, tid, f'matrix-{tid}', 'finished', text='Three people are missing the safety module.', source='fixture')
        elif s in ('done', 'note'):
            tid = task('Book the room for the Thursday walk-through' if s == 'done' else 'Check the Fairhaven badge reader', 'general')
            mail(tid, 'Marcus Reed', 'Can you book a room for the Thursday walk-through?' if s == 'done' else 'The Fairhaven badge reader is offline again.')
            if s == 'note': store.add_comment(tid, 'owner', 'human', 'Closed out: Called the site - it was a loose cable, back up now.')
            concierge.close_task(store, tid, 'owner')
        elif s == 'deferred':
            tid = task('Renew the PhishGuard seats', 'general')
            mail(tid, 'Omar Keller', 'The PhishGuard seats renew next month - can you check the count first?')
            remind.set_reminder(store, tid, (now + timedelta(days=3)).strftime('%Y-%m-%d'), 'owner')
        elif s == 'todo':
            tid = store.create_task({'Title': 'Before the audit', 'Kind': 'task', 'Status': 'open', 'Source': 'assistant'}, 'owner')
            store.set_task_checklist(tid, ['Print the August bank reconciliations', 'Export the AP ageing for Q3', 'Find the fixed asset register'], 'owner')
        elif s == 'idea':
            tid = None
            store.upsert_idea({'key': f'idea:matrix-weekly-ageing-{now:%H%M%S%f}', 'kind': 'idea', 'sig': 'matrix',
                               'text': 'The AP ageing is pulled by hand every Monday - a weekly report could send it.', 'action': {}}, at(minutes=5))
            from taskuary import funnel
            store.reconcile_processing_membership(); funnel.invalidate(); store._poke('feed-changed')
        elif s in ('fyi_thread', 'idea_mail'):
            tid = None
            def fyi_mail(subject, who, words, ago, cid):
                mid = store.add_message({'Channel': 'email', 'ExternalId': f'matrix-{s}-{ago}-{now:%H%M%S%f}', 'ConversationId': cid, 'FromName': who,
                                         'FromEmail': f"{who.split()[0].lower()}@vendor.example", 'Subject': subject, 'BodyText': words,
                                         'SentAt': at(minutes=ago), 'Status': 'filed'})
                store.add_route(mid, None, 'file', 0.9, 'for your information - nothing asked', []); return mid
            if s == 'fyi_thread':
                cid = f'email:matrix-thread-{now:%H%M%S%f}'
                for ago, words in ((1850, 'The Riverside site is moving to the new badge readers on Monday.'),
                                   (1830, 'Correction: the readers go in on Tuesday, not Monday.'), (1810, 'All three readers are in and tested.')):
                    fyi_mail('Badge reader rollout', 'Omar Keller', words, ago, cid)
            else:
                mid = fyi_mail('Statement of account - October', 'Payworth Billing', 'Your October statement is attached. Invoice 88213 is shown as open.',
                               1808, f'email:matrix-statement-{now:%H%M%S%f}')
                store.upsert_idea({'key': f'idea:matrix-statement-{now:%H%M%S%f}', 'kind': 'idea', 'sig': 'matrix-statement',
                                   'text': 'The Payworth statement still shows invoice 88213 open - worth checking it was paid.', 'action': {'mid': mid}},
                                  at(minutes=1807))
            from taskuary import funnel
            store.reconcile_processing_membership(); funnel.invalidate(); store._poke('feed-changed')
        elif s == 'news':
            tid = task('Site ops: who has the gate code', 'general', 'in_progress', Assignee='agent:general', Tags=terminal.SAVED)
            mail(tid, 'Gail Moreno', 'Alex, who has the new gate code for the side door?', ago=120)
            store.add_transcript(tid, f'matrix-{tid}', 'Looking for the gate code.\nThe handover sheet says Ray Colton has it.', agent='general', cwd='C:/work', brain='claude')
            store.add_comment(tid, 'general', 'agent', 'AGENT REPORT\nDetermination: Ray Colton has the gate code.\nActions: Read the handover sheet.\n'
                              'Summary: Ray Colton has it; Gail should ask him.')
            store._exec("UPDATE transcript SET CreatedAt=? WHERE TaskId=?", (at(minutes=60), tid))
            mail(tid, 'Gail Moreno', 'Ray is away this week - who else has it?', ago=5, subject='RE: About news')
        return {'taskId': tid}

    # ── THE ADVISOR AUDIT (2026-10-26): where the Advisor's words land on a task, by stage and drawer ─────────────────────────────────
    # `world` adds the stages the demo lacks, with the Advisor's REAL rule decisions where the app's facts make one: a late ask against a
    # counted usual (three answered threads), one thread on two open tasks (duplicate), an ask with no habit, an agent at work and one
    # that finished. `say` stands in for what only a model writes (a draft warning, a caution): the decision advisor.decide hands every
    # surface, with the label the row would draw, so the page under test reads it from /api/advice like any other. Invented people.
    said = {}
    from taskuary import advisor
    real_decide = advisor.decide

    # ...and it passes the SAME check a real answer does (advisor.checked, the judge's fix 3, 2026-10-26): a scripted Send under a draft
    # caution, a Try again nobody can press, Reply over a ready draft - refused and the next sensible move lit, exactly as the app would.
    # An agent at work is never advised over: the real decide answers before any model is read, and so does this
    def scripted_decide(st, key, preread=True):
        out = real_decide(st, key, preread)
        tgt = advisor.target_of(st, key)
        o = said.get(int(tgt[1])) if tgt and tgt[0] == 'task' else None
        if o is None or out.get('state') == 'working': return out
        item = advisor._item(st, *tgt, key=key)
        verbs = advisor.offered(st, item) if item else []
        from taskuary import rulebook
        r = rulebook.decide(st, item, verbs) if item else {'verb': out.get('verb'), 'line': '', 'evidence': []}
        state = o.get('state', out.get('state'))
        d = advisor.checked(st, item or {}, verbs, {**out, **o, 'key': key, 'state': state, 'verb': o.get('verb', out.get('verb')), 'evidence': [],
                            'kind': o.get('kind') or rulebook.KIND.get(state, 'other')}, {'verb': r['verb'], 'line': r['line'], 'evidence': list(r.get('evidence') or [])})
        lbl = advisor._label(verbs, d['verb'], item) if d['verb'] else ''
        return {**d, 'label': lbl, 'pill': lbl, 'scripted': True}
    advisor.decide = scripted_decide

    @app.post('/api/fixture/advisor/say')
    def advisor_say(body: dict):
        """{taskId, decision}: the Advisor's decision for that task from now on ({state, verb, line, by, kind}); null puts the real one back."""
        if set(body) != {'taskId', 'decision'} or not isinstance(body['taskId'], int): raise HTTPException(422, 'taskId and decision')
        d = body['decision']
        if d is None: said.pop(body['taskId'], None)
        else:
            if not isinstance(d, dict) or not set(d) <= {'state', 'verb', 'line', 'by', 'kind'}: raise HTTPException(422, 'state, verb, line, by, kind only')
            said[body['taskId']] = d
        advisor._emit(f"task:{body['taskId']}", 'task', body['taskId'])
        return {'ok': True}

    @app.post('/api/fixture/advisor/world')
    def advisor_world(body: dict):
        if body: raise HTTPException(422, 'this fixed fixture accepts only an empty object')
        from taskuary import workerstate as ws
        now = datetime.now()
        at = lambda **k: (now - timedelta(**k)).strftime('%Y-%m-%d %H:%M:%S')
        def msg(tid, who, email, subject, words, sent, cid, out=False):
            store.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': f'adv-{cid}-{sent}-{out}', 'ConversationId': cid,
                               'FromName': 'Alex Doyle' if out else who, 'FromEmail': 'alex@northwind.example' if out else email,
                               'Subject': subject, 'BodyText': words, 'SentAt': sent, 'Status': 'routed', **({'Direction': 'out'} if out else {})})
        # Erin's habit: three past asks the owner answered in about twenty minutes, then today's ask, five hours old and unanswered
        for n in range(3):
            old = store.create_task({'Title': f'Erin: vendor form {n + 1}', 'Kind': 'reply', 'Status': 'done', 'Source': 'email'}, 'router')
            msg(old, 'Erin Blake', 'erin@northwind.example', f'Vendor form {n + 1}', 'Can you sign this off?', at(days=10 + n), f'adv-erin-old-{n}')
            msg(old, 'Erin Blake', 'erin@northwind.example', f'RE: Vendor form {n + 1}', 'Signed.', at(days=10 + n, minutes=-20), f'adv-erin-old-{n}', out=True)
        late = store.create_task({'Title': 'Can you approve the Trainly renewal?', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
        msg(late, 'Erin Blake', 'erin@northwind.example', 'Trainly renewal', 'Alex, can you approve the Trainly renewal today?', at(hours=5), 'adv-erin-late')
        # ...and an ask from someone with no habit: no usual can be said of Omar
        plain = store.create_task({'Title': 'Which cost centre for the PhishGuard seats?', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
        msg(plain, 'Omar Keller', 'omar@northwind.example', 'PhishGuard seats', 'Which cost centre should the PhishGuard seats go on?', at(hours=5), 'adv-omar')
        # one thread on two open tasks: each is the same ask as the other
        dup1 = store.create_task({'Title': 'Spendly cards for the new site', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
        msg(dup1, 'Marcus Reed', 'marcus@northwind.example', 'Spendly cards', 'Can we get Spendly cards for the new site?', at(hours=7), 'adv-dup')
        dup2 = store.create_task({'Title': 'RE: Spendly cards', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
        msg(dup2, 'Marcus Reed', 'marcus@northwind.example', 'RE: Spendly cards', 'Following up on the Spendly cards.', at(hours=2), 'adv-dup')
        # an agent at work, and one that finished - REACHED this time (the judge: both stages had stayed a plain ask, so "never over a working
        # agent" was never tried): the working one has a live session the run's own events name (workerstate: working needs a live run), the
        # finished one its chat and its report, so the page draws its Result
        from taskuary import general, terminal
        work = store.create_task({'Title': 'Reconcile the Payworth September export', 'Kind': 'general', 'Status': 'in_progress', 'Source': 'email'}, 'router')
        msg(work, 'Paula Vance', 'paula@northwind.example', 'Payworth export', 'The September export does not tie out.', at(hours=3), 'adv-work')
        pane = _demo.Replay(store, work, 'Claude Code', lines=[('Reading the September export and the bank feed side by side...', 0)])
        terminal.SESSIONS[pane.sid] = pane
        ws.record(store, work, str(pane.sid), 'working', source='fixture')
        fin = store.create_task({'Title': 'Summarise the Trainly completion report', 'Kind': 'general', 'Status': 'in_progress', 'Source': 'email'}, 'router')
        msg(fin, 'Gail Moreno', 'gail@northwind.example', 'Trainly completions', 'Who is still missing the safety module?', at(hours=6), 'adv-fin')
        store.add_comment(fin, 'owner', general.USER_TYPE, 'Who is still missing the safety module?')
        store.add_comment(fin, 'assistant', general.ASSISTANT_TYPE, 'Four people are missing the safety module; the list is in the result.')
        store.add_comment(fin, 'general', 'agent', 'AGENT REPORT\nDetermination: four people are missing the safety module.\n'
                          'Actions: Read the Trainly completion report.\nSummary: The four names, with their sites.')
        ws.record(store, fin, f'adv-fin-{fin}', 'working', source='fixture')
        ws.record(store, fin, f'adv-fin-{fin}', 'finished', text='Four people are missing the safety module; the list is in the result.', source='fixture')
        # ...AND ERIN'S USUAL AS A LINE IN LEARNED.md, as the day's reflection writes it from the count (learn.answer_lines): the task's late
        # line reads that line and nothing else, so the task, LEARNED.md and Why? say one thing (the judge's problem 3)
        from taskuary import learn
        store.save_doc('learned', learn.answer_lines(store, store.get_doc('learned') or ''), 'reflect')
        return {'late': late, 'plain': plain, 'dup1': dup1, 'dup2': dup2, 'working': work, 'finished': fin}

    @app.post('/api/fixture/intake/arrive')
    def intake_arrive(body: dict):
        """{messages: [{msg, verdict}]}: each arrives through the real door (ingest.ingest_message) as one poll hands it over, triage scripted to
        the verdict given (None: no model call is expected). Invented senders only. Returns each outcome and the server's ms for it."""
        import json, time
        from unittest import mock
        from taskuary import ingest
        items = body.get('messages') if set(body) == {'messages'} else None
        if not isinstance(items, list) or not 0 < len(items) <= 20 or not all(isinstance(i, dict) and set(i) == {'msg', 'verdict'} for i in items):
            raise HTTPException(422, 'messages: 1-20 {msg, verdict}')
        out = []
        with mock.patch.object(ingest, '_spawn'):          # one wake-up per write, as a channel's poll makes them
            for i in items:
                calls, v = [], i['verdict']
                def llm(system, user, **k): calls.append(1); return json.dumps(v or {'intent': 'fyi', 'why': 'unscripted'})
                t = time.perf_counter()
                r = ingest.ingest_message(store, dict(i['msg']), llm=llm)
                out.append({**{k: r.get(k) for k in ('status', 'task_id', 'message_id')}, 'ms': round((time.perf_counter() - t) * 1000, 1), 'calls': len(calls)})
        store.reconcile_processing_membership()
        return {'out': out}

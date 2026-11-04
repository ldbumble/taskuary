"""Narrow synthetic source edits, installed only by the disposable browser server."""
import os, re
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
        '/api/fixture/task/pr-closeout',
        '/api/fixture/task/coding-saved',
        '/api/fixture/task/coding-live', '/api/fixture/task/coding-live/end',
        '/api/fixture/task/chat-burst',
        '/api/fixture/task/chat-saved',
        '/api/fixture/task/closed-asked',
        '/api/fixture/task/closeout-rounds',
        '/api/fixture/task/playbook-failed',
        '/api/fixture/general/canvas',
        '/api/fixture/general/rest',
        '/api/fixture/signin/link',
        '/api/fixture/signin/terminal-ask',
        '/api/fixture/browser/last-frame',
        '/api/fixture/browser/view', '/api/fixture/browser/paint',
        '/api/fixture/processing/arrive-during-next', '/api/fixture/processing/rerun',
        '/api/fixture/task/closed-elsewhere', '/api/fixture/task/live-agent',
        '/api/fixture/task/agent-draft', '/api/fixture/task/agent-word',
        '/api/fixture/advisor/world',
        '/api/fixture/advisor/say',
        '/api/fixture/intake/arrive',
        '/api/fixture/task/matrix',
        '/api/fixture/task/advisor-raised',
        '/api/fixture/task/long-chat',
        '/api/fixture/task/picture-mail',
        '/api/fixture/task/big-chat',
        '/api/fixture/task/group-chat',
        '/api/fixture/task/workstreams',
        '/api/fixture/advisor/report-idea',
        '/api/fixture/stress/seed', '/api/fixture/stress/clear',
        '/api/fixture/walk/world', '/api/fixture/walk/do', '/api/fixture/walk/keys', '/api/fixture/walk/big',
        '/api/fixture/day/away',
    })

    def fixture_refuse(method, path):
        # Only these test-installed, bounded database edits are extra allowances.
        # Every production route retains the original demo guard and socket guard.
        if method == 'POST' and path in fixture_paths:
            return ''
        # ...and a reply recorded as sent by a test's own channel (review_sent below): one numbered review, nothing more
        if method == 'POST' and re.fullmatch(r'/api/fixture/review/\d+/sent', path):
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
        # ...and the task's workstream picker: moving the fixture's task is the thing the workstream test checks
        if method == 'PUT' and re.fullmatch(r'/api/tasks/\d+/workstream', path):
            return ''
        return refuse(method, path)

    demo.refuse = fixture_refuse
    answer_paths = set()

    sync_token = [None]

    @app.post('/api/fixture/review/{rid}/sent')
    def review_sent(rid: int):
        """A reply the test's own channel answered as gone (send-stays-on-closeout): the review recorded as sent, as a real Send leaves it -
        so the close after it (concierge.close_after_send) finds nothing still waiting for a Send, and judges the rest as it would."""
        rv = store.get_review(rid)
        if not rv or rv.get('Status') not in ('pending', 'held'): raise HTTPException(409, 'no pending reply by that id')
        store.decide_review(rid, 'approved', rv.get('DraftText') or '', 'owner')
        return {'ok': True}

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

    @app.post('/api/fixture/task/pr-closeout')
    def pr_closeout(body: dict):
        """A task whose coding agent opened a pull request and finished: its close-out (merge northwind/ledger#42) waits beside the reply to the
        person who asked, one decision on Close out's card. Nothing reaches GitHub - the test answers the card's read and its press. Invented people."""
        if body: raise HTTPException(422, 'no fields')
        import json
        tid = store.create_task({'Title': 'Ledger export drops the 4100 accounts', 'Kind': 'coding', 'Status': 'open', 'Source': 'github'}, 'router')
        conv = f'github:northwind/ledger#42@{tid}'
        mid = store.add_message({'TaskId': tid, 'Channel': 'github', 'ExternalId': conv, 'ConversationId': conv, 'FromName': 'Gail Moreno',
                                 'Subject': 'Ledger export drops the 4100 accounts', 'Status': 'routed',
                                 'BodyText': 'The nightly ledger export is missing the 4100 accounts - can you have a look?'})
        reply = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'reply', 'Status': 'pending',
                                  'DraftText': 'Fixed - the export reads the 4100 accounts from the new chart again.'})
        co = store.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'DraftText': json.dumps(
            {'action': 'merge_pr', 'repo': 'northwind/ledger', 'number': 42, 'closeout': True, 'text': 'Read the 4100 accounts from the new chart'})})
        return {'taskId': tid, 'reply': reply, 'closeout': co}

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

    @app.post('/api/fixture/task/closeout-rounds')
    def closeout_rounds(body: dict):
        """A task closed out more than once (the owner, 2026-11-01): Erin asked, the owner replied and it closed; with `rounds` 3 she wrote
        again and it was closed with a note, nothing sent; then a question from her on the same thread reopened it, through the real door
        with triage scripted. Each round's reply, close and reopen happened, and is then dated back a day apart. `draft`: a reply waits for
        Send on the question. Invented people."""
        if set(body) - {'rounds', 'draft'} or body.get('rounds', 2) not in (2, 3) or not isinstance(body.get('draft', False), bool):
            raise HTTPException(422, 'rounds is 2 or 3, draft a boolean')
        import json
        from unittest import mock
        from taskuary import concierge, ingest
        n, conv, now = body.get('rounds', 2), f'fixture-rounds-{datetime.now():%H%M%S%f}', datetime.now()
        at = lambda days, h=9, m=0: (now - timedelta(days=days)).replace(hour=h, minute=m, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
        tid = store.create_task({'Title': 'Missing ledger accounts', 'Kind': 'task', 'Status': 'open', 'Source': 'email'}, 'router')
        def erin(i, words, sent):
            return store.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': f'{conv}-{i}', 'ConversationId': conv, 'FromName': 'Erin Blake',
                                      'FromEmail': 'erin@northwind.example', 'Subject': 'RE: Missing ledger accounts' if i > 1 else 'Missing ledger accounts',
                                      'BodyText': words, 'SentAt': sent, 'Status': 'routed'})
        def closed(when):        # ...the close just made, dated back: the ledger's row and the audit's reopen before it
            store._exec("UPDATE outcome SET At=? WHERE Id=(SELECT MAX(Id) FROM outcome WHERE Kind='task.closed' AND TargetId=?)", (when, tid))
            store._exec("UPDATE comment SET CreatedAt=? WHERE TaskId=? AND Body LIKE 'Closed out: %' AND CreatedAt>?", (when, tid, when))
        m1 = erin(1, 'Some accounts are missing from the ledger pull - can you check which ones?', at(n, 9))
        rid = store.add_review({'TaskId': tid, 'MessageId': m1, 'Kind': 'reply', 'DraftText': 'They were folded into 4100 when the chart changed.', 'Status': 'pending'})
        store.decide_review(rid, 'approved', 'They were folded into 4100 when the chart changed. I will send the mapping.', 'owner')
        store._exec('UPDATE review SET CreatedAt=?, DecidedAt=? WHERE ReviewId=?', (at(n, 12, 30), at(n, 12, 36), rid))
        concierge.close_task(store, tid, 'owner'); closed(at(n, 12, 37))
        if n == 3:
            erin(2, 'Thanks - could you send the mapping when you have it?', at(2, 8, 15))
            store.update_task(tid, {'Status': 'open'}, 'router')
            store._exec("UPDATE audit SET CreatedAt=? WHERE Id=(SELECT MAX(Id) FROM audit WHERE EntityType='task' AND EntityId=? AND Action='reopened')", (at(2, 8, 16), tid))
            store.add_comment(tid, 'owner', 'human', 'Closed out: Walked Erin through the mapping on a call.')
            concierge.close_task(store, tid, 'owner'); closed(at(2, 15, 5))
        said = {'intent': 'reply_only', 'why': 'Erin asks Alex directly', 'title': 'Missing ledger accounts', 'asks_owner': True,
                'summary': 'Erin Blake asks which of the 4100 accounts moved in the change.'}
        with mock.patch.object(ingest, '_spawn'):
            out = ingest.ingest_message(store, {'external_id': f'{conv}-q', 'channel': 'email', 'from_email': 'erin@northwind.example',
                                                'from_name': 'Erin Blake', 'conversation_id': conv, 'subject': 'RE: Missing ledger accounts',
                                                'body': 'One more - which of the 4100 accounts moved in the change?',
                                                'sent_at': (now - timedelta(minutes=20)).strftime('%Y-%m-%d %H:%M:%S')},
                                         llm=lambda system, user, **k: json.dumps(said))
        if out.get('task_id') != tid: raise HTTPException(409, f'the question did not join its task: {out}')
        # ...the draft the question opened (its drafter is the job _spawn would run), written; or one, where it opened none
        if body.get('draft'):
            words, rv = '4101 and 4102 moved; the rest stayed where they were.', store.pending_review(tid, live_only=False)
            if rv: store._exec('UPDATE review SET DraftText=? WHERE ReviewId=?', (words, rv['ReviewId']))
            else: store.add_review({'TaskId': tid, 'MessageId': out['message_id'], 'Kind': 'reply', 'Status': 'pending', 'DraftText': words})
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

    @app.post('/api/fixture/advisor/report-idea')
    def advisor_report_idea(body: dict):
        """Three of Alex's agent runs ending on one error, counted by the Advisor's own detector (reportideas.ideas) and raised as its
        "Report this?" line - the owner, 2026-11-01: "yes the advisor can suggest fixes/features"."""
        if body: raise HTTPException(422, 'this fixed fixture accepts only an empty object')
        from taskuary import reportideas
        now = datetime.now()
        for i in range(3):
            tid = store.create_task({'Title': f'Reconcile the vendor batch {i + 1}', 'Kind': 'general', 'Status': 'open'}, 'owner')
            rid = store.start_run(tid, 'coding', 'reconcile it', 'owner')
            store._exec("UPDATE run SET Status='error', LastError=?, FinishedAt=? WHERE RunId=?",
                        (f"KeyError: 'session' in the run loop (attempt {i + 1})", (now - timedelta(hours=i + 1)).isoformat(' ', 'seconds'), rid))
        lines = [x for x in reportideas.ideas(store, now) if x['kind'] == 'report']
        if not lines: raise HTTPException(409, 'the detector raised nothing')
        rows = [store.upsert_idea(x, now.isoformat(' ', 'seconds')) for x in lines]
        return {'ideas': [r['IdeaId'] for r in rows], 'text': lines[0]['text']}

    @app.post('/api/fixture/task/workstreams')
    def workstreams_task(body: dict):
        """Alex's three workstreams (the owner, 2026-11-01) and Omar's bug report from the Ledger app's tester, placed there by its people -
        the task's picker shows it and moves it."""
        if body: raise HTTPException(422, 'this fixed fixture accepts only an empty object')
        from taskuary import workstreams
        workstreams.save(store, [{'name': 'Northwind finance systems', 'domains': ['northwind.example']},
                                 {'name': 'Ledger app', 'people': ['omar@ledger.example']}, {'name': 'Personal', 'personal': True}])
        tid = store.create_task({'Title': 'Export button greyed in the Ledger app', 'Kind': 'task', 'Status': 'open', 'Source': 'email',
                                 'Summary': 'Omar Keller says the export button is greyed out.'}, 'router')
        mid = store.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': f'fixture-ws-{tid}', 'FromName': 'Omar Keller',
                                 'FromEmail': 'omar@ledger.example', 'Subject': 'Export greyed', 'BodyText': 'The export button is greyed out.',
                                 'SentAt': datetime.now().isoformat(' ', 'seconds'), 'Status': 'routed'})
        workstreams.stamp_message(store, mid)
        return {'taskId': tid, 'workstream': workstreams.of_task(store, tid)}

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

    @app.post('/api/fixture/task/picture-mail')
    def picture_mail(body: dict):
        """Three mails on one task: one that is only a pasted picture (cid:, a tiny PNG made here), one that is only a picture on the
        sender's site, and one whose "View report" button is a link (the owner, 2026-11-03: "entire email was a image it showed nothing",
        "hyper links in fyi email like view report are not coming thru"). Invented sender and addresses."""
        if body: raise HTTPException(422, 'this fixed fixture accepts only an empty object')
        import json, struct, zlib
        from taskuary.artifacts import attachment_dir
        chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
        png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 2, 0, 0, 0)) + \
            chunk(b'IDAT', zlib.compress(b'\x00' + b'\xff\x00\x00' * 2 + b'\x00' + b'\x00\x00\xff' * 2)) + chunk(b'IEND', b'')
        tid = store.create_task({'Title': 'October numbers from Vendor', 'Kind': 'task', 'Status': 'open', 'Source': 'email',
                                 'Summary': 'The October numbers came in.'}, 'router')
        start, mids = datetime.now() - timedelta(hours=1), []
        for i, (subj, text, meta) in enumerate([('October numbers', '[image: October numbers]', None),
                                                ('October banner', '[remote image: banner.png]', None),
                                                ('October report', 'Your October report is ready.\nView report',
                                                 {'links': [['View report', 'https://reports.vendor.example/r/9?u=alex']]})]):
            mids.append(store.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': f'fixture-pic-{tid}-{i}', 'FromName': 'Reports at Vendor',
                                           'FromEmail': 'reports@vendor.example', 'Subject': subj, 'BodyText': text, 'Status': 'routed',
                                           'MailMetaJson': json.dumps(meta) if meta else None,
                                           'SentAt': (start + timedelta(minutes=5 * i)).isoformat(' ', 'seconds')}))
        f = attachment_dir(mids[0]) / '0-image001.png'
        f.write_bytes(png)
        store.add_attachment({'MessageId': mids[0], 'ExternalId': f'fixture-pic-att-{tid}', 'Name': 'image001.png', 'ContentType': 'image/png',
                              'Size': len(png), 'ContentId': 'image001.png@01DB', 'Inline': 1, 'Path': str(f)})
        return {'taskId': tid, 'mids': mids}

    @app.post('/api/fixture/task/big-chat')
    def big_chat(body: dict):
        """A BIG task (the owner, 2026-11-01: a rail row clicked drew a spinner in an empty frame for seconds - "this still happens"): a
        WhatsApp group of 1,500 lines from three people and the owner on one task, a photo every fifth line, drafts, notes, twenty agent
        runs and their saved sessions. Its read judged where every line came from, one line at a time (tests/test_big_task_opens_fast.py)."""
        if body: raise HTTPException(422, 'this fixed fixture accepts only an empty object')
        tid = store.create_task({'Title': 'Site ops: the walk-in cooler', 'Kind': 'reply', 'Status': 'open', 'Source': 'whatsapp',
                                 'Summary': 'The site team needs the walk-in cooler repair booked.'}, 'router')
        start, who = datetime.now() - timedelta(hours=30), (('Ray Colton', '15550003@s.whatsapp.net'), ('Gail Moreno', '15550002@s.whatsapp.net'),
                                                            ('Paula Vance', '15550004@s.whatsapp.net'))
        for j in range(1500):
            mine = j % 4 == 3
            name, addr = ('Alex Doyle', 'alex@northwind.example') if mine else who[j % 4 % 3]
            mid = store.add_message({'TaskId': tid, 'Channel': 'whatsapp', 'SourceName': 'Site ops', 'ExternalId': f'fixture-big-{tid}-{j}',
                                     'ConversationId': f'fixture-big-{tid}', 'FromName': name, 'FromEmail': addr, 'Direction': 'out' if mine else 'in',
                                     'BodyText': f'Cooler note {j + 1}: ' + ('the compressor is cycling again' if j % 2 else 'the engineer can come Thursday') * 4,
                                     'SentAt': (start + timedelta(minutes=j)).isoformat(' ', 'seconds'), 'Status': 'context' if mine else 'routed'})
            store.add_route(mid, tid, 'create' if j == 0 else 'attach', None, 'same chat', [], 'triage', verdict={'intent': 'reply_only', 'summary': 'the cooler'})
            if j % 5 == 0: store.add_attachment({'MessageId': mid, 'Name': f'cooler{j}.jpg', 'ContentType': 'image/jpeg'})
        for k in range(30):
            store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'sent' if k else 'pending', 'Reason': 'needs a reply',
                              'DraftText': f'Thanks Paula - booking the engineer for Thursday ({k}).'})
        for k in range(100): store.add_comment(tid, 'general', 'agent', f'Note {k}: checked the service log for the cooler.')
        for k in range(20):
            rid = store.start_run(tid, 'general', 'Find the earliest engineer slot for the cooler.', 'owner'); store.update_run(rid, {'Status': 'done'}, finished=True)
            store.add_transcript(tid, f'fixture-big-{tid}-{k}', 'Looked up the engineer rota.\n' * 4000, agent='general', ext_id=f'fixture-big-ext-{k}', brain='claude')
        store.reconcile_processing_membership()
        return {'taskId': tid}

    @app.post('/api/fixture/task/group-chat')
    def group_chat(body: dict):
        """A WhatsApp group's 87 lines from three people on one reply task (the owner, 2026-11-02): Came from as the slim column beside an open
        Close out drew its message lines down the whole spine, and its moves (Remind me, Watch it, Not a task) stood on top of them. `live`: an
        agent live on it too, its session ended by coding-live/end - the spines slim beside it, then full again."""
        if set(body) - {'live'} or body.get('live', False) not in (True, False): raise HTTPException(422, 'only live, true or false, is accepted')
        tid = store.create_task({'Title': 'Site ops: the loading bay rota', 'Kind': 'reply', 'Status': 'open', 'Source': 'whatsapp',
                                 'Summary': 'The site team wants the loading bay rota for next week settled.'}, 'router')
        start, who = datetime.now() - timedelta(hours=8), ('Ray Colton', 'Gail Moreno', 'Paula Vance')
        for i in range(87):
            store.add_message({'TaskId': tid, 'Channel': 'whatsapp', 'SourceName': 'Site ops', 'ExternalId': f'fixture-group-{tid}-{i}',
                               'ConversationId': f'fixture-group-{tid}', 'FromName': who[i % 3],
                               'BodyText': f'Rota note {i + 1}: ' + ('who takes the early deliveries on Monday' if i % 2 else 'the forklift is booked for the afternoon'),
                               'SentAt': (start + timedelta(minutes=5 * i)).isoformat(' ', 'seconds'), 'Status': 'routed'})
        if body.get('live'):
            from taskuary import terminal
            store.add_transcript(tid, f'fixture-group-{tid}', 'Reading the rota thread.\nRay Colton takes Monday.', agent='general', cwd='C:/work', brain='claude')
            store.add_comment(tid, 'general', 'agent', 'AGENT REPORT\nSummary: Ray Colton takes the Monday deliveries; the group should be told.')
            pane = live_panes[tid] = _demo.Replay(store, tid, 'Claude Code', lines=[('Reading the rota thread...', 0), ('Who takes Monday?', 0.1)])
            terminal.SESSIONS[pane.sid] = pane
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
        `mine`: a task the owner made in the Assistant - nobody sent it, so nobody is owed a reply. `writing`: its write-up still running.
        `twice`: an earlier run two hours before this one, with its own report - the Agent pane keeps it under the latest (2026-10-29)."""
        if set(body) - {'mine', 'writing', 'twice'} or not all(isinstance(v, bool) for v in body.values()):
            raise HTTPException(422, 'only the booleans mine, writing and twice are accepted')
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
        if body.get('twice'):
            then = (datetime.now() - timedelta(hours=2)).isoformat(' ', timespec='seconds')
            store.add_transcript(tid, f'fixture-{tid}-1', "Reading the census sync.\n> pytest tests/test_census_sync.py -q\n1 failed, 8 passed",
                                 agent='coding', cwd='C:/work/org-app', brain='codex')
            cid = store.add_comment(tid, 'coding', 'agent', 'AGENT REPORT\nSummary: Found where the census run stops; no fix yet.\n\nLAST MESSAGE\n'
                                    'The run stops at the first site with no manager. Not fixed yet - the test reproduces it.')
            store._exec('UPDATE transcript SET CreatedAt=? WHERE Sid=?', (then, f'fixture-{tid}-1'))
            store._exec('UPDATE comment SET CreatedAt=? WHERE CommentId=?', (then, cid))
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

    @app.post('/api/fixture/processing/rerun')
    def rerun_row(body: dict):
        """A row that RE-RAN while it was on the table (a nightly report's new run): its members move to a new item and the old item
        redirects there, so the rail's row has a new key and answers to the old one as an alias - the card on the page still says the
        old key until the page reads its rail again (the re-run's own wake-up, poked here)."""
        if set(body) != {'key'} or not str(body['key']).startswith('processing:'):
            raise HTTPException(422, 'one processing key is required')
        import uuid
        from taskuary import funnel
        old, new = body['key'][len('processing:'):], f'pi_{uuid.uuid4().hex}'
        row = store._one('SELECT Kind FROM processing_item WHERE ItemId=? AND RedirectItemId IS NULL', (old,))
        if not row: raise HTTPException(404, 'no such live item')
        now = datetime.now().isoformat(' ')
        store._exec('INSERT INTO processing_item (ItemId,Kind,CreatedAt,UpdatedAt) VALUES (?,?,?,?)', (new, row['Kind'], now, now))
        store._exec('UPDATE processing_member SET ItemId=? WHERE ItemId=? AND RetiredAt IS NULL', (new, old))
        store._exec('UPDATE processing_item SET RedirectItemId=?,ContextRevision=NULL,ViewRevision=NULL,UpdatedAt=? WHERE ItemId=?', (new, now, old))
        funnel.invalidate(); store._poke('feed-changed')
        return {'old': body['key'], 'new': f'processing:{new}'}

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

    # THE WALK TABLE'S WORLD (tests/walkworld.py): the rows the Python runner walks, laid out on this demo, and the moves the table makes
    # somewhere other than the desk - an arrival, a close elsewhere, an agent closing its own task, a row read, the phone - so both runners
    # walk one world
    import sys
    from pathlib import Path
    tests_dir = str(Path(__file__).resolve().parents[2] / 'tests')
    if tests_dir not in sys.path: sys.path.insert(0, tests_dir)
    import walkworld
    world = {}

    def walk_keys():
        from taskuary import funnel, railwalk
        funnel.invalidate()
        rows, peek = walkworld.rows(store), railwalk.peek(store)
        return {'keys': {sym: walkworld.key_of(store, world, sym, rows) for sym in world},
                'on': railwalk.on(store), 'walk': {k: v for k, v in peek.items() if k != 'below'}, 'below': peek.get('below')}

    @app.post('/api/fixture/walk/world')
    def walk_world(body: dict):
        if body: raise HTTPException(422, 'this fixed fixture accepts only an empty object')
        from taskuary import funnel, railwalk
        world.clear(); world.update(walkworld.build(store))
        railwalk.reset(store); funnel.invalidate()
        return walk_keys()

    @app.post('/api/fixture/walk/do')
    def walk_do(body: dict):
        verb, sym = body.get('verb'), body.get('sym')
        if verb not in ('arrive', 'close-elsewhere', 'agent-closes', 'watch', 'read', 'phone start', 'phone next') \
                or (sym is not None and not re.fullmatch(r'[A-Z]\d', str(sym))):
            raise HTTPException(422, 'a table verb and a symbol')
        from taskuary import concierge, funnel, railwalk, remote_assistant
        if verb == 'arrive': walkworld.arrive(store, world, sym)
        elif verb == 'close-elsewhere': walkworld.close_elsewhere(store, world, sym)
        elif verb == 'agent-closes': walkworld.agent_closes(store, world, sym)
        elif verb == 'watch': walkworld.watch(store, world, sym)
        elif verb == 'read':                          # ...a row the demo's own passes took off already is read already
            key = walkworld.key_of(store, world, sym)
            if key: funnel.settle(store, key, 'surfaced', 'owner', read=True); walkworld.reconcile(store)
        elif verb == 'phone start': remote_assistant.walk(store, 'owner', opener=False)
        else:
            on = railwalk.on(store)
            with concierge.delivering(concierge.PHONE): remote_assistant.run_act(store, {'t': 'next'}, {'key': on} if on else None, 'owner')
        if verb.startswith('phone'):                  # ...and the desk hears of it as it hears a phone turn end (remote_assistant.respond)
            from taskuary import live
            live.emit(live.CHAT, thinking=False, channel='telegram')
        return walk_keys()

    # THE STRESS WALK'S WORLD (browser/stress-walk-*): the demo's rail cleared and laid out big - or as one row - from invented people, so
    # Next, Back and the row clicks can be hammered over a long rail. Mixed kinds: reply drafts, agent tasks, goals, plain asks, meetings,
    # reports, FYI in batches and Advisor ideas.
    @app.post('/api/fixture/walk/big')
    def walk_big(body: dict):
        n = {k: body.get(k, d) for k, d in (('tasks', 100), ('reports', 15), ('fyi', 30), ('ideas', 4), ('meetings', 3))}
        if set(body) - set(n) or not all(type(v) is int and 0 <= v <= 200 for v in n.values()): raise HTTPException(422, 'tasks, reports, fyi, ideas, meetings: 0-200')
        from taskuary import assistant, funnel, railwalk
        from taskuary.testing import Factory
        walkworld.clear(store)
        world.clear()
        f, now = Factory(store), datetime.now()
        f.actor = 'triage'
        at = lambda m: (now - timedelta(minutes=m)).strftime('%Y-%m-%d %H:%M:%S')
        people = [('Erin Blake', 'erin'), ('Gail Moreno', 'gail'), ('Paula Vance', 'paula'), ('Ray Colton', 'ray'), ('Marcus Reed', 'marcus'), ('Omar Keller', 'omar')]
        asks = ['the June variance', 'the Payworth export', 'badges for the new starters', 'the Trainly seats', 'the Spendly card feed', 'the portal upgrade',
                'the PhishGuard dates', 'the fixed asset register', 'the AP ageing', 'the vendor form']
        span = max(1, n['tasks'] + n['reports'] + n['fyi'] + n['ideas'])
        tids = []
        for i in range(n['tasks']):
            who, user = people[i % len(people)]
            kind = ('reply', 'general', 'goal', 'general')[i % 4]
            title = f"{('Reply about', 'Look into', 'Goal: finish', 'Sort out')[i % 4]} {asks[i % len(asks)]} #{i + 1}"
            status = 'in_progress' if i % 4 == 1 and i % 8 == 1 else 'open'
            tid = f.task(title=title, status=status, kind=kind)
            mid = f.message(task_id=tid, subject=title, from_name=who, from_email=f'{user}@northwind.example', sent_at=at(3 * span - i),
                            body=f'{title} - can you take a look?', conversation_id=f'stress:T{i}')
            f.route(mid, tid, 'create', 'real work')
            store._exec('UPDATE task SET CreatedAt=? WHERE TaskId=?', (at(3 * span - i), tid))
            if kind == 'reply': f.review(tid, mid, draft='Thanks - I will have it to you by Friday.')
            elif kind == 'goal': store.set_task_checklist(tid, ['Gather the numbers', 'Check with the site', 'Send the summary'], 'triage')
            elif status == 'in_progress': f.run(tid, agent='general')
            tids.append(tid)
        if n['meetings']:
            start = now.replace(second=0, microsecond=0)
            assistant._AGENDA.update(days=7, at=now.timestamp() + 10 ** 9, events=[{
                'start': (start + timedelta(minutes=20 + 45 * k)).strftime('%Y-%m-%d %H:%M'), 'end': (start + timedelta(minutes=50 + 45 * k)).strftime('%Y-%m-%d %H:%M'),
                'subject': f'Northwind check-in {k + 1}', 'all_day': False, 'status': 'busy', 'where': '', 'mailbox': 'demo', 'organizer': 'Gail Moreno',
                'who': ['Gail Moreno'], 'about': '', 'join': '', 'link': ''} for k in range(n['meetings'])])
        else: assistant._AGENDA.update(days=7, at=now.timestamp() + 10 ** 9, events=[])
        for i in range(n['reports']):
            r = f.report_row(title=f'Northwind report {i + 1}')
            store._exec('UPDATE message SET SentAt=? WHERE MessageId=?', (at(2 * span - i), r.mid))
        for i in range(n['ideas']):
            idea = store.upsert_idea({'key': f'idea:stress-{i}', 'kind': 'idea', 'sig': f'stress-{i}', 'text': f'Payworth renewal idea {i + 1}: nobody has asked for the terms.',
                                      'action': {'type': 'note', 'whose': 'the owner', 'suggest': 'Ask Payworth for the renewal terms.'}}, at(span - i))
            store._exec('UPDATE idea SET FirstSeen=?, LastSaid=? WHERE IdeaId=?', (at(span - i), at(span - i), idea['IdeaId']))
            store.set_idea_action(idea['IdeaId'], {'type': 'note', 'whose': 'the owner', 'suggest': 'Ask Payworth for the renewal terms.',
                                                   'triage': {'intent': 'fyi', 'kind': None, 'why': 'a note for you', 'sig': idea.get('Sig') or '',
                                                              'at': at(span - i), 'linked_task': None, 'error': None}})
        for i in range(n['fyi']):
            mid = f.message(task_id=None, status='filed', subject=f'Northwind floor notice {i + 1}', from_name='Paula Vance', from_email='paula@northwind.example',
                            sent_at=at(span - n['ideas'] - i), body=f'Floor notice {i + 1}: nothing to do.', conversation_id=f'stress:F{i}')
            f.route(mid, None, 'file', 'information, nothing to do')
        store.set_setting('fyi_batch', '4', 'owner')
        walkworld.reconcile(store); railwalk.reset(store); funnel.invalidate(); store._poke('feed-changed')
        return {'tasks': tids, 'pile': [i['key'] for i in funnel.pile(store, force=True)['items']]}

    @app.post('/api/fixture/day/away')
    def day_away(body: dict):
        """The owner was last here seventeen hours ago, so the page's next arrive draws the day's opener (welcome.due's gap), and the
        page is told to arrive now, past its minute's throttle - as the end of the startup catch-up tells it."""
        if body: raise HTTPException(422, 'this fixed fixture accepts only an empty object')
        from taskuary import live, welcome
        welcome._HELD.clear(); welcome._CATCHUP.clear()
        gone = (datetime.now() - timedelta(hours=17)).strftime('%Y-%m-%d %H:%M:%S')
        for k in (welcome.SEEN_KEY, welcome.CLOSED_KEY): store.set_setting(k, gone, 'fixture')
        live.emit(live.ARRIVE)
        return {'away_since': gone}

    @app.post('/api/fixture/walk/keys')
    def walk_keys_now(body: dict): return walk_keys()

    @app.post('/api/fixture/task/closed-elsewhere')
    def closed_elsewhere(body: dict):
        """The task on the table closed somewhere else - the phone, the Tasks page - so the rail's next read says it is gone and the
        table clears under whatever the page was doing (the owner, 2026-10-26: Next said "The list moved while that was loading")."""
        if set(body) != {'task_id'} or type(body['task_id']) is not int: raise HTTPException(422, 'exact task_id is required')
        from taskuary import concierge, funnel
        if not concierge.close_task(store, body['task_id'], 'owner'): raise HTTPException(409, 'that task was not open')
        store.reconcile_processing_membership(); funnel.invalidate()
        return {'closed': body['task_id']}

    @app.post('/api/fixture/task/live-agent')
    def live_agent(body: dict):
        """An agent live on the task, at its prompt and waiting on the owner (send-live-agent-stays): a recorded pane in the sessions, its
        run's own ask recorded, as a CLI's Stop hook leaves it - the shape a Send closed under (the owner, 2026-11-01). `working`: still mid-turn,
        nothing asked (agent-draft-popup)."""
        if set(body) - {'working'} != {'task_id'} or type(body['task_id']) is not int or type(body.get('working', False)) is not bool:
            raise HTTPException(422, 'exact task_id is required; working is a boolean')
        from taskuary import funnel, terminal, workerstate as ws
        from taskuary import demo as _d
        tid = body['task_id']
        if not store.get_task(tid): raise HTTPException(404, 'no such task')
        # ...a working one is still typing: its next line is far off, so the recording stays mid-turn for the test's whole length
        pane = _d.Replay(store, tid, 'Claude Code', lines=[('Checked the invoice against the purchase order: the totals match.', 0)]
                         + ([('Filing the receipt with the purchase order...', 3600)] if body.get('working') else []))
        terminal.SESSIONS[pane.sid] = pane
        if not body.get('working'): ws.record(store, tid, str(pane.sid), 'input_needed', text='Should I also file the receipt with the purchase order?', source='hook')
        funnel.invalidate()
        return {'taskId': tid, 'sid': pane.sid}

    @app.post('/api/fixture/task/agent-draft')
    def agent_draft(body: dict):
        """The task's agent saved a message for the person who asked - `taskuary --reply` (wrapup.agent_reply): the pending draft marked as the
        agent's, waiting on the owner's Send (agent-draft-popup). `answered`: the owner then answered that person themselves, outside Taskuary -
        their reply on the thread, newer than the message the draft answers. Invented words only."""
        if set(body) - {'answered'} != {'task_id', 'text', 'agent'} or type(body['task_id']) is not int                 or not all(isinstance(body.get(k, 'x'), str) and 0 < len(body.get(k, 'x')) < 2000 for k in ('text', 'agent', 'answered')):
            raise HTTPException(422, 'exact task_id, text and agent are required; answered is optional')
        import json
        from taskuary import funnel, wrapup
        out = wrapup.agent_reply(store, body['task_id'], body['text'], body['agent'])
        if not out.get('review_id'): raise HTTPException(409, f"the agent's draft was refused: {out.get('why') or out}")
        if body.get('answered'):
            m = store.get_message(out['message_id']) or {}
            store.add_message({'TaskId': body['task_id'], 'Channel': m.get('Channel') or 'email', 'ExternalId': f"fixture-answered-{out['review_id']}",
                               'ConversationId': m.get('ConversationId'), 'SourceName': 'alex@northwind.example', 'FromName': 'Alex Doyle',
                               'FromEmail': 'alex@northwind.example', 'Subject': f"RE: {m.get('Subject') or ''}", 'BodyText': body['answered'],
                               'OwnText': body['answered'], 'Direction': 'out', 'Status': 'context', 'RecipientsJson': json.dumps({'to': [m.get('FromEmail') or '']}),
                               # ...a minute on, so a message that arrived this same second is still the older one
                               'SentAt': (datetime.now() + timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S')})
        funnel.invalidate()
        return {'reviewId': out['review_id']}

    @app.post('/api/fixture/task/agent-word')
    def agent_word(body: dict):
        """The live agent's own word changes mid-run (agent-draft-popup): `working` again, a pause the run reports as `input_needed`, or `ended` -
        and the task-changed poke a running agent's page re-reads on, as the server sends it every few seconds while an agent works."""
        if set(body) != {'task_id', 'word'} or type(body['task_id']) is not int or body['word'] not in ('working', 'input_needed', 'ended'):
            raise HTTPException(422, 'exact task_id and word (working | input_needed | ended) are required')
        from taskuary import funnel, live, terminal, workerstate as ws
        tid = body['task_id']
        pane = next((p for p in terminal.SESSIONS.values() if getattr(p, 'task_id', None) == tid and p.alive), None)
        if pane is None: raise HTTPException(404, 'no live agent on that task')
        if body['word'] == 'ended':                                         # ...or the agent stops: the session closes, as a CLI that exits
            pane.close()
            for loop, q in list(getattr(pane, 'subs', [])): loop.call_soon_threadsafe(q.put_nowait, None)
            funnel.invalidate(); live.emit('task-changed', task_id=tid)
            return {'taskId': tid, 'word': 'ended'}
        if hasattr(pane, 'busy'): pane.busy = body['word'] == 'working'   # a general agent's conversation: its turn in flight, or answered
        ws.record(store, tid, str(pane.sid), body['word'], text='Should I also file the receipt?' if body['word'] == 'input_needed' else '', source='hook')
        funnel.invalidate(); live.emit('task-changed', task_id=tid)
        return {'taskId': tid, 'word': body['word']}

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

    live_panes = {}

    @app.post('/api/fixture/task/coding-live')
    def coding_live(body: dict):
        """A coding task whose agent is live and waiting on the owner, with `runs` earlier runs kept under its terminal, each with its own
        report (the owner, 2026-11-01: eight of them took the terminal's room). Invented repository and people."""
        n = body.get('runs')
        if set(body) != {'runs'} or not isinstance(n, int) or not 0 <= n <= 20: raise HTTPException(422, 'runs, 0 to 20, is required')
        from taskuary import terminal
        tid = store.create_task({'Title': 'org/app#412 roster export drops the night shift', 'Kind': 'coding', 'Status': 'in_progress',
                                 'Source': 'assistant', 'Assignee': 'agent:coding', 'Tags': 'repo:org/app'}, 'router')
        for i in range(1, n + 1):
            then = (datetime.now() - timedelta(hours=2 * (n - i + 1))).isoformat(' ', timespec='seconds')
            sid = f'fixture-live-{tid}-{i}'
            store.add_transcript(tid, sid, f'Run {i} on the roster export.\n> pytest tests/test_roster.py -q\n{i} passed', agent='coding', cwd='C:/work/org-app', brain='claude')
            cid = store.add_comment(tid, 'coding', 'agent', f'AGENT REPORT\nSummary: Pass {i} on the roster export; Erin Blake checks the night shift.\n\nLAST MESSAGE\nPass {i} done.')
            store._exec('UPDATE transcript SET CreatedAt=? WHERE Sid=?', (then, sid))
            store._exec('UPDATE comment SET CreatedAt=? WHERE CommentId=?', (then, cid))
        pane = live_panes[tid] = _demo.Replay(store, tid, 'Claude Code', lines=[('Reading the roster export...', 0), ('Which shift file should I use?', 0.1)])
        terminal.SESSIONS[pane.sid] = pane
        return {'taskId': tid, 'sid': pane.sid}

    @app.post('/api/fixture/task/coding-live/end')
    def coding_live_end(body: dict):
        "...and its agent stops: the session closes, as a CLI that exits"
        if set(body) != {'taskId'} or body['taskId'] not in live_panes: raise HTTPException(422, 'the taskId of a coding-live task is required')
        pane = live_panes.pop(body['taskId']); pane.close()
        for loop, q in list(pane.subs): loop.call_soon_threadsafe(q.put_nowait, None)   # the exit marker a real pty's watchers get
        return {'ended': True}

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

    # ── THE BROWSER VIEW IN THE AGENT'S CANVAS (browser/browser-view, 2026-10-28) ───────────────────────────────────────────────────────
    # An agent-browser session with no Chrome and no socket: browserview.state says it is open on an invented sign-up page, the relay sends
    # that page's frame (the test draws it) and keeps what the owner's mouse and keys send, and a held act's Approve "runs" here. The agent
    # is a conversation session whose turns are recorded, not run - what it was told is what the test reads.
    from taskuary import browsergate as _bg, browserview as _bv, general as _gen
    VIEW, told, view_sid = {}, {}, {}
    _state, _relay, _run = _bv.state, _bv.relay, _bg._run

    def view_state(sid, fresh=False):
        v = VIEW.get(str(sid))
        return {'open': v['open'], 'url': v['url'] if v['open'] else '', 'port': 0} if v else _state(sid, fresh)

    async def view_relay(ws, sid):
        import json
        v = VIEW.get(str(sid))
        if not v: return await _relay(ws, sid)
        if not v['open']: return await ws.close(code=4404)
        await ws.accept()
        frame = json.dumps({'type': 'frame', 'seq': 1, 'data': v['frame'], 'metadata': {'deviceWidth': 1200, 'deviceHeight': 760}})
        _bv.remember(str(sid), frame)
        for m in (json.dumps({'type': 'status', 'connected': True, 'screencasting': True}), json.dumps({'type': 'url', 'url': v['url']}), frame):
            await ws.send_text(m)
        v.setdefault('sockets', []).append(ws)
        try:
            while True:
                m = json.loads(await ws.receive_text())
                v['input'].append(m.get('type'))
                # THE PAGE'S FOCUSED BOX, as Chrome's Input.dispatchKeyEvent edits it: text goes in on a keyDown that carries it; Backspace
                # and Delete act only with their Windows key code - without it they do nothing (measured on agent-browser 0.38.2)
                if m.get('type') == 'input_keyboard' and m.get('eventType') in ('keyDown', 'rawKeyDown'):
                    f, vk = v.setdefault('field', ''), m.get('windowsVirtualKeyCode')
                    if vk == 8: v['field'] = f[:-1]
                    elif vk == 65 and m.get('modifiers') == 2: v['all'] = True
                    elif m.get('text') and m.get('text') != '\r': v['field'] = ('' if v.pop('all', False) else f) + m['text']
                    if vk == 8 and v.pop('all', False): v['field'] = ''
                if m.get('type') == 'ack': v.setdefault('acks', []).append(m.get('seq'))
        except Exception: pass
        finally: v['sockets'].remove(ws)

    @app.post('/api/fixture/browser/paint')
    async def browser_paint(body: dict):
        """{taskId, frame}: the page moves on - one more frame down every open view's socket, the newest seq, as a screencast sends it."""
        import json
        v = VIEW.get(view_sid.get(int(body.get('taskId') or 0)) or '')
        if not v or not body.get('frame'): raise HTTPException(404, 'no fixture browser on that task')
        v['seq'] = v.get('seq', 1) + 1
        m = json.dumps({'type': 'frame', 'seq': v['seq'], 'data': body['frame'], 'metadata': {'deviceWidth': 1200, 'deviceHeight': 760}})
        for ws in list(v.get('sockets', [])): await ws.send_text(m)
        return {'seq': v['seq'], 'sent': len(v.get('sockets', []))}

    def view_run(sid, args, wait, tag):
        v = VIEW.get(str(sid))
        if not v: return _run(sid, args, wait, tag)
        if list(args) == ['get', 'url']: return 0, v['url']
        v['ran'].append(list(args)); v['url'] = v.get('next') or v['url']
        return 0, '✓ Done'

    _bv.state, _bv.relay, _bg._run = view_state, view_relay, view_run

    class ViewAgent(_gen.GeneralSession):
        """A conversation agent whose turns are kept, not run: Approve's word and the owner's hand-back land here. Taskuary's word starts
        a turn that stays at work until the fixture's next step ends it (the way the agent goes on after Approve); the owner's is answered."""
        def send_prompt(self, text, *a, as_owner=True, **k):
            told.setdefault(self.task_id, []).append(text)
            if not as_owner: self.busy = True; return ''
            store.add_comment(self.task_id, 'owner', _gen.USER_TYPE, text)
            reply = 'I looked at the page again and carried on from there.'
            store.add_comment(self.task_id, 'assistant', _gen.ASSISTANT_TYPE, reply)
            return reply

    @app.post('/api/fixture/browser/view')
    def browser_view(body: dict):
        """{step: 'open', frame}: a general task whose agent has Taskuary's browser open on an invented webinar sign-up page.
        {step: 'hold' | 'turn' | 'close', taskId}: the hold puts its Register press on the task (browsergate's own proposal); the agent
        hands the page over for a human check (browserview.your_turn); the agent's session ends with the browser on that page.
        {step: 'blank', frame}: a general task marked as needing a browser whose agent answered without one - its Chrome on about:blank,
        and a question for the owner asked in words (the owner's pane, 2026-11-03).
        {step: 'asked', frame}: the same, with a page the agent opened in it - an invented fares page - and its question asked in words."""
        step = body.get('step')
        if step not in ('open', 'hold', 'turn', 'close', 'blank', 'asked') or not set(body) <= {'step', 'frame', 'taskId'}: raise HTTPException(422, 'bad step')
        from taskuary import proposals, terminal
        if step in ('blank', 'asked'):
            from taskuary import workerstate as ws
            tid = store.create_task({'Title': 'Gail Moreno asks what Taskuary costs', 'Kind': 'general', 'Status': 'in_progress',
                                     'Tags': 'needs:browser'}, 'fixture')
            store.add_comment(tid, 'taskuary', _gen.USER_TYPE, 'Gail Moreno wrote: what does it cost a month, and can you sign me up?')
            store.add_comment(tid, 'assistant', _gen.ASSISTANT_TYPE, 'Gail Moreno asks what it costs.\n\nFirst month free, or a price now?')
            sess = ViewAgent(store, tid)
            terminal.SESSIONS[sess.sid] = sess; view_sid[tid] = sess.sid
            VIEW[sess.sid] = {'open': True, 'url': 'about:blank' if step == 'blank' else 'https://fares.example/results?to=DEN',
                              'frame': str(body.get('frame') or ''), 'input': [], 'ran': []}
            ws.record(store, tid, sess.sid, 'input_needed', request_id='q-price', text='First month free, or a price now?', source='api')
            return {'taskId': tid, 'sid': sess.sid}
        if step == 'open':
            frame = str(body.get('frame') or '')
            if not frame or len(frame) > 2_000_000: raise HTTPException(422, 'a base64 JPEG frame is required')
            tid = store.create_task({'Title': 'Sign up for the Trainly onboarding webinar', 'Kind': 'general', 'Status': 'in_progress',
                                     'Tags': 'needs:browser'}, 'fixture')
            store.add_comment(tid, 'owner', _gen.USER_TYPE, 'Sign me up for the Trainly onboarding webinar from the invite.')
            store.add_comment(tid, 'assistant', _gen.ASSISTANT_TYPE, 'I opened the registration page and filled in your name and email.')
            sess = ViewAgent(store, tid)
            terminal.SESSIONS[sess.sid] = sess; view_sid[tid] = sess.sid
            sess.busy = True                                      # at work: its turn opened the browser, and ends at the next step
            VIEW[sess.sid] = {'open': True, 'url': 'https://events.trainly.example/onboarding/register', 'frame': frame, 'input': [], 'ran': [],
                              'next': 'https://events.trainly.example/onboarding/registered'}
            answer_paths.update({f'/api/tasks/{tid}/assistant/stream', f'/api/tasks/{tid}/worker/answer'})
            return {'taskId': tid, 'sid': sess.sid}
        tid = int(body.get('taskId') or 0)
        sess = terminal.SESSIONS.get(view_sid.get(tid) or '')
        if not isinstance(sess, ViewAgent): raise HTTPException(404, 'no fixture browser on that task')
        if step == 'hold':
            v = VIEW[sess.sid]
            r = proposals.queue(store, tid, {'action': 'browser_act', 'sid': sess.sid, 'args': ['click', '@e7'], 'command': 'agent-browser click @e7',
                                             'url': v['url'], 'site': 'trainly.example', 'what': 'press "Register" on events.trainly.example - signs you up',
                                             'why': "it can't be undone"}, 'agent')
            rid = (r or {}).get('ReviewId') or store._rows("SELECT ReviewId FROM review WHERE TaskId=? AND Status='pending' ORDER BY ReviewId DESC", (tid,))[0]['ReviewId']
            answer_paths.add(f'/api/reviews/{rid}/decide')
            sess.busy = False                                     # ...and the held press ended that turn (browsergate: "End your turn now")
            return {'reviewId': rid}
        if step == 'turn':
            rid = _bv.your_turn(store, tid, sess.sid, 'tick the "I\'m not a robot" box on the form')
            sess.busy = False                                     # the turn it went on with after Approve ends on the hand-over
            return {'requestId': rid}
        _bv.LAST[sess.sid] = {'frame': json_frame(VIEW[sess.sid]['frame']), 'url': VIEW[sess.sid]['url'], 'at': 0}
        sess.close(learn=False, report=False)
        VIEW[sess.sid]['open'] = False
        return {'closed': True, 'kept': bool(_bv.last_frame(tid))}

    def json_frame(data):
        import json
        return json.dumps({'type': 'frame', 'data': data})

    @app.get('/api/fixture/browser/view/{tid}')
    def browser_view_seen(tid: int):
        "What the agent was told, what its browser ran, and what the owner's mouse and keys sent the page."
        v = VIEW.get(view_sid.get(tid)) or {}
        return {'told': told.get(tid, []), 'ran': v.get('ran', []), 'input': v.get('input', []), 'acks': v.get('acks', []), 'field': v.get('field', '')}

    # ── THE STATE MATRIX (browser/state-matrix, 2026-10-28): the task states the demo world lacks, each one task, invented people ──────────
    MATRIX = ('sent', 'working', 'coding_working', 'asked', 'stopped', 'finished', 'done', 'note', 'deferred', 'todo', 'idea', 'news',
              'fyi_thread', 'idea_mail', 'habits')

    @app.post('/api/fixture/task/matrix')
    def matrix_state(body: dict):
        """{state}: one task in that state, built the way the app leaves it. `sent` a reply that went, the task still open; `working` a
        general agent's terminal at work, `coding_working` a coding one's; `asked` an agent at its prompt with a question for the owner;
        `stopped` a coding run cut off mid-work - its screen kept, no write-up; `finished` a general agent whose run said it finished;
        `done` / `note` closed by the owner, bare or with a note; `deferred` put away with Remind me; `todo` the owner's own to-do list;
        `idea` an Advisor find on the rail; `news` a saved agent result and then the sender writing again; `fyi_thread` three FYI mails on
        one email thread with no task (one rail row, trust audit P2); `idea_mail` an Advisor find about an FYI mail with no task (P1); `habits`
        the one habits row (habits.py) - a habit the Advisor was sure of and adopted, and one it asks about."""
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
        elif s == 'habits':
            tid = None
            from taskuary import funnel, habits, learn, learnedgraph as lg
            day = now.strftime('%Y-%m-%d')
            def line(k, text, sc, ev): return lg.fmt({'key': k, 'text': text, 'ev': ev, 'score': sc, 'seen': day, 'status': 'proposed'})
            add = '\n'.join([line('matrix sso', '{{owner_first}} closes sign-in help threads directly; they need no drafted reply', 12,
                                   [f'rv{i}' for i in range(901, 909)]),
                              line('matrix fyi', 'Forwarded FYI mail from the Payworth desk needs no reply', 5, ['rv920', 'rv921'])])
            doc = store.get_doc(learn.DOC) or '# LEARNED\n\n## What you care about\n'
            if learn.PROP_END not in doc: doc += f'\n## Proposed rules — your call\n{learn.PROP_START}\n{learn.PROP_END}\n'
            store.save_doc(learn.DOC, doc.replace(learn.PROP_END, add + '\n' + learn.PROP_END, 1), 'reflect')
            habits.tick(store)
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
    # `world` adds the stages the demo lacks, with the Advisor's REAL decisions (the model's - the demo script's) on the app's facts: a late ask against a
    # counted usual (three answered threads), one thread on two open tasks (duplicate), an ask with no habit, an agent at work and one
    # that finished. `say` stands in for what only a model writes (a draft warning, a caution): the decision advisor.decide hands every
    # surface, with the label the row would draw, so the page under test reads it from /api/advice like any other. Invented people.
    said = {}
    from taskuary import advisor
    real_decide = advisor.decide

    # ...and it passes the SAME check a real answer does (advisor.checked, the judge's fix 3, 2026-10-26): a scripted Send under a draft
    # caution, a Try again nobody can press - refused and nothing lit, exactly as the app would (it never swaps in a verb since 2026-11-02).
    # An agent at work keeps the real decision (the model's read of it)
    def scripted_decide(st, key, preread=True):
        out = real_decide(st, key, preread)
        tgt = advisor.target_of(st, key)
        o = said.get(int(tgt[1])) if tgt and tgt[0] == 'task' else None
        if o is None or out.get('state') == 'working': return out
        item = advisor._item(st, *tgt, key=key)
        verbs = advisor.offered(st, item) + [{'verb': 'next', 'label': 'Next'}] if item else []
        state = o.get('state', out.get('state'))
        d = advisor.checked(st, item or {}, verbs, {**out, **o, 'key': key, 'state': state, 'verb': o.get('verb', out.get('verb')), 'evidence': [],
                            'kind': o.get('kind') or 'other'})
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

    # ── THE BUTTON STRESS (the owner, 2026-11-02: "hitting all the buttons - reply, mark done, continue and everything - still looks smooth
    # and no crazy stuff"): a fresh copy of any item kind for each press, the world emptied to one item, and what a press wrote, counted ──
    stress_n = [0]

    @app.post('/api/fixture/stress/seed')
    def stress_seed(body: dict):
        """{kind}: one fresh item of that kind, titled with its own number, so every press lands on an item nobody pressed before.
        Returns {taskId, title} - a rail row's words are its title. Invented people only."""
        import json
        from taskuary import artifacts, calwrite, funnel, testing
        kind = body.get('kind')
        stress_n[0] += 1
        n, f = stress_n[0], testing.Factory(store)
        f._n, f.actor = 10_000 * n, 'triage'
        def mail(tid, who, email, subject, words, **kw):
            return f.message(task_id=tid, subject=subject, body=words, from_name=who, from_email=email, conversation_id=f'email:stress-{n}', sent_at=f.ago(minutes=30), **kw)
        title = None
        if kind in MATRIX or kind in ('failed', 'saved', 'coding_saved'):
            tid = (matrix_state({'state': kind}) if kind in MATRIX else {'failed': playbook_failed, 'saved': chat_saved, 'coding_saved': coding_saved}[kind]({}))['taskId']
            # ...its own number on its title: the states share theirs, and a row is found by its words
            if tid: title = f"{(store.get_task(tid) or {}).get('Title')} ({n})"; store._exec('UPDATE task SET Title=? WHERE TaskId=?', (title, tid))
            # ...a rail item with no task is found by its own words (the stress world empties the rail first, so they are its only row)
            else: title = {'idea': 'weekly report could send it', 'fyi_thread': 'Badge reader rollout', 'idea_mail': 'Payworth statement still shows'}.get(kind)
        elif kind == 'fyis':
            # an FYI batch: three notices on three threads, read together under All read, next
            for i, (who, subject) in enumerate((('Payworth Updates', f'Payroll calendar, week {n}'), ('Trainly', f'Course catalogue update {n}'),
                                                ('PhishGuard', f'Monthly phishing report {n}'))):
                mid = f.message(task_id=None, status='filed', subject=subject, from_email=f'news{i}@vendor.example', from_name=who, conversation_id=f'email:stress-{n}-{i}',
                                body='For your information - nothing is asked.', sent_at=f.ago(minutes=20 + i))
                f.route(mid, None, 'file', 'automated/informational')
            title, tid = f'Payroll calendar, week {n}', None
        elif kind == 'general':
            title = f'Payroll export mismatch, batch {n}'
            tid = f.task(title=title, kind='general')
            f.route(mail(tid, 'Ray Colton', 'ray@northwind.example', title, 'Two rows came through with the old ids - can the export map them?'), tid, 'create', 'a concrete ask')
        elif kind == 'owed':
            title = f'Which cost centre for order {n}?'
            tid = f.task(title=title, kind='reply')
            f.route(mail(tid, 'Omar Keller', 'omar@northwind.example', title, 'Which cost centre should this order go on?'), tid, 'create', 'a question for you')
        elif kind == 'draft':
            title = f'Invoice {88000 + n} - past due'
            tid = f.task(title=title, kind='reply')
            mid = mail(tid, 'Paula Vance', 'paula@vendor.example', title, 'This invoice is 46 days past due. Please advise.')
            f.route(mid, tid, 'create', 'a vendor chasing payment')
            f.review(tid, mid, draft="Thanks Paula - it goes out in Friday's payment run.")
        elif kind == 'blocked':
            title = f'org/app#{500 + n} import stops on a blank site'
            tid = f.task(title=title, kind='coding', status='in_progress', source='github', Assignee='agent:coding', Tags='repo:org/app')
            f.route(mail(tid, 'Marcus Reed', None, title, 'The import aborts when a site has no manager.', channel='github'), tid, 'create', 'an issue')
            live_agent({'task_id': tid})
        elif kind == 'goal':
            title = f'Move the payroll export to the new ledger ({n})'
            tid = f.task(title=title, kind='task', DoneWhen='the payroll export lands in the new ledger', DueAt=(datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'))
            store.set_task_checklist(tid, [f'List the export fields {n}', f'Map them to the ledger {n}', f'Gail: sign-off {n}'], 'owner')
            wait = f.task(title=f'Gail: sign-off {n}', status='waiting', kind='task', ParentId=tid, Assignee='person:gail@northwind.example',
                          DueAt=(datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d'))
            store.link_step(tid, store.checklist_id(f'Gail: sign-off {n}'), wait, 'owner')
        elif kind == 'invite':
            d1 = _demo._workdays(1)[0]
            subject = f'Ledger cutover rehearsal {n}'
            c = {'kind': 'request', 'provider': 'outlook', 'mailbox': 'demo', 'event_id': f'stress-event-{n}', 'ical_uid': f'stress-uid-{n}', 'update': False,
                 'answered': False, 'asks': True, 'subject': subject, 'start': f'{d1} 10:00', 'end': f'{d1} 11:00', 'all_day': False,
                 'organizer': 'Erin Blake', 'organizer_email': 'erin@northwind.example', 'attendees': ['erin@northwind.example', 'alex@northwind.example']}
            title = f'Invite: {subject}'
            tid = f.task(title=title, kind='reply', Summary=f"Erin Blake invited you to {subject}, {calwrite.when(c['start'], c['end'])}. Accept, decline or propose a new time.")
            mid = mail(tid, 'Erin Blake', 'erin@northwind.example', f'Invitation: {subject}', 'A rehearsal of the ledger cutover.', MailMetaJson=json.dumps({'invite': True, 'cal': c}))
            f.route(mid, tid, 'create', 'Erin invited you')
        elif kind == 'meet':
            d2 = _demo._workdays(2)[1]
            title = f'Half an hour on the vendor list ({n})'
            tid = f.task(title=title, kind='reply')
            mid = mail(tid, 'Gail Moreno', 'gail@northwind.example', f'Vendor list - 30 minutes? ({n})', f"Can we find 30 minutes {d2:%A} to go through the vendor list?",
                       MeetJson=json.dumps({'minutes': 30, 'from': str(d2), 'to': str(d2)}))
            f.route(mid, tid, 'create', 'she asks for half an hour')
            f.review(tid, mid, draft=f"Yes - {d2:%A} works. I'll send an invite.")
        elif kind == 'report':
            title = f'Badge swipes by site {n}'
            pic = f.report_row(title=title)
            rows = [{'site': 'Lakeview', 'swipes': 112 + n}, {'site': 'Riverside', 'swipes': 98}, {'site': 'Fairhaven', 'swipes': 143}]
            text = '\n'.join(json.dumps(r) for r in rows)
            store._exec('UPDATE message SET BodyText=?, Subject=? WHERE MessageId=?', (text, f'{title} - {len(rows)} rows', pic.mid))
            artifacts.attach_report_output(store, pic.mid, title, text)
            tid = None
        elif kind == 'fyi':
            title = f'Platform digest, week {n}'
            mid = f.message(task_id=None, status='filed', subject=title, from_email='digest@vendor.example', from_name='Payworth Updates',
                            body="An automated summary of this week's changes. Nothing is asked.", sent_at=f.ago(minutes=20))
            f.route(mid, None, 'file', 'automated/informational')
            tid = None
        elif kind == 'watched':
            from taskuary import watch
            title = f'Paula sorts the Trainly seats ({n})'
            tid = f.task(title=title, kind='general')
            f.route(mail(tid, 'Paula Vance', 'paula@northwind.example', title, 'I will sort the Trainly seats this week.'), tid, 'create', 'a heads-up')
            watch.watch(store, tid, 'owner')
        else: raise HTTPException(422, f'unknown kind {kind!r}')
        store.reconcile_processing_membership(); funnel.invalidate(); store._poke('feed-changed')
        return {'taskId': tid, 'title': title, 'kind': kind}

    @app.post('/api/fixture/stress/clear')
    def stress_clear(body: dict):
        """Every rail item put away without a word to anyone: open tasks closed in the database, everything else settled done - the world
        the next seed is the one item of."""
        from taskuary import funnel, railwalk
        store._exec("UPDATE task SET Status='done', WatchedAt=NULL WHERE Status NOT IN ('done', 'dropped', 'cancelled')", ())
        funnel.invalidate()
        for it in funnel.pile(store, force=True).get('items', []):
            k = str(it.get('key') or '')
            if k and not k.startswith('task:'):
                try: funnel.settle(store, k, 'done', 'fixture')
                except Exception: pass
        store.reconcile_processing_membership(); railwalk.reset(store); funnel.invalidate(); store._poke('feed-changed')
        return {'left': [i.get('key') for i in funnel.pile(store, force=True).get('items', [])]}

    @app.get('/api/fixture/stress/count')
    def stress_count(task_id: int = 0):
        """What the presses wrote: on the task (its status, watch, comments, reviews, its audit and its operations by kind) and everywhere
        (every operation by kind and status) - a press counted twice shows as one more row than a single press leaves."""
        from collections import Counter
        ops = store._rows('SELECT Kind, Status, TargetKind, TargetId FROM operation')
        out = {'ops': dict(Counter(f"{o['Kind']}/{o['Status']}" for o in ops if o['Status'] != 'proposed'))}
        if task_id:
            t = store.get_task(task_id) or {}
            out['task'] = {k: t.get(k) for k in ('Status', 'WatchedAt', 'Assignee', 'Priority', 'Kind')}
            cs = store.list_comments(task_id)
            out['comments'], out['said'] = len(cs), [f"{c.get('Actor')}: {(c.get('Body') or '')[:160]}" for c in cs[-2:]]
            out['reviews'] = [f"{r['ReviewId']}:{r['Status']}" for r in store._rows('SELECT ReviewId, Status FROM review WHERE TaskId=?', (task_id,))]
            out['audit'] = dict(Counter(a['Action'] for a in store._rows("SELECT Action FROM audit WHERE EntityType='task' AND EntityId=?", (task_id,))))
            out['taskOps'] = dict(Counter(f"{o['Kind']}/{o['Status']}" for o in ops if o['TargetKind'] == 'task' and o['TargetId'] == task_id and o['Status'] != 'proposed'))
        return out

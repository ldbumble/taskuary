"""Seed a believable day-in-the-life into TASKUARY_HOME for the README screenshot.

Pictures go through taskuary.testing.Factory so the screenshot graph is the same
graph the regression suite pins - a JOIN rewrite that drops a chip fails both.
"""
import json as _json
from datetime import datetime, timedelta
from taskuary import config
from taskuary.store import SQLiteStore
from taskuary.testing import Factory

s = SQLiteStore(config.db_path())
fx = Factory(s)
fx.actor = 'router'
now = datetime.now()
t = lambda h, m=0: (now - timedelta(hours=h, minutes=m)).strftime('%Y-%m-%d %H:%M:%S')

# 1. reply-only question -> pending AI draft (the waiting-on-you star of the shot)
tid1 = fx.task(title='Q3 vendor spend report?', kind='reply', source='email')
m1 = fx.message(task_id=tid1, external_id='demo1', source_name='john.smith@example.com',
    subject='Q3 vendor spend report?', from_name='Sarah Chen', from_email='sarah.chen@example.com',
    sent_at=t(0, 25), body='Hi John, do you have the Q3 vendor spend report handy? Finance wants the top-10 breakdown before the board call on Thursday.')
fx.route(m1, tid1, 'create', 'reply-only question', by='router')
fx.review(tid1, m1, reason='AI drafted a reply for your review',
    draft='Hi Sarah,\n\nYes - the Q3 vendor spend report is in the shared Finance folder (Q3/vendor-spend-2026.xlsx). The top-10 breakdown is on the second tab; total spend was $2.41M, down 6% from Q2.\n\nBest,\nJohn')

# 2. coding task worked by the agent, diff attached, done
tid2 = fx.task(title='Nightly export job writes empty CSVs', kind='coding', status='done', source='email', Assignee='agent:coder')
m2 = fx.message(task_id=tid2, external_id='demo2', source_name='john.smith@example.com',
    subject='Nightly export job writes empty CSVs', from_name='Marcus Webb', from_email='marcus.webb@example.com',
    sent_at=t(3, 10), body='The nightly export produced empty files again last night. Can you take a look before tonight runs?')
fx.route(m2, tid2, 'create', 'asks the owner to do something', by='router')
rid = fx.run(tid2, status='done', agent='coder', instruction='Work this coding task end to end.')
s.update_run(rid, {'Result': 'Fixed: the exporter swallowed the timezone-aware cutoff. Added regression test.',
    'DiffText': 'diff --git a/export/job.py b/export/job.py\n@@ -41,7 +41,7 @@\n-    cutoff = datetime.utcnow() - timedelta(days=1)\n+    cutoff = datetime.now(timezone.utc) - timedelta(days=1)\n', 'SessionId': 'demo'}, finished=True)
fx.comment(tid2, 'CODER REPORT\nTriage: real bug in export/job.py\nDetermination: naive/aware datetime comparison filtered out every row\nActions: fixed the cutoff, added a regression test, opened PR #142\nSummary: nightly export fixed; the next run will produce data', actor='coder')
fx.review(tid2, m2, status='approved',
    draft='Hi Marcus - found it and fixed it: a timezone bug filtered out every row. The next run is fine.',
    final='Hi Marcus - found it and fixed it: a timezone bug filtered out every row. The next run is fine.')

# 3. scheduled report rows (mssql)
sid = s.save_source({'Channel': 'report', 'Address': 'Nightly headcount', 'Active': 1,
    'ConfigJson': '{"type": "mssql", "title": "Nightly headcount", "every_minutes": 480}'}, 'owner')
m3 = fx.message(status='filed', external_id='demo3', conversation_id='report:%d' % sid, channel='report',
    source_name='Nightly headcount', subject='Nightly headcount - 4 rows', from_name='Nightly headcount',
    sent_at=t(7, 45), body='{"site": "Lakeview", "headcount": 112}\n{"site": "Riverside", "headcount": 98}\n{"site": "Oak Grove", "headcount": 87}\n{"site": "Summit", "headcount": 64}')
fx.route(m3, None, 'file', 'scheduled report', by='report')

# 3b. Teams chat auto-answered - teal "auto" chip + purple channel bar
tid4 = fx.task(title='Standup moved to 10:30?', kind='reply', status='done', source='teams')
m6 = fx.message(task_id=tid4, external_id='demo6', channel='teams', source_name='Ops chat',
    subject='Priya Nair in Ops chat', from_name='Priya Nair', from_email='priya.nair@example.com',
    sent_at=t(1, 5), body='Is standup moving to 10:30 today because of the vendor call?')
fx.route(m6, tid4, 'create', 'reply-only question', by='router')
fx.review(tid4, m6, kind='auto', status='auto',
    draft='Yes - 10:30 today only, back to 9:45 tomorrow.', final='Yes - 10:30 today only, back to 9:45 tomorrow.')

# 3c. Slack deploy notification, filed
m7 = fx.message(status='filed', external_id='demo7', channel='slack', source_name='#deploys',
    subject='deploy 2026.8.17-2 finished', from_name='deploybot',
    sent_at=t(2, 40), body='api v2026.8.17-2 deployed to prod - 0 errors, p95 142ms.')
fx.route(m7, None, 'file', 'automated notification', by='router')

# 3d. coding task escalated - the amber waiting-on-you dot
tid5 = fx.task(title='PTO import for the 7/26-8/8 payroll period', kind='coding',
    status='in_progress', source='email', Assignee='agent:coder')
m8 = fx.message(task_id=tid5, external_id='demo8', source_name='john.smith@example.com',
    subject='PTO import - check date 8/17', from_name='Chana Levine', from_email='chana.levine@example.com',
    sent_at=t(4, 55), body='Please run the PTO import for the 7/26-8/8 pay period, check date 8/17.')
fx.route(m8, tid5, 'create', 'asks the owner to do something', by='router')
fx.review(tid5, m8, kind='escalation', reason='coder needs you: confirm reconciliation=True before the import writes payroll data')

# 3e. routed, queued for the coder - indigo
tid6 = fx.task(title='Update the on-call rotation page', kind='coding', source='email')
m9 = fx.message(task_id=tid6, external_id='demo9', source_name='john.smith@example.com',
    subject='On-call rotation page is stale', from_name='IT Helpdesk', from_email='helpdesk@example.com',
    sent_at=t(5, 30), body='The on-call page still shows July - can it pull from the schedule automatically?')
fx.route(m9, tid6, 'create', 'asks the owner to do something', by='router')

# 4. fyi newsletter, filed
m4 = fx.message(status='filed', external_id='demo4', source_name='john.smith@example.com',
    subject='Weekly platform digest', from_name='Platform Updates', from_email='no-reply@vendor.example.com',
    sent_at=t(26), body='This is an automated summary of platform changes this week.')
fx.route(m4, None, 'file', 'automated/informational', by='router')

# 5. thread attached to an existing task yesterday
tid3 = fx.task(title='Onboard the new AP clerk', kind='general', status='in_progress', source='email')
m5 = fx.message(task_id=tid3, external_id='demo5', conversation_id='c-onboard', source_name='john.smith@example.com',
    subject='RE: Onboard the new AP clerk', from_name='Dana Ruiz', from_email='dana.ruiz@example.com',
    sent_at=t(28, 20), body='Adding one more thing - she also needs access to the invoice approval queue.')
fx.route(m5, tid3, 'attach', 'same conversation thread', score=0.81,
         candidates=[{'task_id': tid3, 'score': 0.81, 'signals': {'thread': 1, 'subject': 0.7, 'body': 0.4}}], by='router')
# 6. the personal messengers: a Telegram question with the reply drafted, a WhatsApp task
tid7 = fx.task(title='Can you resend the Q3 numbers?', kind='reply', source='telegram')
m10 = fx.message(task_id=tid7, external_id='demo10', conversation_id='telegram:88214', channel='telegram',
    source_name='Sam (Telegram)', subject=None, from_name='Sam Delgado', from_email='@samdelgado',
    sent_at=t(0, 55), body='Hey - can you resend the Q3 numbers? The link from last week expired.')
fx.route(m10, tid7, 'create', 'reply-only question', by='router')
fx.review(tid7, m10, reason='AI drafted a reply for your review',
    draft='Fresh link: finance.example.com/q3-2026 - this one does not expire.')

tid8 = fx.task(title='Scanner in the mailroom is jamming again', kind='coding', source='whatsapp')
m11 = fx.message(task_id=tid8, external_id='demo11', conversation_id='whatsapp:15550100@s.whatsapp.net',
    channel='whatsapp', source_name='Rob (WhatsApp)', from_name='Rob Feld',
    sent_at=t(2, 5), body='the mailroom scanner is jamming on every third page again, same as March. can someone look before the 3pm batch?')
fx.route(m11, tid8, 'create', 'asks the owner to do something', by='router')

# 7. the collaboration scene: two agents in the SAME checkout - each card shows the files
# ITS agent has modified (the other agent is told the same list) - and a third task queued
# behind the one whose files it would touch (affinity routing).
tid9 = fx.task(title='Report charts render blank in dark mode', kind='coding', status='in_progress',
               source='email', Assignee='agent:claude')
m12 = fx.message(task_id=tid9, external_id='demo12', source_name='john.smith@example.com',
    subject='Dark mode charts are blank', from_name='Amir Solomon', from_email='amir.solomon@example.com',
    sent_at=t(0, 40), body='Since the theme update, every report chart renders blank when the app is in dark mode.')
fx.route(m12, tid9, 'create', 'asks the owner to do something', by='router')
r9 = s.start_run(tid9, 'claude', 'Work this coding task end to end.', 'router')
s.update_run(r9, {'TraceJson': _json.dumps([
    {'at': t(0, 4), 'kind': 'live', 'name': 'claude', 'detail': '→ Edit: website/src/ReportsView.jsx'},
    {'at': t(0, 3), 'kind': 'live', 'name': 'claude', 'detail': '→ Edit: website/src/theme.jsx'},
    {'at': t(0, 2), 'kind': 'live', 'name': 'claude', 'detail': '· chart palette now reads the theme tokens, not hex constants'},
    {'at': t(0, 1), 'kind': 'live', 'name': 'claude', 'detail': '→ Bash: npm run build'}])})
s._exec('UPDATE run SET StartedAt=? WHERE RunId=?', (t(0, 18), r9))

tid10 = fx.task(title='Weekly headcount report misses one site', kind='coding', status='in_progress',
                source='teams', Assignee='agent:codex')
m13 = fx.message(task_id=tid10, external_id='demo13', channel='teams', source_name='Ops chat',
    subject='Rina Katz in Ops chat', from_name='Rina Katz', from_email='rina.katz@example.com',
    sent_at=t(1, 10), body='The weekly headcount report skips Summit - looks like the new site never made it into the query.')
fx.route(m13, tid10, 'create', 'asks the owner to do something', by='router')
r10 = s.start_run(tid10, 'codex', 'Work this coding task end to end.', 'router')
s.update_run(r10, {'TraceJson': _json.dumps([
    {'at': t(0, 6), 'kind': 'live', 'name': 'codex', 'detail': '→ Edit: taskuary/reports.py'},
    {'at': t(0, 5), 'kind': 'live', 'name': 'codex', 'detail': '→ Write: tests/test_reports.py'},
    {'at': t(0, 1), 'kind': 'live', 'name': 'codex', 'detail': '· 14 passed in 2.1s'}])})
s._exec('UPDATE run SET StartedAt=? WHERE RunId=?', (t(0, 9), r10))

tid11 = fx.task(title='Add CSV export to the reports page', kind='coding', source='email')
m14 = fx.message(task_id=tid11, external_id='demo14', source_name='john.smith@example.com',
    subject='CSV export for reports?', from_name='Sarah Chen', from_email='sarah.chen@example.com',
    sent_at=t(0, 12), body='Could the reports page get a download-as-CSV button? Finance keeps retyping the numbers.')
fx.route(m14, tid11, 'create', 'asks the owner to do something', by='router')
fx.queued(tid11, tid9, agent='claude', reason='both would modify website/src/ReportsView.jsx')
fx.comment(tid11, 'Queued behind TQ-%04d "Report charts render blank in dark mode" - '
           'both would modify website/src/ReportsView.jsx. It starts by itself when that agent finishes.' % tid9,
           actor='router')

# 7b. The durable handbook is deliberately separate from the Board's live handoffs. Each entry
# names the agent and the task that taught it, so Social demonstrates provenance instead of
# looking like an anonymous robot feed.
from taskuary import handbook
lore1 = handbook.post(s, 'Report charts must read theme tokens, not fixed colors',
    'Use the report palette from website/src/theme.jsx. Fixed light colors disappear when the canvas is rendered in dark mode.',
    'reports', 'gotcha', 'claude', task_id=tid9, cwd='website/src', repo='taskuary')
s.lore_vote(lore1['LoreId'], 2)
lore2 = handbook.post(s, 'New sites belong in the shared site filter',
    'The weekly headcount query and every export share the site filter in taskuary/reports.py. Add a site there rather than patching one report.',
    'reporting', 'howto', 'codex', task_id=tid10, cwd='taskuary', repo='taskuary')
s.lore_comment(lore2['LoreId'], 'This also covers scheduled CSV exports.', 'owner')

# 8. the Morning digest, sectioned - the panel renders the emoji headers as real headings,
# and the digest screenshot is cropped off this row's open panel
m15 = fx.message(external_id='demodigest', channel='report', source_name='Morning digest',
    subject='Morning digest — the last 3 days, distilled', from_name='Morning digest',
    sent_at=t(0, 5), status='filed', body=(
        '\U0001f680 In flight\n'
        '- TQ-0009 “Report charts render blank in dark mode” — claude is on it; the theme tokens were the culprit.\n'
        '- TQ-0010 “Weekly headcount report misses one site” — codex is on it; tests already pass.\n\n'
        '⏳ Waiting on you\n'
        '- TQ-0001 Sarah Chen wants the Q3 vendor spend report — the reply is drafted, one click to send.\n'
        '- TQ-0004 PTO import for the 7/26-8/8 payroll period — confirm before it writes payroll data.\n\n'
        '\U0001f4cc Keep honoring\n'
        '- Vendor newsletters stay filed — you ruled the last three FYI, and triage remembers.\n\n'
        '\U0001f4c8 Patterns\n'
        '- Sarah Chen wrote twice in a day about Q3 numbers — the board call is Thursday.\n'
        '- The nightly export failed twice this week before the fix that closed TQ-0002.'))
fx.route(m15, None, 'file', 'scheduled report - informational, never a task', by='report')

# A deterministic Assistant post for the browser demo and README screenshot. It carries the same
# stored shape assistant.run writes, including provenance about what it reviewed.
from taskuary import assistant
stamp = t(0, 2)
idea_specs = [
    {'key': 'idea:summit-filter', 'kind': 'idea',
     'text': 'Summit is missing from more than one report; fix the shared site filter once.',
     'action': {'type': 'task', 'task': tid10, 'section': 'ideas',
                'why': 'The headcount task and the CSV export both use the same site list.'}},
    {'key': 'followup:q3-spend', 'kind': 'followup',
     'text': 'Sarah still needs the Q3 vendor-spend breakdown before Thursday.',
     'action': {'type': 'followup', 'mid': m1, 'task': tid1, 'section': 'loose',
                'why': 'Her reply is drafted, but it has not been approved.'}},
]
ideas = [s.upsert_idea(spec, stamp) for spec in idea_specs]
public = [assistant._public(i) for i in ideas]
amid = s.add_message({'ExternalId': f'assistant:{stamp}', 'ConversationId': 'assistant',
    'Channel': 'assistant', 'SourceName': 'Assistant', 'Subject': public[0]['text'] + ' (+1 more)',
    'FromName': 'Assistant', 'SentAt': stamp,
    'BodyText': '\n'.join(f"- {i['text']}\n    why: {i['why']}" for i in public), 'Status': 'feed'})
s.add_route(amid, None, 'feed', None, "the assistant's post: what it noticed and what it would do", [], 'assistant')
s.set_brief(amid, _json.dumps({'ideas': public, 'reviewed': {
    'candidates': {'followup': 1, 'idea': 1}, 'skipped': [], 'recent': 14,
    'week': 2, 'open': 7, 'said': 0, 'model': True, 'people': 4},
    'flight': [], 'stats': {}}))
s.set_ideas_message([i['id'] for i in public], amid)

# every report source reads as freshly polled, or the server's STARTUP run files its own
# rows on top of the fiction (a FAILED headcount, a raw digest) and they photobomb the shots
s._exec("UPDATE source SET LastPolledAt=? WHERE Channel='report'", (t(0, 0),))

print('demo data seeded')

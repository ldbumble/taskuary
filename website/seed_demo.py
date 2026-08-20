"""Seed a believable day-in-the-life into TASKUARY_HOME for the README screenshot."""
from datetime import datetime, timedelta
from taskuary import config
from taskuary.store import SQLiteStore

s = SQLiteStore(config.db_path())
now = datetime.now()
t = lambda h, m=0: (now - timedelta(hours=h, minutes=m)).strftime('%Y-%m-%d %H:%M:%S')

# 1. reply-only question -> pending AI draft (the waiting-on-you star of the shot)
tid1 = s.create_task({'Title': 'Q3 vendor spend report?', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
m1 = s.add_message({'TaskId': tid1, 'ExternalId': 'demo1', 'Channel': 'email', 'SourceName': 'john.smith@example.com',
    'Subject': 'Q3 vendor spend report?', 'FromName': 'Sarah Chen', 'FromEmail': 'sarah.chen@example.com',
    'SentAt': t(0, 25), 'BodyText': 'Hi John, do you have the Q3 vendor spend report handy? Finance wants the top-10 breakdown before the board call on Thursday.', 'Status': 'routed'})
s.add_route(m1, tid1, 'create', None, 'reply-only question', [], 'router')
s.add_review({'TaskId': tid1, 'MessageId': m1, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'AI drafted a reply for your review',
    'DraftText': 'Hi Sarah,\n\nYes - the Q3 vendor spend report is in the shared Finance folder (Q3/vendor-spend-2026.xlsx). The top-10 breakdown is on the second tab; total spend was $2.41M, down 6% from Q2.\n\nBest,\nJohn'})

# 2. coding task worked by the agent, diff attached, done
tid2 = s.create_task({'Title': 'Nightly export job writes empty CSVs', 'Kind': 'coding', 'Status': 'done', 'Source': 'email', 'Assignee': 'agent:coder'}, 'router')
m2 = s.add_message({'TaskId': tid2, 'ExternalId': 'demo2', 'Channel': 'email', 'SourceName': 'john.smith@example.com',
    'Subject': 'Nightly export job writes empty CSVs', 'FromName': 'Marcus Webb', 'FromEmail': 'marcus.webb@example.com',
    'SentAt': t(3, 10), 'BodyText': 'The nightly export produced empty files again last night. Can you take a look before tonight runs?', 'Status': 'routed'})
s.add_route(m2, tid2, 'create', None, 'asks the owner to do something', [], 'router')
rid = s.start_run(tid2, 'coder', 'Work this coding task end to end.', 'owner')
s.update_run(rid, {'Status': 'done', 'Result': 'Fixed: the exporter swallowed the timezone-aware cutoff. Added regression test.',
    'DiffText': 'diff --git a/export/job.py b/export/job.py\n@@ -41,7 +41,7 @@\n-    cutoff = datetime.utcnow() - timedelta(days=1)\n+    cutoff = datetime.now(timezone.utc) - timedelta(days=1)\n', 'SessionId': 'demo'}, finished=True)
s.add_comment(tid2, 'coder', 'agent', 'CODER REPORT\nTriage: real bug in export/job.py\nDetermination: naive/aware datetime comparison filtered out every row\nActions: fixed the cutoff, added a regression test, opened PR #142\nSummary: nightly export fixed; the next run will produce data')
s.add_review({'TaskId': tid2, 'MessageId': m2, 'Kind': 'draft', 'Status': 'approved',
    'DraftText': 'Hi Marcus - found it and fixed it: a timezone bug filtered out every row. The next run is fine.',
    'FinalText': 'Hi Marcus - found it and fixed it: a timezone bug filtered out every row. The next run is fine.'})

# 3. scheduled report rows (mssql)
sid = s.save_source({'Channel': 'report', 'Address': 'Nightly census', 'Active': 1,
    'ConfigJson': '{"type": "mssql", "title": "Nightly census", "every_minutes": 480}'}, 'owner')
m3 = s.add_message({'TaskId': None, 'ExternalId': 'demo3', 'ConversationId': 'report:%d' % sid, 'Channel': 'report',
    'SourceName': 'Nightly census', 'Subject': 'Nightly census - 4 rows', 'FromName': 'Nightly census',
    'SentAt': t(7, 45), 'BodyText': '{"facility": "Lakeview", "census": 112}\n{"facility": "Riverside", "census": 98}\n{"facility": "Oak Grove", "census": 87}\n{"facility": "Summit", "census": 64}', 'Status': 'filed'})
s.add_route(m3, None, 'file', None, 'scheduled report', [], 'report')

# 3b. Teams chat auto-answered - teal "auto" chip + purple channel bar
tid4 = s.create_task({'Title': 'Standup moved to 10:30?', 'Kind': 'reply', 'Status': 'done', 'Source': 'teams'}, 'router')
m6 = s.add_message({'TaskId': tid4, 'ExternalId': 'demo6', 'Channel': 'teams', 'SourceName': 'Ops chat',
    'Subject': 'Priya Nair in Ops chat', 'FromName': 'Priya Nair', 'FromEmail': 'priya.nair@example.com',
    'SentAt': t(1, 5), 'BodyText': 'Is standup moving to 10:30 today because of the vendor call?', 'Status': 'routed'})
s.add_route(m6, tid4, 'create', None, 'reply-only question', [], 'router')
s.add_review({'TaskId': tid4, 'MessageId': m6, 'Kind': 'auto', 'Status': 'auto',
    'DraftText': 'Yes - 10:30 today only, back to 9:45 tomorrow.', 'FinalText': 'Yes - 10:30 today only, back to 9:45 tomorrow.'})

# 3c. Slack deploy notification, filed
m7 = s.add_message({'TaskId': None, 'ExternalId': 'demo7', 'Channel': 'slack', 'SourceName': '#deploys',
    'Subject': 'deploy 2026.8.17-2 finished', 'FromName': 'deploybot',
    'SentAt': t(2, 40), 'BodyText': 'api v2026.8.17-2 deployed to prod - 0 errors, p95 142ms.', 'Status': 'filed'})
s.add_route(m7, None, 'file', None, 'automated notification', [], 'router')

# 3d. coding task escalated - the amber waiting-on-you dot
tid5 = s.create_task({'Title': 'PTO import for the 7/26-8/8 payroll period', 'Kind': 'coding',
    'Status': 'in_progress', 'Source': 'email', 'Assignee': 'agent:coder'}, 'router')
m8 = s.add_message({'TaskId': tid5, 'ExternalId': 'demo8', 'Channel': 'email', 'SourceName': 'john.smith@example.com',
    'Subject': 'PTO import - check date 8/17', 'FromName': 'Chana Levine', 'FromEmail': 'chana.levine@example.com',
    'SentAt': t(4, 55), 'BodyText': 'Please run the PTO import for the 7/26-8/8 pay period, check date 8/17.', 'Status': 'routed'})
s.add_route(m8, tid5, 'create', None, 'asks the owner to do something', [], 'router')
s.add_review({'TaskId': tid5, 'MessageId': m8, 'Kind': 'escalation', 'Status': 'pending',
    'Reason': 'coder needs you: confirm reconciliation=True before the import writes payroll data'})

# 3e. routed, queued for the coder - indigo
tid6 = s.create_task({'Title': 'Update the on-call rotation page', 'Kind': 'coding', 'Status': 'open', 'Source': 'email'}, 'router')
m9 = s.add_message({'TaskId': tid6, 'ExternalId': 'demo9', 'Channel': 'email', 'SourceName': 'john.smith@example.com',
    'Subject': 'On-call rotation page is stale', 'FromName': 'IT Helpdesk', 'FromEmail': 'helpdesk@example.com',
    'SentAt': t(5, 30), 'BodyText': 'The on-call page still shows July - can it pull from the schedule automatically?', 'Status': 'routed'})
s.add_route(m9, tid6, 'create', None, 'asks the owner to do something', [], 'router')

# 4. fyi newsletter, filed
m4 = s.add_message({'TaskId': None, 'ExternalId': 'demo4', 'Channel': 'email', 'SourceName': 'john.smith@example.com',
    'Subject': 'Weekly platform digest', 'FromName': 'Platform Updates', 'FromEmail': 'no-reply@vendor.example.com',
    'SentAt': t(26), 'BodyText': 'This is an automated summary of platform changes this week.', 'Status': 'filed'})
s.add_route(m4, None, 'file', None, 'automated/informational', [], 'router')

# 5. thread attached to an existing task yesterday
tid3 = s.create_task({'Title': 'Onboard the new AP clerk', 'Kind': 'general', 'Status': 'in_progress', 'Source': 'email'}, 'router')
m5 = s.add_message({'TaskId': tid3, 'ExternalId': 'demo5', 'ConversationId': 'c-onboard', 'Channel': 'email',
    'SourceName': 'john.smith@example.com', 'Subject': 'RE: Onboard the new AP clerk', 'FromName': 'Dana Ruiz',
    'FromEmail': 'dana.ruiz@example.com', 'SentAt': t(28, 20),
    'BodyText': 'Adding one more thing - she also needs access to the invoice approval queue.', 'Status': 'routed'})
s.add_route(m5, tid3, 'attach', 0.81, 'same conversation thread',
            [{'task_id': tid3, 'score': 0.81, 'signals': {'thread': 1, 'subject': 0.7, 'body': 0.4}}], 'router')
# 6. the personal messengers: a Telegram question with the reply drafted, a WhatsApp task
tid7 = s.create_task({'Title': 'Can you resend the Q3 numbers?', 'Kind': 'reply', 'Status': 'open', 'Source': 'telegram'}, 'router')
m10 = s.add_message({'TaskId': tid7, 'ExternalId': 'demo10', 'ConversationId': 'telegram:88214', 'Channel': 'telegram',
    'SourceName': 'Leah (Telegram)', 'Subject': None, 'FromName': 'Leah Stern', 'FromEmail': '@leahstern',
    'SentAt': t(0, 55), 'BodyText': 'Hey - can you resend the Q3 numbers? The link from last week expired.', 'Status': 'routed'})
s.add_route(m10, tid7, 'create', None, 'reply-only question', [], 'router')
s.add_review({'TaskId': tid7, 'MessageId': m10, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'AI drafted a reply for your review',
    'DraftText': 'Fresh link: finance.example.com/q3-2026 - this one does not expire.'})

tid8 = s.create_task({'Title': 'Scanner in the mailroom is jamming again', 'Kind': 'coding', 'Status': 'open', 'Source': 'whatsapp'}, 'router')
m11 = s.add_message({'TaskId': tid8, 'ExternalId': 'demo11', 'ConversationId': 'whatsapp:15550100@s.whatsapp.net',
    'Channel': 'whatsapp', 'SourceName': 'Rob (WhatsApp)', 'FromName': 'Rob Feld',
    'SentAt': t(2, 5), 'BodyText': 'the mailroom scanner is jamming on every third page again, same as March. can someone look before the 3pm batch?', 'Status': 'routed'})
s.add_route(m11, tid8, 'create', None, 'asks the owner to do something', [], 'router')

print('demo data seeded')

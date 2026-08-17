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
print('demo data seeded')

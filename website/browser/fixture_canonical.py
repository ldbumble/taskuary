"""Canonical All census fixtures; loaded only by the socket-isolated demo server."""
import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import HTTPException


def install_canonical_changes(app, store):
    if os.environ.get('TASKUARY_DEMO') != '1' or not os.environ.get('TASKUARY_HOME'):
        raise RuntimeError('canonical fixture requires an isolated demo home')
    from taskuary import calendar, funnel, live, processing_all
    seeded = {}

    def root(kind, local_id):
        with store._processing_read() as cur:
            row = cur.execute('''SELECT ItemId FROM processing_member
                WHERE EntityKind=? AND LocalId=? AND RetiredAt IS NULL''', (kind, str(local_id))).fetchone()
            return row['ItemId']

    def message(title, at, *, task=None, source='canonical@example.test', status='filed', body=None,
                conversation=None, channel='email'):
        mid = store.add_message({'TaskId': task, 'ExternalId': f'canonical:{title}', 'Channel': channel,
                                 'SourceName': source, 'Subject': title, 'FromName': 'Canonical fixture',
                                 'FromEmail': source, 'BodyText': body or title, 'Status': status,
                                 'SentAt': at, 'ConversationId': conversation})
        store._exec('UPDATE message SET CreatedAt=? WHERE MessageId=?', (at, mid))
        return mid

    @app.post('/api/fixture/processing/canonical-all')
    def seed(body: dict):
        if body != {'count': 507}:
            raise HTTPException(422, 'fixture requires exactly count=507')
        if seeded:
            return seeded
        now = datetime.now()
        stamp = now.isoformat(' ')
        # Suspend this isolated fixture's worker while seeding; normal store methods
        # retain their own locks. Complete the census explicitly before returning.
        with patch.object(processing_all.MembershipWorker, 'reconcile'), patch.object(store, '_poke'), patch.object(live, 'emit'):
            store.save_source({'Channel': 'email', 'Address': 'canonical-older@example.test',
                               'Active': 1, 'ConfigJson': '{}'}, 'fixture')
            tid = store.create_task({'Title': 'Canonical grouped task', 'Status': 'open', 'Kind': 'reply'}, 'fixture')
            older = message('Canonical older selected member', (now - timedelta(seconds=3)).isoformat(' '),
                            task=tid, source='canonical-older@example.test', status='routed',
                            body='Full older source ' + 'x' * 6000 + ' CANONICAL FULL BODY END')
            latest = message('Canonical latest grouped member', stamp, task=tid, status='routed')
            selected_review = store.add_review({'TaskId': tid, 'MessageId': older, 'Kind': 'draft_reply', 'Status': 'pending',
                              'DraftText': 'CANONICAL SELECTED DRAFT', 'Deliver': json.dumps({
                                  'kind': 'reply', 'mode': 'reply_all', 'to': ['canonical-to@example.test', 'canonical-participant@example.test'],
                                  'cc': ['canonical-copy@example.test'], 'delivery': 'unknown'})})
            store.add_review({'TaskId': tid, 'MessageId': latest, 'Kind': 'draft_reply', 'Status': 'pending',
                              'DraftText': 'CANONICAL SIBLING DRAFT', 'Deliver': json.dumps({
                                  'kind': 'reply', 'to': ['canonical-sibling-to@example.test'],
                                  'cc': ['canonical-sibling-copy@example.test']})})
            store.add_attachment({'MessageId': older, 'Name': 'canonical-evidence.txt',
                                  'ContentType': 'text/plain', 'Size': 12, 'ExternalId': 'canonical-attachment'})
            standalone_message = message('Canonical standalone message', stamp,
                                         body='Standalone full source ' + 'y' * 6000 + ' CANONICAL MESSAGE END')
            task = store.create_task({'Title': 'Canonical standalone task', 'Status': 'open',
                                      'Summary': 'CANONICAL TASK BODY'}, 'fixture')
            store.set_task_checklist(task, ['Canonical retained checklist'], 'fixture')
            store.add_comment(task, 'fixture', 'user', 'Canonical retained task history')
            idea = store.upsert_idea({'key': 'canonical:independent-idea', 'kind': 'followup',
                                      'text': 'CANONICAL IDEA BODY'}, stamp)['IdeaId']
            review = store.add_review({'Kind': 'action', 'Status': 'pending', 'Reason': 'CANONICAL REVIEW BODY'})
            ignored = message('Canonical ignored remains in All', stamp, status='ignored')
            muted = message('Canonical muted remains in All', stamp, source='canonical-muted@example.test')
            funnel.remember_mute(store, {'sender': 'canonical-muted@example.test', 'words': [],
                                        'why': 'Synthetic existing exclusion'}, 'fixture')
            store.set_funnel_state(f'msg:{muted}', 'done', note='Fixture preserved owner state')
            upcoming = {'subject': 'Canonical upcoming meeting', 'start': (now + timedelta(minutes=45)).isoformat(),
                        'end': (now + timedelta(minutes=75)).isoformat(), 'who': ['Fixture attendee'],
                        'where': '', 'about': 'Synthetic calendar', 'all_day': False}
            started = {**upcoming, 'subject': 'Canonical started meeting',
                       'start': (now - timedelta(minutes=20)).isoformat(),
                       'end': (now + timedelta(minutes=10)).isoformat()}
            prep_title = 'Canonical calendar preparation'
            prep_task = store.create_task({'Title': 'Prep: ' + prep_title, 'Status': 'open',
                                           'Source': 'calendar', 'SourceRef': 'canonical:prep'}, 'fixture')
            prep_mid = message('Prep: ' + prep_title, stamp, task=prep_task, channel='own',
                               conversation=f"calendar:{upcoming['start']}:{upcoming['subject']}")
            # Eight roots above, including the calendar prep root. Existing demo and
            # held Current records are preserved; these are 507 additional roots.
            for index in range(507 - 8):
                message(f'Canonical census filler {index:04}',
                        (now - timedelta(hours=2, seconds=index)).isoformat(' '))
            result = store.reconcile_processing_membership()
            if result['status'] not in {'complete', 'already_current'}:
                raise HTTPException(409, result)
            calendar.today = lambda _store: {'date': now.date().isoformat(), 'now': now.strftime('%H:%M'),
                                             'events': [started, upcoming], 'tz': 'fixture local', 'errors': []}
            seeded.update(grouped={'item_id': root('message', older), 'message_ids': [older, latest],
                                   'member_count': len(store.processing_members(root('message', older))),
                                   'task_id': tid, 'selected_review_id': selected_review,
                                   'source_nonrepresentative': 'canonical-older@example.test',
                                   'full_body_marker': 'CANONICAL FULL BODY END',
                                   'selected_draft_marker': 'CANONICAL SELECTED DRAFT',
                                   'sibling_draft_marker': 'CANONICAL SIBLING DRAFT'},
                          standalone={kind: {'item_id': root(kind, value), 'id': value, 'body_marker': marker}
                                      for kind, value, marker in (
                                          ('message', standalone_message, 'CANONICAL MESSAGE END'),
                                          ('task', task, 'CANONICAL TASK BODY'), ('idea', idea, 'CANONICAL IDEA BODY'),
                                          ('review', review, 'CANONICAL REVIEW BODY'))},
                          ignored_item_id=root('message', ignored), muted_item_id=root('message', muted),
                          calendar={'upcoming': upcoming['subject'], 'started': started['subject'], 'prep': prep_title,
                                    'prep_item_id': root('message', prep_mid), 'prep_message_id': prep_mid},
                          total=processing_all.AllInventory().page(store)['counts']['total'])
        return seeded

    @app.post('/api/fixture/processing/canonical-arrival')
    def arrival(body: dict):
        if body != {'emit': False} or not seeded:
            raise HTTPException(422, 'seed first; arrival requires emit=false')
        with patch.object(processing_all.MembershipWorker, 'reconcile'), patch.object(store, '_poke'), patch.object(live, 'emit'):
            title = 'Canonical arrival after frozen first page'
            mid = message(title, datetime.now().isoformat(' '))
            store.reconcile_processing_membership()
            return {'item_id': root('message', mid), 'title': title}

    @app.post('/api/fixture/processing/canonical-emit')
    def emit():
        live.emit('feed-changed')
        return {'ok': True}

"""Pictures the Timeline and Board actually show, for regression tests.

A test that INSERT's a task row is not a regression: NeedsYou, the draft chip, a
thread attach, a held review, last year's Done - those are JOINs. This module
writes the same graph the funnel would have left, one named picture at a time,
on whatever store you hand it (MemoryStore for the suite, a file for load).

Two layers:
  inbound(...)     a dict ingest_message accepts (lowercase keys)
  Factory(store)   primitives (task/message/review) and named pictures
                   (pending_draft, running, filed_fyi, ...). Pictures return
                   ids; Factory.row(pic) is the Timeline row for that mail.

python -m taskuary.testing desk     # one of each picture into TASKUARY_HOME
python -m taskuary.testing load 2k  # the same mix, many times, for a load db
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

from .store import MemoryStore, SQLiteStore

_n = 0


def inbound(**kw):
    """A dict ingest_message accepts. Unique external_id unless you pass one.

    Defaults match the core-engine tests (channel api, a body that is real work)
    so swapping self.msg() for inbound() does not change a heuristic."""
    global _n
    _n += 1
    base = {'external_id': f'in-{_n}', 'channel': 'api', 'subject': 's',
            'body': 'please add the new user to the system', 'from_email': 'a@b.com',
            'conversation_id': None, 'sent_at': '2026-08-17 09:00',
            'source_link': None, 'from_name': 'A'}
    return {**base, **kw}


def _pic(**kw):
    return SimpleNamespace(**kw)


class Factory:
    """One store, monotonically unique ExternalIds, named pictures."""

    def __init__(self, store=None):
        self.s = store if store is not None else MemoryStore()
        self._n = 0
        self.actor = 't'

    def _xid(self, prefix='x'):
        self._n += 1
        return f'{prefix}-{self._n}'

    def ago(self, hours=0, minutes=0):
        return (datetime.now() - timedelta(hours=hours, minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')

    # ── primitives (return ids) ──────────────────────────────────────────────
    def task(self, title='work', status='open', kind='general', source='email', **kw):
        fields = {'Title': title, 'Status': status, 'Kind': kind, 'Source': source, **kw}
        return self.s.create_task(fields, self.actor)

    def message(self, task_id=None, status='routed', channel='email', **kw):
        fields = {'TaskId': task_id, 'Status': status, 'Channel': channel,
                  'ExternalId': kw.pop('external_id', None) or self._xid(),
                  'Subject': kw.pop('subject', 'please look'),
                  'FromName': kw.pop('from_name', 'Sam Okafor'),
                  'FromEmail': kw.pop('from_email', 'sam@example.com'),
                  'BodyText': kw.pop('body', 'x'),
                  'SentAt': kw.pop('sent_at', None) or self.ago(),
                  'SourceName': kw.pop('source_name', None),
                  'ConversationId': kw.pop('conversation_id', None),
                  'Direction': kw.pop('direction', 'in')}
        fields.update(kw)
        fields = {k: v for k, v in fields.items() if v is not None}
        return self.s.add_message(fields)

    def route(self, mid, tid, decision='create', reason='real work', score=None,
              candidates=None, by='triage'):
        return self.s.add_route(mid, tid, decision, score, reason, candidates or [], by)

    def review(self, task_id, message_id=None, status='pending', kind='draft',
               reason='AI drafted a reply', draft='Hi - done.', final=None, **kw):
        fields = {'TaskId': task_id, 'MessageId': message_id, 'Status': status, 'Kind': kind,
                  'Reason': reason, 'DraftText': draft, 'FinalText': final}
        fields.update(kw)
        fields = {k: v for k, v in fields.items() if v is not None}
        return self.s.add_review(fields)

    def run(self, task_id, status='running', agent='coder', instruction='go'):
        rid = self.s.start_run(task_id, agent, instruction, self.actor)
        if status != 'running':
            self.s.update_run(rid, {'Status': status}, finished=status in ('done', 'failed'))
        return rid

    def attachment(self, message_id, name='shot.png', content_type='image/png'):
        return self.s.add_attachment({'MessageId': message_id, 'Name': name, 'ContentType': content_type})

    def comment(self, task_id, body, actor=None, actor_type='agent'):
        return self.s.add_comment(task_id, actor or self.actor, actor_type, body)

    def waiting(self, task_id, note='also handle the null case'):
        return self.s.add_waiting(task_id, note, self.actor)

    def queued(self, task_id, behind, agent='coder', reason='overlap'):
        return self.s.enqueue_dispatch(task_id, behind, agent, reason)

    def policy(self, pattern, action='ignore', kind='subject', reason='automated', **kw):
        return self.s.save_policy({'Name': kw.pop('name', pattern), 'Kind': kind, 'Pattern': pattern,
                                   'Action': action, 'Reason': reason, **kw}, self.actor)

    def memory(self, note, scope='sender', scope_key='n@n.com', source='verdict'):
        return self.s.add_memory({'Scope': scope, 'ScopeKey': scope_key, 'Note': note,
                                  'Source': source, 'Active': 1, 'CreatedBy': self.actor})

    def row(self, pic, limit=200):
        """The Timeline row for this picture's mail. Fail loud if it is not on the feed."""
        mid = pic.mid if hasattr(pic, 'mid') else pic
        return next(r for r in self.s.feed(limit=limit) if r['MessageId'] == mid)

    # ── a routed mail on a task (the common stem) ────────────────────────────
    def _work(self, title, status='open', kind='general', decision='create',
              reason='real work', **msg):
        tid = self.task(title=title, status=status, kind=kind, source=msg.get('channel', 'email'))
        mid = self.message(task_id=tid, **msg)
        self.route(mid, tid, decision, reason)
        return tid, mid

    # ── named pictures (the JOIN contract) ───────────────────────────────────
    def pending_draft(self, title='Q3 vendor spend?', **kw):
        """Open reply-task + inbound + pending draft. Timeline NeedsYou + Review chip."""
        draft = kw.pop('draft', 'Hi - done.')
        tid, mid = self._work(title, kind='reply', **kw)
        rid = self.review(tid, mid, draft=draft)
        return _pic(tid=tid, mid=mid, rid=rid)

    def held_draft(self, title='held draft'):
        """Park the pending reply while an agent works it. Leaves the Review queue."""
        p = self.pending_draft(title=title)
        self.s.hold_reviews(p.tid, 'held while an agent works the task')
        return p

    def rejected_draft(self, title='rejected draft'):
        p = self.pending_draft(title=title)
        self.s.decide_review(p.rid, 'rejected', '', self.actor)
        return p

    def approved_done(self, title='finished today'):
        """Done today with an approved review. Board active_only still shows it."""
        tid, mid = self._work(title, status='open', kind='reply')
        rid = self.review(tid, mid, status='approved', draft='Hi - fixed.', final='Hi - fixed.')
        self.s.update_task(tid, {'Status': 'done'}, self.actor)
        return _pic(tid=tid, mid=mid, rid=rid)

    def old_done(self, title='finished last year'):
        """Last year's Done. The Board's ?active=1 must drop it; Tasks keeps it."""
        p = self.approved_done(title=title)
        self.s._exec("UPDATE task SET ClosedAt='2020-01-01 12:00:00', UpdatedAt='2020-01-01 12:00:00' WHERE TaskId=?",
                     (p.tid,))
        return p

    def dropped(self, title='dropped work'):
        tid, mid = self._work(title)
        rid = self.review(tid, mid)
        self.s.update_task(tid, {'Status': 'dropped'}, self.actor)
        return _pic(tid=tid, mid=mid, rid=rid)

    def running(self, title='busy work', agent='coder'):
        """An agent is on it: NeedsYou flips off even with no review."""
        tid, mid = self._work(title, status='in_progress', kind='coding')
        run_id = self.run(tid, agent=agent)
        return _pic(tid=tid, mid=mid, run_id=run_id)

    def open_task(self, title='open work'):
        """Routed, nobody working it, no draft. NeedsYou because it is yours."""
        tid, mid = self._work(title)
        return _pic(tid=tid, mid=mid)

    def filed_fyi(self, subject='Weekly platform digest', **kw):
        subject = kw.pop('title', subject)
        mid = self.message(task_id=None, status='filed', subject=subject,
                           from_email='no-reply@vendor.example.com', from_name='Platform Updates',
                           body='This is an automated summary of platform changes this week.')
        self.route(mid, None, 'file', 'automated/informational')
        return _pic(tid=None, mid=mid)

    def ignored(self, subject='unsubscribe here', **kw):
        subject = kw.pop('title', subject)
        mid = self.message(task_id=None, status='ignored', subject=subject,
                           from_email='n@n.com', body='click to unsubscribe')
        self.route(mid, None, 'ignore', 'policy')
        return _pic(tid=None, mid=mid)

    def feed_only(self, subject='org/app#2 a PR', **kw):
        """A feed-role connection: shown, never triaged."""
        subject = kw.pop('title', subject)
        mid = self.message(task_id=None, status='feed', channel='github', subject=subject,
                           from_email='kai', body='please merge')
        self.route(mid, None, 'file', 'feed role')
        return _pic(tid=None, mid=mid)

    def report_row(self, title='Nightly census'):
        sid = self.s.save_source({'Channel': 'report', 'Address': title, 'Active': 1,
                                  'ConfigJson': '{"type": "mssql", "title": "%s"}' % title}, self.actor)
        mid = self.message(task_id=None, status='filed', channel='report', subject=f'{title} - 4 rows',
                           source_name=title, from_name=title, conversation_id=f'report:{sid}',
                           body='{"facility": "Lakeview", "census": 112}')
        self.route(mid, None, 'file', 'scheduled report', by='report')
        return _pic(tid=None, mid=mid, sid=sid)

    def auto_replied(self, title='Standup moved to 10:30?'):
        tid, mid = self._work(title, status='done', kind='reply', channel='teams',
                              source_name='Ops chat', from_name='Priya Nair')
        rid = self.review(tid, mid, status='auto', kind='auto',
                          draft='Yes - 10:30 today only.', final='Yes - 10:30 today only.')
        return _pic(tid=tid, mid=mid, rid=rid)

    def messenger(self, channel='telegram', title='Can you resend the Q3 numbers?'):
        tid, mid = self._work(title, kind='reply', channel=channel,
                             conversation_id=f'{channel}:88214', from_name='Leah Stern',
                             from_email='@leahstern', source_name=f'Leah ({channel})',
                             body='Hey - can you resend the Q3 numbers?')
        rid = self.review(tid, mid)
        return _pic(tid=tid, mid=mid, rid=rid)

    def thread(self, title='Onboard the new AP clerk', n=2):
        """n messages on one conversation. ChainSize is the non-context count."""
        conv = self._xid('c')
        tid, mid = self._work(title, conversation_id=conv)
        mids = [mid]
        for i in range(1, n):
            m = self.message(task_id=tid, conversation_id=conv, subject=f'RE: {title}',
                             body=f'and one more thing {i}')
            self.route(m, tid, 'attach', 'same conversation thread', score=0.81)
            mids.append(m)
        return _pic(tid=tid, mid=mid, mids=mids, conversation_id=conv)

    def with_attachment(self, title='please fix with a screenshot'):
        p = self.pending_draft(title=title)
        aid = self.attachment(p.mid)
        follow = self.message(task_id=p.tid, subject=f'RE: {title}', body='also the logs')
        self.route(follow, p.tid, 'attach', 'same conversation thread')
        p.aid, p.follow = aid, follow
        return p

    def behind(self, title='Add CSV export'):
        """Queued behind a running task whose files it would touch."""
        busy = self.running(title='Report charts render blank in dark mode', agent='claude')
        tid, mid = self._work(title, kind='coding')
        self.queued(tid, busy.tid, agent='claude', reason='both would modify website/src/ReportsView.jsx')
        self.comment(tid, f'Queued behind TQ-{busy.tid:04d} - both would modify the same file.',
                     actor='router')
        return _pic(tid=tid, mid=mid, behind=busy)

    def waitroom_note(self, title='PTO import', note='confirm reconciliation=True'):
        p = self.running(title=title)
        wid = self.waiting(p.tid, note)
        p.wid = wid
        return p

    def handover(self, title='live', note='HANDOVER NOTE found: date parse\ndid: nothing yet\nnext: patch it'):
        """Latest HANDOVER NOTE lands on list_tasks. An ordinary comment after it must not win."""
        tid = self.task(title=title, status='in_progress', kind='coding')
        self.review(tid, status='approved')
        rid = self.review(tid, status='pending')
        self.run(tid, agent='coder')
        run_id = self.run(tid, agent='codex')
        self.comment(tid, note, actor='coder')
        self.comment(tid, 'ordinary comment', actor='coder')
        return _pic(tid=tid, rid=rid, run_id=run_id)

    def late_pending_on_done(self, title='already closed'):
        """A pending review added after the task is done: queue hides it, live_only=False still sees it."""
        tid, mid = self._work(title)
        self.s.update_task(tid, {'Status': 'done'}, self.actor)
        rid = self.review(tid, mid, kind='draft_reply')
        return _pic(tid=tid, mid=mid, rid=rid)

    def skipped_pending(self, title='hidden by skip'):
        """Skip-hidden mail must not keep the Review badge at 1."""
        p = self.pending_draft(title=title)
        self.s.set_message_status(p.mid, 'skipped')
        return p

    def attachable(self, title='PTO import', conv='c1'):
        """A live coding task with an original mail - the inbound-answer attach hook."""
        tid, mid = self._work(title, status='in_progress', kind='coding',
                              conversation_id=conv, subject=title, sent_at='2026-08-23 09:00:00')
        return _pic(tid=tid, mid=mid, conversation_id=conv)

    # ── the desk: one of each live picture, the JOIN regression set ──────────
    def timeline(self):
        """The four rows the Timeline JOIN pins: pending+attach+file, done, running, fyi."""
        pending = self.with_attachment(title='please fix')
        done = self.approved_done(title='thanks')
        busy = self.running(title='working')
        fyi = self.filed_fyi()
        return _pic(pending=pending, done=done, busy=busy, fyi=fyi,
                    open=pending.mid, done_mid=done.mid, busy_mid=busy.mid, fyi_mid=fyi.mid)

    def desk(self):
        """One of every named picture. A JOIN rewrite that drops a chip fails this set."""
        names = ('pending_draft', 'held_draft', 'rejected_draft', 'approved_done', 'old_done',
                 'dropped', 'running', 'open_task', 'filed_fyi', 'ignored', 'feed_only',
                 'report_row', 'auto_replied', 'messenger', 'thread', 'with_attachment',
                 'behind', 'waitroom_note', 'handover', 'late_pending_on_done', 'skipped_pending',
                 'attachable')
        out = {}
        for name in names:
            out[name] = getattr(self, name)()
        return out

    def fill(self, n=200):
        """Cycle the live mix so a load db has real JOIN shape, not one kind of row."""
        makers = (self.pending_draft, self.running, self.filed_fyi, self.approved_done,
                  self.open_task, self.thread, self.ignored, self.messenger)
        pics = []
        for i in range(int(n)):
            pics.append(makers[i % len(makers)](title=f'load {i}'))
        return pics


def _open_home():
    from . import config
    return SQLiteStore(config.db_path())


def main(argv=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = (argv[0] if argv else 'help').lower()
    if cmd in ('-h', '--help', 'help'):
        print('usage: python -m taskuary.testing desk|load [N]\n'
              '  desk  one of each picture into TASKUARY_HOME\n'
              '  load  N rows of the live mix (default 2000)')
        return 0
    fx = Factory(_open_home())
    if cmd == 'desk':
        d = fx.desk()
        print(f'desk: {len(d)} pictures, feed {len(fx.s.feed(limit=500))} rows, '
              f'tasks {len(fx.s.list_tasks())}')
        return 0
    if cmd == 'load':
        n = int(str(argv[1]).rstrip('kK')) * (1000 if str(argv[1]).lower().endswith('k') else 1) if len(argv) > 1 else 2000
        fx.fill(n)
        print(f'load: {n} pictures, feed {len(fx.s.feed(limit=500))} (capped), tasks {len(fx.s.list_tasks())}')
        return 0
    print(f'unknown command: {cmd}', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())

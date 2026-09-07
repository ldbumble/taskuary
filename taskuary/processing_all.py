"""Canonical All presentation and bounded, frozen HTTP pagination.

This module does not allocate membership or infer canonical read/action state. The
explicit membership reconciler owns writes; an incomplete census cannot be exposed
as a successfully empty All. Only compact presentation rows survive in a lease.
"""
from collections import OrderedDict
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import asyncio
import base64
import copy
import hashlib
import json
import threading
import time
import uuid
import weakref
from loguru import logger

from .categories import category_of, team_domains_of
from .processing_order import feed_band


def idea_lane(idea: dict) -> str:
    """An idea's lane from its own triage - the same rule the unread pile applies (processing_unread.card_for)."""
    try: action = json.loads(idea.get('ActionJson') or '{}')
    except (ValueError, TypeError): action = {}
    triage = action.get('triage') or {}
    return 'asked' if triage.get('intent') in ('task', 'reply_only') else 'report' if action.get('section') == 'systems' else 'fyi'


def row_lane(row: dict) -> str:
    """The pile's word for a feed row, so All and unread say the same thing about one item."""
    if row.get('ReportFailed'): return 'broken'
    if (row.get('TaskStatus') in ('open', 'in_progress') and str(row.get('Assignee') or '').startswith('agent:')
            and not row.get('Working') and not row.get('AgentWaiting')): return 'queued'
    return {1: 'time', 2: 'approve', 3: 'report' if row.get('Channel') == 'report' else 'asked', 4: 'fyi', 5: 'working'}[feed_band(row)]


SCHEMA = 'taskuary.processing.all.v1'
MEMBERSHIP_RULES = 'idea-joins-task-1'     # bump when reconcile_membership groups entities differently
PRESENTATION_VERSION = 1
HIDDEN_MESSAGES = {'context', 'history', 'skipped'}


class AllError(Exception):   # not a ValueError: the routes that map ValueError to 422 must not swallow it
    def __init__(self, code, message, status=409, **extra):
        super().__init__(message)
        self.status = status
        self.detail = {'code': code, 'message': message, **extra}


SETTLE_WAIT, SETTLE_TICK = 1.5, 0.05
def wait_settled(store, wait: float = SETTLE_WAIT) -> bool:
    """A read that lands inside the membership worker's lag waits for it instead of failing: every
    write bumps the dirty generation, so without this each chat line and each shown item made the
    next read say "All items are not ready yet". Conflicted membership is a real refusal, not a race."""
    status = getattr(store, 'processing_reconcile_status', None)
    if status is None or getattr(store, 'membership_worker', None) is None: return True   # nobody to wait for: tests, bare stores
    deadline = time.monotonic() + wait
    while True:
        st = status()
        if st['dirty_generation'] <= st['reconciled_generation'] or st.get('status') == 'conflicted': return True
        if time.monotonic() >= deadline: return False
        time.sleep(SETTLE_TICK)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _stamp(value):
    """Keep legacy stored-local chronology explicit; never invent a UTC offset."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _time_key(value):
    parsed = _stamp(value)
    return ((parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute,
             parsed.second, parsed.microsecond) if parsed else None)


def _newest(rows, field, id_field):
    return max(rows, key=lambda r: (_time_key(r.get(field)) or (), r.get(id_field) or 0)) if rows else None


def _owned(item, kind, id_field, collection):
    ids = {mid.split(':', 1)[1] for mid in item.get('member_ids', [])
           if mid.startswith(kind + ':')}
    return [r for r in item.get('view', {}).get(collection, []) if str(r.get(id_field)) in ids]


def normalize_query(channel=None, source=None, days=14):
    if isinstance(days, bool) or not isinstance(days, int) or not 0 <= days <= 36500:
        raise AllError('processing_query_invalid', 'Invalid history interval', 422)
    if channel is not None and not isinstance(channel, str):
        raise AllError('processing_query_invalid', 'Invalid channel', 422)
    if source is not None and not isinstance(source, str):
        raise AllError('processing_query_invalid', 'Invalid source', 422)
    return {'channel': sorted({part.strip() for part in (channel or '').split(',') if part.strip()}),
            'source': source or '', 'days': days, 'order': 'stored_local_newest',
            'presentation_version': PRESENTATION_VERSION}


def _matches(channel, source, query):
    return ((not query['channel'] or channel in query['channel'])
            and (not query['source'] or source == query['source']))


def _in_history(value, cutoff):
    stamp = _stamp(value)
    return stamp is None or stamp >= cutoff


def _thread_index(items):
    messages = {}
    for item in items:
        for message in item.get('view', {}).get('messages', []):
            messages[message['MessageId']] = message
    threads = {}
    for message in messages.values():
        if message.get('ConversationId'):
            threads.setdefault(message['ConversationId'], []).append(message)
    return threads


def message_row(message, item, threads, now, *, full=False):
    """The existing All status presentation, from the same captured inventory.

    NeedsYou here remains the legacy display chip, not canonical eligibility/read
    state. Bare-conversation reply presentation retains the existing feed contract;
    it does not create membership or claim account-scoped chain completion.
    """
    view = item['view']
    mid, tid = message['MessageId'], message.get('TaskId')
    task = next((t for t in view.get('tasks', []) if t['TaskId'] == tid), {})
    reviews = [r for r in view.get('reviews', []) if r.get('MessageId') == mid]
    review = max(reviews, key=lambda r: r['ReviewId']) if reviews else {}
    routes = [r for r in view.get('routes', []) if r.get('MessageId') == mid]
    route = max(routes, key=lambda r: r['RouteId']) if routes else {}
    thread = threads.get(message.get('ConversationId'), [])
    sent = message.get('SentAt') or ''
    answered = max((m.get('SentAt') or '' for m in thread
                    if message.get('SentAt') is not None and m.get('Status') == 'context'
                    and (m.get('SentAt') or '') > sent), default=None)
    last = _newest([m for m in thread if m.get('Status') is not None and m.get('Status') != 'skipped'], 'SentAt', 'MessageId') or {}
    yours = last.get('Status') == 'context' or last.get('Direction') == 'out'
    decision_at = review.get('DecidedAt') if review.get('DecidedAt') is not None else review.get('CreatedAt')
    sent_unanswered = (review.get('Status') in {'approved', 'edited', 'sent'}
                       and review.get('Kind') is not None and review.get('Kind') != 'action' and not any(
                           m.get('Status') is not None and m.get('Status') not in HIDDEN_MESSAGES
                           and m.get('Direction') != 'out' and decision_at is not None
                           and m.get('SentAt') is not None and m['SentAt'] > decision_at for m in thread))
    active_task = bool(tid) and task.get('Status') not in {'done', 'dropped'}
    theirs = bool(active_task and (yours or sent_unanswered))
    running = [r for r in view.get('runs', []) if r.get('TaskId') == tid and r.get('Status') == 'running']
    needs = review.get('Status') == 'pending' or (
        active_task and not running and (task.get('Kind') != 'note' or (message.get('SentAt') is not None and sent <= now))
        and message.get('Status') is not None and message.get('Status') != 'withdrawn' and answered is None and not theirs)
    row = {key: message.get(key) for key in (
        'MessageId', 'Channel', 'SourceName', 'Subject', 'FromName', 'FromEmail', 'SentAt',
        'ConversationId', 'SourceLink', 'TaskId', 'Direction')}
    row.update(IngestedAt=message.get('CreatedAt'), Preview=(message.get('BodyText') or '')[:4000 if full else 400],
               MsgStatus=message.get('Status'), Title=task.get('Title'), TaskStatus=task.get('Status'), Assignee=task.get('Assignee'),
               Priority=task.get('Priority'), TaskKind=task.get('Kind'), TaskTags=task.get('Tags'),
               NeedsYou=int(needs), ChainSize=sum(m.get('Status') not in {'context', 'history'}
                                                for m in view.get('messages', [])) if tid else 0,
               Decision=route.get('Decision'), RouteReason=route.get('Reason'),
               ReviewId=review.get('ReviewId'), ReviewStatus=review.get('Status'),
               ReviewKind=review.get('Kind'), HasDraft=int(bool(review.get('DraftText'))),
               DraftError=review.get('DraftError'),
               Attachments=sum(a.get('MessageId') == mid for a in view.get('attachments', [])),
               AnsweredAt=answered, TheirTurn=int(theirs))
    workers = [r for r in view.get('worker_attention', [])
               if str(r.get('taskId', r.get('task_id'))) == str(tid)] if tid else []
    working = (running[-1].get('AgentName') or 'agent') if running else None
    waiting = False
    for worker in workers:
        working = worker.get('agent') or worker.get('label') or 'coder'
        waiting = waiting or bool(worker.get('waiting'))
    if working and active_task:
        row.update(Working=working, AgentWaiting=waiting)
        if review.get('Status') != 'pending':
            row['NeedsYou'] = int(waiting)
    # Classification needs the existing 4k window even when the HTTP preview is compact.
    row['Category'] = category_of({**row, 'Preview': (message.get('BodyText') or '')[:4000]},
                                  team_domains_of(view.get('settings', {})))
    if row.get('Channel') == 'report':
        from .funnel import _FAILED
        row['ReportFailed'] = view.get('report_outcomes', {}).get(str(row.get('SourceName') or ''),
                                                                bool(_FAILED.search(str(row.get('Subject') or ''))))
    if full:
        row.update(BodyText=message.get('BodyText'), Brief=message.get('Brief'))
    row['Lane'] = row_lane(row)          # after ReportFailed and NeedsYou: the pile's word for this row
    return row


def _muted_candidate(item, row, lane=None):
    """Existing standing rules apply to candidate members in both views."""
    from .funnel import muted, MUTED_LANES
    from .processing_order import feed_band
    try:
        rules = json.loads(item['view'].get('settings', {}).get('funnel_mutes') or '[]')
    except (ValueError, TypeError):
        rules = []
    if not isinstance(rules, list):
        return False
    lane = lane or row_lane(row)
    if lane not in MUTED_LANES:
        return False
    if row.get('ReportFailed'):
        return False
    candidate = {'email': row.get('FromEmail'), 'who': row.get('FromName'),
                 'title': row.get('Subject') or row.get('Title'), 'lane': lane}
    return any(isinstance(rule, dict) and muted(rule, candidate) for rule in rules)


def _generic_target(item, query, cutoff, include_excluded=False):
    if item['view'].get('messages'):
        return None  # Hidden or filtered message roots must not reappear as generic work.
    for kind, id_field, collection, stamp_field in (
            ('task', 'TaskId', 'tasks', 'CreatedAt'),
            ('idea', 'IdeaId', 'ideas', 'LastSaid'),
            ('review', 'ReviewId', 'reviews', 'CreatedAt')):
        rows = _owned(item, kind, id_field, collection)
        # A filtered-out message-backed task must not reappear as an unfiltered task.
        if kind == 'task' and item['view'].get('messages'):
            continue
        candidates = []
        for entity in rows:
            if kind == 'task' and entity.get('SourceRef') == 'assistant:dock':
                continue  # Existing task-list boundary: persistent application chrome, not work.
            channel = 'assistant' if kind == 'idea' else 'own'
            source = str(entity.get('Source') or '')
            stamp = entity.get(stamp_field) or entity.get('FirstSeen') or entity.get('CreatedAt')
            candidate = {'Subject': entity.get('Title') or entity.get('Text') or entity.get('Reason'),
                         'FromName': entity.get('CreatedBy'), 'Channel': channel}
            lane = 'asked' if kind == 'task' else 'approve' if kind == 'review' else 'fyi'
            if kind == 'idea':
                try:
                    action = json.loads(entity.get('ActionJson') or '{}')
                    if (action.get('triage') or {}).get('intent') in ('task', 'reply_only'):
                        lane = 'asked'
                except (ValueError, TypeError):
                    pass
            if (_matches(channel, source, query) and _in_history(stamp, cutoff)
                    and (include_excluded or not _muted_candidate(item, candidate, lane))):
                candidates.append((entity, stamp, channel, source))
        if candidates:
            entity, stamp, channel, source = max(candidates, key=lambda x: (_time_key(x[1]) or (), x[0][id_field]))
            return kind, entity, stamp, channel, source
    return None


def compact_inventory(snapshot, query, *, include_excluded=False):
    coverage = copy.deepcopy(snapshot['coverage'])
    reconciliation = coverage.get('processing_reconciliation') or {}
    if (reconciliation.get('pending', True) or reconciliation.get('status') == 'conflicted'
            or any(coverage.get('uncatalogued', {}).values())):
        raise AllError('processing_coverage_pending', 'All items are not ready yet', coverage=coverage)
    now = _stamp(snapshot['as_of'])
    if now is None:
        raise AllError('processing_query_invalid', 'Invalid snapshot time', 422)
    cutoff = now - timedelta(days=query['days'])
    threads = _thread_index(snapshot['items'])
    rows, hidden, tombstones = [], 0, 0
    for item in snapshot['items']:
        members = item.get('member_ids', [])
        if not members:
            tombstones += 1
            continue
        view = item['view']
        # an Assistant digest post is only the container for its ideas, which are roots of their own; in both
        # views it is not presented (the duplicate-Assistant regression of 2026-09-04, back on 2026-09-06)
        from .funnel import _assistant_wrapper
        candidates = [m for m in view.get('messages', []) if m.get('Status') not in HIDDEN_MESSAGES and not _assistant_wrapper(m)
                      and _matches(m.get('Channel'), m.get('SourceName'), query)
                      and _in_history(m.get('CreatedAt'), cutoff)]
        if (view.get('processing_read') or {}).get('active') and not include_excluded:
            candidates = [m for m in candidates if not _muted_candidate(
                item, message_row(m, item, threads, now.strftime('%Y-%m-%d %H:%M:%S')))]
        message = _newest(candidates, 'SentAt', 'MessageId')
        if message:
            legacy = message_row(message, item, threads, now.strftime('%Y-%m-%d %H:%M:%S'))
            target = {'kind': 'message', 'id': message['MessageId']}
            title = message.get('Subject') or legacy.get('Title') or 'Message'
            actor, stamp = message.get('FromName') or message.get('FromEmail') or '', message.get('SentAt') or message.get('CreatedAt')
            channel, source, status = message.get('Channel') or '', message.get('SourceName') or '', message.get('Status') or ''
            preview, category = legacy['Preview'], legacy['Category']
        else:
            generic = _generic_target(item, query, cutoff, include_excluded=include_excluded or not (view.get('processing_read') or {}).get('active'))
            if not generic:
                hidden += 1
                continue
            kind, entity, stamp, channel, source = generic
            id_field = {'task': 'TaskId', 'idea': 'IdeaId', 'review': 'ReviewId'}[kind]
            target = {'kind': kind, 'id': entity[id_field]}
            title = entity.get('Title') or entity.get('Subject') or entity.get('Text') or entity.get('Reason') or kind.title()
            # an idea is the assistant's own word; idea rows carry no author field, and the fallback read "unknown"
            actor, status = (entity.get('CreatedBy') or ('Assistant' if kind == 'idea' else '')), entity.get('Status') or ''
            preview = str(entity.get('Summary') or entity.get('Text') or entity.get('Reason') or '')[:400]
            category = 'todo' if kind == 'task' else kind
            open_task = kind == 'task' and status in ('open', 'in_progress', 'waiting')
            legacy = {'Channel': channel, 'SourceName': source, 'Subject': str(title)[:240],
                      'SentAt': stamp, 'IngestedAt': entity.get('CreatedAt') or entity.get('FirstSeen'),
                      'Preview': preview, 'MsgStatus': status, 'Category': category,
                      'Lane': ('queued' if str(entity.get('Assignee') or '').startswith('agent:') else 'asked') if open_task
                              else 'approve' if kind == 'review' else idea_lane(entity) if kind == 'idea' else 'fyi'}
        counts = {kind: sum(mid.startswith(prefix + ':') for mid in members) for kind, prefix in (
            ('messages', 'message'), ('tasks', 'task'), ('ideas', 'idea'), ('reviews', 'review'))}
        counts.update(members=len(members), attachments=len(view.get('attachments', [])))
        if (view.get('processing_read') or {}).get('active'):
            from .processing_reads import state
            read = state(item, now)
            active_tasks = {t['TaskId'] for t in view.get('tasks', []) if t.get('Status') not in ('done', 'dropped')}
            working = bool((legacy.get('Working') and legacy.get('TaskStatus') not in ('done', 'dropped'))
                           or any(w.get('taskId') in active_tasks for w in view.get('worker_attention', []))
                           or any(r.get('TaskId') in active_tasks and r.get('Status') == 'running' for r in view.get('runs', [])))
            legacy.update(Unread=int((read['unread'] and not read.get('deferred')) or working), Deferred=bool(read.get('deferred')),
                          DeferUntil=read.get('defer_until'), FunnelKey='processing:' + item['item_id'])
        rows.append({'item_id': item['item_id'], 'member_ids': list(members),
                     'display_message_ids': [m['MessageId'] for m in candidates],
                     'context_revision': item['context_revision'], 'view_revision': item['view_revision'],
                     'activity_at': stamp if _stamp(stamp) else None,
                     'activity_basis': 'stored_local_wall_clock' if _stamp(stamp) else 'unknown',
                     'title': str(title)[:240], 'actor': str(actor)[:240], 'preview': preview,
                     'channel': channel, 'source': source, 'category': category, 'status': status,
                     'counts': counts, 'open_target': target, 'row': legacy})
    rows.sort(key=lambda row: (0, tuple(-v for v in _time_key(row['activity_at'])), row['item_id'])
              if _time_key(row['activity_at']) else (1, (), row['item_id']))
    today = [row for row in rows if (_stamp(row['activity_at']) or datetime.min).date() == now.date()]
    return rows, coverage, {'total': len(rows),
                            'canonical_roots': coverage.get('canonical_item_count', len(snapshot['items'])),
                            'tombstones': tombstones, 'not_presented': hidden,
                            'today': len(today), 'today_info': sum(r['category'] == 'info' for r in today),
                            'today_promo': sum(r['category'] == 'promo' for r in today),
                            'today_ignored': sum(r['status'] == 'ignored' for r in today)}


class AllInventory:
    def __init__(self, *, ttl=120, max_leases=8, clock=time.monotonic):
        self.ttl, self.max_leases, self.clock = ttl, max_leases, clock
        self._stores = weakref.WeakKeyDictionary()
        self._lock = threading.RLock()

    def page(self, store, *, channel=None, source=None, days=14, limit=100, cursor=None,
             fixed_now=None, live_state=None):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise AllError('processing_query_invalid', 'Page size must be between 1 and 500', 422)
        query = normalize_query(channel, source, days)
        query_revision = _digest(query)
        wait_settled(store)
        position, lease_id = 0, None
        if cursor is not None:
            try:
                if not isinstance(cursor, str) or len(cursor) > 2048:
                    raise ValueError()
                payload = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
                if set(payload) != {'lease', 'position', 'query', 'anchor'}:
                    raise ValueError()
                lease_id, position = payload['lease'], payload['position']
                if (not isinstance(lease_id, str) or isinstance(position, bool)
                        or not isinstance(position, int) or position <= 0 or payload['query'] != query_revision):
                    raise ValueError()
            except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
                raise AllError('processing_query_invalid', 'Invalid page cursor or changed query', 422) from None
        if lease_id is None:
            snapshot = store.processing_inventory_snapshot(
                fixed_now=fixed_now or datetime.now().isoformat(), live_state=live_state,
                display_only=True, history_days=query['days'])
            rows, coverage, counts = compact_inventory(snapshot, query)
            lease_id = uuid.uuid4().hex
            lease = {'created': self.clock(), 'query': query_revision, 'items': rows,
                     'snapshot_revision': snapshot['snapshot_revision'], 'coverage': coverage, 'counts': counts}
        with self._lock:
            leases = self._stores.setdefault(store, OrderedDict())
            for key in list(leases):
                if self.clock() - leases[key]['created'] >= self.ttl:
                    del leases[key]
            if cursor is None:
                leases[lease_id] = lease
                while len(leases) > self.max_leases:
                    leases.popitem(last=False)
            else:
                lease = leases.get(lease_id)
                if lease is None:
                    raise AllError('processing_snapshot_expired', 'This page snapshot expired; refresh All')
                if (lease['query'] != query_revision or position >= len(lease['items'])
                        or payload['anchor'] != lease['items'][position - 1]['item_id']):
                    raise AllError('processing_query_invalid', 'Invalid page cursor', 422)
                leases.move_to_end(lease_id)
            end = min(position + limit, len(lease['items']))
            next_cursor = None
            if end < len(lease['items']):
                next_cursor = base64.urlsafe_b64encode(_json({
                    'lease': lease_id, 'position': end, 'query': query_revision,
                    'anchor': lease['items'][end - 1]['item_id']}).encode()).decode().rstrip('=')
            return copy.deepcopy({'schema_version': SCHEMA, 'snapshot_revision': lease['snapshot_revision'],
                                  'lease': lease_id, 'next_cursor': next_cursor,
                                  'counts': {**lease['counts'], 'returned': end - position},
                                  'coverage': lease['coverage'], 'items': lease['items'][position:end]})


inventory = AllInventory()


class MembershipWorker:
    """One explicitly owned reconciliation loop; external SQL writes also wake All."""
    def __init__(self, store, *, interval=0.25, notify=None):
        self.store, self.interval, self.notify = store, interval, notify
        self.stop = threading.Event()
        self.thread = None

    def reconcile(self):
        state = self.store.processing_reconcile_status()
        if state['dirty_generation'] <= state['attempted_generation']:
            return
        result = self.store.reconcile_processing_membership()
        if self.notify:
            self.notify(result)

    def start(self):
        def run():
            # the grouping rule changed (an idea joins its task): every existing install reconciles once.
            # The setting is in PROCESSING_DIRTY_SETTINGS, so writing it is what makes the loop below work.
            try:
                if self.store.get_settings().get('processing_membership_rules') != MEMBERSHIP_RULES:
                    self.store.set_setting('processing_membership_rules', MEMBERSHIP_RULES, 'system')
            except Exception as exc: logger.warning(f'processing membership rule stamp failed: {exc}')
            while not self.stop.is_set():
                delay = self.interval
                try:
                    self.reconcile()
                except Exception as exc:
                    logger.warning(f'processing membership refresh failed: {exc}')
                    delay = max(self.interval, 5.0)
                if self.stop.wait(delay):
                    break
        self.thread = threading.Thread(target=run, name='processing-membership', daemon=True)
        self.thread.start()
        self.store.membership_worker = self       # readers wait for a worker that exists (wait_settled)

    def close(self):
        self.stop.set()
        self.store.membership_worker = None
        if self.thread:
            self.thread.join()  # Do not close its store or abandon a transaction during shutdown.


@asynccontextmanager
async def membership_lifecycle(store):
    from . import live
    # a tick that reconciled nothing is not news: it made every open Assistant tab force a rebuild
    changed = lambda r: any(r.get(k) for k in ('created_items', 'created_members', 'moved_members', 'retired_members',
                                                'redirected_items', 'created_aliases', 'created_relations', 'retired_relations'))
    worker = MembershipWorker(store, notify=lambda r: changed(r) and live.emit('feed-changed'))
    worker.start()
    try:
        yield
    finally:
        closing = asyncio.create_task(asyncio.to_thread(worker.close))
        try:
            await asyncio.shield(closing)
        except asyncio.CancelledError:
            await closing
            raise


def item_detail(store, item_id, *, kind=None, local_id=None, view_revision=None, live_state=None):
    """Hydrate exactly the selected member under one read transaction.

    Moving that member to another item is a conflict, not permission to silently
    show another task's draft. Full drafts are hydrated only here, never in leases.
    """
    live_state = None if live_state is None else copy.deepcopy(tuple(live_state))
    with store._processing_read() as cur:
        state = store._processing_reconcile_status_cursor(cur)
        if state['pending']:
            raise AllError('processing_coverage_pending', 'Membership is being reconciled; refresh All')
        resolved = store._processing_follow(cur, str(item_id))
        if not resolved:
            raise AllError('processing_item_missing', 'Item no longer exists', 404)
        item = store._processing_snapshot_cursor(cur, resolved, live_state=live_state)
        members = item.get('member_ids', [])
        if kind is None:
            target = next((mid for prefix in ('message:', 'task:', 'idea:', 'review:')
                           for mid in members if mid.startswith(prefix)), None)
            if not target:
                raise AllError('processing_item_missing', 'Item has no current members', 404)
            kind, local_id = target.split(':', 1)
        if kind not in {'message', 'task', 'idea', 'review'}:
            raise AllError('processing_query_invalid', 'Unknown detail target', 422)
        try:
            if isinstance(local_id, bool):
                raise ValueError()
            local_id = int(local_id)
        except (TypeError, ValueError):
            raise AllError('processing_query_invalid', 'Invalid detail target', 422) from None
        if f'{kind}:{local_id}' not in members:
            raise AllError('processing_target_moved', 'This item changed; refresh All and select it again')
        view, row = item['view'], None
        if kind == 'message':
            message = next(m for m in view['messages'] if m['MessageId'] == local_id)
            conversation = message.get('ConversationId')
            # Existing thread display compatibility, never an identity merge. Read all stored
            # records for this detail rather than reusing a list's compact preview.
            thread = ([dict(r) for r in cur.execute(
                'SELECT * FROM message WHERE ConversationId=? ORDER BY SentAt,MessageId', (conversation,))]
                if conversation else [message])
            row = message_row(message, item, {conversation: thread} if conversation else {},
                              datetime.now().strftime('%Y-%m-%d %H:%M:%S'), full=True)
            task = next((t for t in view.get('tasks', []) if t['TaskId'] == message.get('TaskId')), None)
            if task:
                tid = message['TaskId']
                checklist = _checklist(task)
                detail = {key: copy.deepcopy(view.get(key, [])) for key in (
                    'messages', 'attachments', 'artifacts', 'routes', 'comments', 'runs')}
                # Projection order is hash-stable, not presentation chronology.
                # ReviewCanvas reverses messages/comments to locate the latest reply/report.
                detail['messages'].sort(key=lambda m: (m.get('SentAt') or '', m['MessageId']))
                for collection, field, descending in (
                        ('comments', 'CommentId', False), ('routes', 'RouteId', False),
                        ('runs', 'RunId', True), ('artifacts', 'ArtifactId', True)):
                    detail[collection].sort(key=lambda r: r[field], reverse=descending)
                detail.update(task={**task, 'ChecklistMd': '\n'.join(
                    f"- [{'x' if i.get('done') else ' '}] {i['text']}" for i in checklist)},
                    ref=f'TQ-{tid:04d}', checklist=checklist,
                    session=next((copy.deepcopy(s) for s in (live_state or ())
                                  if str(s.get('taskId', s.get('task_id'))) == str(tid)), None),
                    session_available=live_state is not None)
                transcript = next((tr for tr in view.get('transcripts', []) if tr['TaskId'] == tid), None)
                detail['transcript'] = ({key: value for key, value in transcript.items() if key != 'TaskId'}
                                        if transcript else None)
            else:
                detail = {'task': None, 'messages': thread, 'comments': [], 'runs': [],
                          'attachments': view.get('attachments', []),
                          'routes': [r for r in view.get('routes', []) if r.get('MessageId') == local_id]}
            # ReviewCanvas's first pending draft is an action target. Bind it to this message,
            # especially when a source filter selects an older member of a shared task.
            detail['reviews'] = sorted((r for r in view.get('reviews', []) if r.get('MessageId') == local_id),
                                       key=lambda r: r['ReviewId'], reverse=True)
        else:
            collection, id_field = {'task': ('tasks', 'TaskId'), 'idea': ('ideas', 'IdeaId'),
                                    'review': ('reviews', 'ReviewId')}[kind]
            entity = next(r for r in view[collection] if r[id_field] == local_id)
            title = entity.get('Title') or entity.get('Subject') or (f'Review {local_id}' if kind == 'review' else 'Idea')
            body = entity.get('Summary') or entity.get('Text') or entity.get('Reason') or ''
            if kind == 'review':
                review_text = entity.get('FinalText') if entity.get('FinalText') is not None else entity.get('DraftText')
                if review_text:
                    body += ('\n\n' if body else '') + review_text
            links = []
            if kind == 'task':
                links.append({'kind': 'task', 'id': local_id, 'label': f'Open TQ-{local_id:04d}'})
            for link_kind, field in (('task', 'TaskId'), ('message', 'MessageId')):
                if kind != link_kind and entity.get(field):
                    links.append({'kind': link_kind, 'id': entity[field], 'label': f'Open {link_kind}'})
            detail = {'title': title, 'body': body, 'status': entity.get('Status') or '',
                      'checklist': _checklist(entity) if kind == 'task' else [],
                      'history': [{'at': c.get('CreatedAt'), 'actor': c.get('Author') or c.get('Actor') or '',
                                   'text': c.get('Body') or c.get('Text') or ''}
                                  for c in view.get('comments', [])], 'links': links}
        result = {'item_id': resolved, 'context_revision': item['context_revision'],
                  'view_revision': item['view_revision'], 'requested_view_revision': view_revision,
                  'view_changed': view_revision is not None and view_revision != item['view_revision'],
                  'open_target': {'kind': kind, 'id': local_id}, 'row': row, 'detail': detail}
        result['detail_revision'] = _digest(result)
        return result


def _checklist(task):
    try:
        items = json.loads(task.get('Checklist') or '[]')
    except (TypeError, ValueError):
        return []
    return [i for i in items if isinstance(i, dict) and i.get('text')] if isinstance(items, list) else []

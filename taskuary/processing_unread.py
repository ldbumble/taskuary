"""The Unread presentation of the same canonical roots used by All.

The funnel remains a card/navigation adapter. It no longer supplies membership,
read policy, history windows, or an independent size limit after activation.
"""
import copy
import json
from datetime import datetime

from . import processing_all


def query_for(store, only=None, *, history=True):
    try:
        days = int(store.get_settings().get('feed_days') or 14)
    except (TypeError, ValueError):
        days = 14
    filters = {}
    if only and only.startswith('view:'):
        try:
            filters = json.loads(only[5:])
            if not isinstance(filters, dict) or set(filters) - {'channel', 'source'}:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('Invalid shared inventory filter') from None
    return processing_all.normalize_query(filters.get('channel'), filters.get('source'), days if history else 36500)


def card_for(store, item, compact, live_state, now):
    from . import funnel
    from .processing_reads import state

    view = item['view']
    read = state(item, now)
    row = copy.deepcopy(compact['row'])
    tasks = view.get('tasks') or []
    task = next((t for t in tasks if t['TaskId'] == row.get('TaskId')), tasks[0] if tasks else {})
    tid = task.get('TaskId')
    allowed = set(compact.get('display_message_ids', []))
    pending = [r for r in view.get('reviews', []) if r.get('Status') == 'pending'
               and (r.get('MessageId') in allowed or (not row.get('MessageId') and not r.get('MessageId')))]
    review = max(pending, key=lambda r: r['ReviewId']) if pending else None
    workers = [w for w in live_state if w.get('taskId') == tid] if tid else []
    worker = workers[-1] if workers else None
    active = task.get('Status') not in ('done', 'dropped')
    persisted_working = active and any(r.get('TaskId') == tid and r.get('Status') == 'running'
                                      for r in view.get('runs', []))
    if row.get('MessageId'):
        if review:
            exact = next(m for m in view['messages'] if m['MessageId'] == review['MessageId'])
            row = processing_all.message_row(exact, item, processing_all._thread_index([item]), now.strftime('%Y-%m-%d %H:%M:%S'))
            row.update(ReviewId=review['ReviewId'], ReviewStatus='pending', ReviewKind=review.get('Kind'),
                       HasDraft=bool(review.get('DraftText')))
        cards = funnel.from_feed(store, [row], canonical=True)
        card = cards[0]
    else:
        target = compact['open_target']
        kind = target['kind']
        base = dict(tid=tid, when=compact['activity_at'], priority=task.get('Priority'),
                    channel=compact['channel'], category=compact['category'], who=compact['actor'],
                    preview=compact['preview'])
        if kind == 'idea':
            idea = next(i for i in view['ideas'] if i['IdeaId'] == target['id'])
            try: action = json.loads(idea.get('ActionJson') or '{}')
            except (ValueError, TypeError): action = {}
            triage = action.get('triage') or {}
            lane = 'asked' if triage.get('intent') in ('task', 'reply_only') else 'report' if action.get('section') == 'systems' else 'fyi'
            base.update(idea=idea['IdeaId'], idea_kind=idea.get('Kind'), action=action,
                        priority=triage.get('priority'), tid=action.get('tid') or tid,
                        mid=action.get('mid'), settling=bool(triage.get('pending')),
                        urgent_request=lane == 'asked' and funnel.priority_rank(triage.get('priority')) == 0)
            card = funnel._item('', 'idea', lane, compact['title'], **base)
        else:
            card = funnel._item('', 'todo' if kind == 'task' else 'action',
                                'asked' if kind == 'task' and active else 'fyi', compact['title'], **base)
        if review:
            card.update(kind='action' if review.get('Kind') == 'action' else 'review', lane='approve',
                        rid=review['ReviewId'], mid=review.get('MessageId'), draft=bool(review.get('DraftText')),
                        why='A proposed action is waiting for your approval' if review.get('Kind') == 'action' else 'A reply is waiting for your approval')
    if worker and active:
        agent_cards = funnel.from_agents(store, live_state=[worker], now=now)
        if agent_cards:
            card.update(agent_cards[0])
        elif not review:
            card.update(kind='agent', lane='working', working=worker.get('agent') or worker.get('label') or 'agent',
                        agent=worker.get('agent') or worker.get('label') or 'agent', sid=worker.get('sid'),
                        mode=worker.get('mode') or 'terminal', tail=worker.get('tail') or [],
                        why='An agent is working on this; nothing needs your input yet')
    elif (row.get('Working') or persisted_working) and active and not review:
        who = row.get('Working') or 'agent'
        card.update(kind='agent', lane='working', working=who, agent=who)
    # Worker attention is not a read operation. An active worker remains visible.
    unread = bool((read['unread'] and not read.get('deferred')) or (active and (worker or row.get('Working') or persisted_working)))
    card.update(key='processing:' + item['item_id'], processing_id=item['item_id'],
                member_ids=list(item['member_ids']), context_revision=item['context_revision'],
                view_revision=item['view_revision'], aliases=[a['Value'] for a in item.get('aliases', [])
                    if a.get('Namespace') == 'legacy_funnel'] + ['processing:' + root['ItemId'] for root in item.get('item_history', [])],
                unread=unread, deferred=bool(read.get('deferred')), defer_until=read.get('defer_until'),
                more=max(0, compact['counts'].get('messages', 0) - 1),
                source=row.get('SourceName') or compact['source'], status=row.get('MsgStatus') or compact['status'], order_band=funnel._band(card))
    card.pop('surfaced', None)
    card.pop('surfaced_at', None)
    card['actionable'] = bool(unread and not card['deferred'] and not card.get('settling')
                              and card['lane'] != 'working' and not funnel._not_yet(card))
    return card


def build(store, *, now=None, live_state=None, include_read=False, only=None):
    from . import funnel, terminal
    now = now or datetime.now()
    live_state = terminal.live_sessions(tail=6) if live_state is None else live_state
    snapshot = store.processing_inventory_snapshot(fixed_now=now.isoformat(), live_state=live_state)
    rows, coverage, counts = processing_all.compact_inventory(snapshot, query_for(store, only, history=not include_read), include_excluded=include_read)
    by_id = {item['item_id']: item for item in snapshot['items']}
    cards = [card_for(store, by_id[row['item_id']], row, live_state, now) for row in rows]
    cards = [card for card in cards if include_read or card['unread']]
    # Calendar keeps its established adapter; source filtering applies to it too.
    query = query_for(store, only)
    if processing_all._matches('calendar', '', query):
        calendar_states = store.processing_calendar_states()
        for card in funnel.from_calendar(store, now):
            receipt = calendar_states.get(card['key'], {})
            until = processing_all._stamp(receipt.get('until'))
            deferred = receipt.get('status') in ('later', 'skip') and (until is None or until > now)
            if not include_read and (receipt.get('read') or deferred):
                continue
            card.update(unread=True, deferred=False, actionable=not funnel._not_yet(card), order_band=funnel._band(card))
            card.update(unread=not receipt.get('read') and not deferred, deferred=deferred,
                        actionable=not receipt.get('read') and not deferred and not funnel._not_yet(card))
            cards.append(card)
    cards = funnel._order(cards)
    return {'rev': snapshot['snapshot_revision'], 'items': cards, 'hidden': 0, 'muted': 0,
            'rules': [], 'canonical': True, 'coverage': coverage,
            'counts': {'all': counts['total'], 'unread': sum(c['unread'] for c in cards),
                       'actionable': sum(c['actionable'] for c in cards)},
            'lanes': [{'lane': lane, 'word': funnel.LANE_WORDS[lane][0], 'role': funnel.LANE_WORDS[lane][1],
                       'n': sum(c['lane'] == lane for c in cards)} for lane in funnel.LANES]}

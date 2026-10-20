"""WHAT THIS INSTALL CAN DO, answered by one function - read by every check that decides what the owner is OFFERED: the chips,
the Advisor's verbs, the assistant's coding lines, setup, and the page (GET /api/capabilities, website/src/capabilities.js).
Each of these was asked its own way in its own file, and they disagreed: a Teams draft offered Send that could never
leave, coding was offered where no coding tool runs (2026-10-18). Nothing is cached - a connection made a second ago counts."""
from loguru import logger


def _safe(f, default=False):
    # one failing probe (a card with bad JSON, a CLI that will not resolve) answers "no" for that one, never takes the rest down
    try: return f()
    except Exception as e:
        logger.debug(f'capabilities: {getattr(f, "__name__", "probe")} failed - {e}'); return default


def can_code(store) -> bool:
    """A coding tool that starts on this computer (agents.coding_ready) - read off the module so a test's patch is honoured."""
    from . import agents
    return bool(store is not None and _safe(lambda: agents.coding_ready(store)))


def ai_brain(store) -> dict:
    """The brain triage would run, or a backup that answers (setup._ai) - its `ready` IS "an AI is connected"; setup reads the
    rest (its name, why not) off the same dict."""
    from . import setup
    return (_safe(lambda: setup._ai(store), None) if store is not None else None) or {'ready': False}
def has_ai(store) -> bool:
    # the demo's script answers every ask (llm.build_llm) - with no AI "connected" the page drew Connect an AI over advice it had
    from . import demo
    return demo.enabled() or bool(ai_brain(store).get('ready'))


def mail_cards(store) -> list:
    """The mailboxes connected and polled (setup._inbound) - names, for the screens that list them."""
    from . import setup
    return (_safe(lambda: setup._inbound(store), []) if store is not None else []) or []
def has_mail(store) -> bool: return bool(mail_cards(store))


def can_send(store, channel) -> bool:
    """Can a reply on this channel leave from here (outbound.can_reply): email yes, Teams - read, never posted into - no."""
    from . import outbound
    return bool(store is not None and channel and _safe(lambda: outbound.can_reply(store, channel)))


def send_refusal(store, channel) -> str:
    """'' when a message can leave on this channel, else the one sentence why (outbound.send_block names the place that lifts
    it) - three doors each said "turn its replies on in Connections", true of none of Teams, a switched-off reply or a mailbox."""
    if can_send(store, channel): return ''
    from . import outbound, words
    why = _safe(lambda: outbound.send_block(store, channel), '') or f"its card under {words.name('connections')} cannot deliver yet"
    return f'{channel or "that channel"} cannot send from here - {why}'


def draft_channel(store, rid) -> str:
    """The channel a draft would leave on: its envelope's for a message the owner started, else the message it answers.
    '' when it is not a reply at all (an agent's proposal, an invoice) or nothing says - nothing to refuse then."""
    import json
    r = (store.get_review(int(rid)) if store is not None and rid else None) or {}
    if not r or r.get('Kind') == 'action': return ''
    try: env = json.loads(r.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): env = {}
    if not isinstance(env, dict) or env.get('kind') in ('zoho_invoice', 'calendar'): return ''      # outbound.OWN_ROAD
    m = (store.get_message(r['MessageId']) if r.get('MessageId') else None) or {}
    return str(m.get('Channel') or env.get('channel') or '')


def can_send_draft(store, rid) -> bool:
    """False only where the draft's channel is known and cannot deliver - the Send that would only ever fail."""
    ch = draft_channel(store, rid)
    return not ch or can_send(store, ch)


def channels() -> tuple:
    """Every channel a reply could be asked of: the ones with a sender and the ones read here but answered there."""
    from . import outbound
    return tuple(dict.fromkeys((*outbound.SENDABLE, *outbound.NO_SENDER)))


def capabilities(store) -> dict:
    """{"coding", "ai", "mail", "send": {channel: bool}} - the one answer, for the server and the page alike."""
    return {'coding': can_code(store), 'ai': has_ai(store), 'mail': has_mail(store),
            'send': {ch: can_send(store, ch) for ch in channels()}}

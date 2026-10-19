"""WHO DOES A TASK, once (kinds.json): the four kinds, which an agent works, which triage may name, and each one's words - read by
the server here and by the page (website/src/kinds.js). `('coding', 'general', 'task')` was typed in routing, operations, triage,
funnel, the server and the assistant, and the picker's labels twice in the page with different hints (the cleanup round, 2026-10-18)."""
import json
from pathlib import Path

_J = json.loads(Path(__file__).with_name('kinds.json').read_text(encoding='utf-8'))
KIND = {k['key']: k for k in _J['kinds']}
KINDS = tuple(KIND)                                          # task, general, coding, reply - the picker's order
AGENT = tuple(k for k, v in KIND.items() if v['agent'])      # general, coding: an agent works it, it is on the Board
TRIAGE = tuple(k for k, v in KIND.items() if v['triage'])    # what triage (or the owner's "make it a task") may name


def label(kind) -> str: return (KIND.get(str(kind or '')) or {}).get('label') or str(kind or '')


def worker(kind) -> str:
    """Who works an agent kind, in a sentence: 'the coding agent' for coding, 'the assistant' for any other."""
    return KIND['coding' if str(kind or '') == 'coding' else 'general']['worker']


def triage_kind(kind, default: str = 'task') -> str:
    """A kind triage may name, as given; anything else is `default` - the owner's list, where nothing starts on a guess."""
    k = str(kind or '').lower()
    return k if k in TRIAGE else default

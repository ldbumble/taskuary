"""A HABIT THE ADVISOR IS SURE OF IS ADOPTED; ONE IT IS NOT SURE OF IS ASKED, ONCE (the owner, 2026-11-01: "when the Advisor is SURE,
it adopts the habit without asking; it asks (Adopt / No, once, never repeated after No) only for really useful ones it is unsure about").

The reflection proposes a rule it has inferred under "Proposed rules - your call" and it waited there for a click - the audit found eleven,
one resting on 31 of the owner's own acts, that would have spared most of the side-product and personal misses. After each reflection:

  sure     its strength is SURE_S or more, resting on SURE_EV or more distinct acts of the owner's (episodes.is_act: never a press, never
           what a sender wrote) -> adopted, and said once as an Advisor card whose No takes it back (memoryedit Wrong)
  useful   strength USEFUL_S or more, short of sure -> an Advisor card asks Adopt / No; No leaves it where it was and never asks again
  the rest wait, as before

Counted, never thought: the same evidence the books already keep. A rule never reaches triage from a press: _books drops press-only lines."""
import re
from datetime import datetime
from loguru import logger

SURE_S, SURE_EV, USEFUL_S = 10, 6, 5


def _slug(key: str) -> str: return re.sub(r'[^a-z0-9]+', '-', str(key).lower()).strip('-')[:60]


def tick(store) -> dict:
    """Adopt the sure ones and card the useful ones. {adopted: [keys], asked: [keys]}. Never raises."""
    from . import learn, learnedgraph as lg
    from .episodes import is_act
    out = {'adopted': [], 'asked': []}
    try:
        for l in lg.lines(store.get_doc(learn.DOC) or ''):
            if l['status'] != 'proposed': continue
            acts = {e for e in l['ev'] if is_act(e)}
            if l['score'] >= SURE_S and len(acts) >= SURE_EV and len(acts) == len(set(l['ev'])):
                try: learn.adopt(store, l['key'], 'advisor-sure')
                except ValueError: continue
                card(store, l['key'], l['text'], adopted=True); out['adopted'].append(l['key'])
            elif l['score'] >= USEFUL_S and acts and card(store, l['key'], l['text'], adopted=False): out['asked'].append(l['key'])
    except Exception as e: logger.warning(f'habits not weighed: {e}')
    return out


def card(store, key: str, text: str, adopted: bool) -> dict | None:
    """The Advisor's card for one habit - said once: a No on it (dismissed) is never asked again, and an answered one is not re-raised."""
    k = f'idea:habit-{_slug(key)}'
    old = store._one('SELECT Status FROM idea WHERE Key=?', (k,))
    if old and (old['Status'] in ('dismissed', 'done') or not adopted): return None
    say = f'Adopted a habit of yours: "{text}"' if adopted else f'Is this a habit of yours: "{text}"?'
    return store.upsert_idea({'key': k, 'kind': 'habit', 'text': say, 'sig': f"{key}:{'adopted' if adopted else 'ask'}",
                              'action': {'type': 'habit', 'line': key, 'adopted': adopted, 'whose': 'the owner',
                                         'suggest': 'Keep it' if adopted else 'Adopt it'}}, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


def answer(store, idea: dict, yes: bool, actor: str = 'owner') -> dict:
    """Adopt / Keep (yes) or No on a habit card. Adopt moves a proposed line live; No on one the Advisor adopted takes it back for good
    (Wrong); No on one it asked about leaves it proposed - and the card, dismissed, never comes back."""
    import json
    from . import learn, memoryedit
    try: a = json.loads(idea.get('ActionJson') or '{}') or {}
    except ValueError: a = {}
    key = a.get('line')
    if not key: return {'line': None}
    if yes and not a.get('adopted'):
        try: learn.adopt(store, key, actor)
        except ValueError: pass
        return {'line': key, 'adopted': True}
    if not yes and a.get('adopted'):
        try: memoryedit.mark(store, key, 'wrong')
        except ValueError as e: logger.info(f'habit {key} not taken back: {e}')
        return {'line': key, 'adopted': False}
    return {'line': key, 'adopted': bool(a.get('adopted'))}

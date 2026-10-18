"""THE ONE LIST OF BUTTONS, read (buttons.json). Every label the server puts on a chip, a proposal, a card's question, the
Advisor's line or the assistant's tools comes from here - never retyped (the owner, 2026-10-17: "if it's in one code place it's
easy to update it later"). Verb ids are wiring and stay; labels are words and live in the json."""
import json
from pathlib import Path

_J = json.loads((Path(__file__).with_name('buttons.json')).read_text(encoding='utf-8'))
VERBS = {k: v for k, v in _J['verbs'].items() if not k.startswith('_')}
REMOVED = {k: v for k, v in _J['removed'].items() if not k.startswith('_')}
CHOICES = {k: tuple(tuple(p) for p in v) for k, v in _J['choices'].items() if not k.startswith('_')}


def canon(verb):
    """A removed verb lands where buttons.json sends it (prep -> None: it is gone); any other word is itself."""
    return REMOVED[verb] if verb in REMOVED else verb


def label(verb: str, state: str = None) -> str:
    """The button's one name - or the name it shows in `state` ('action' on approve, 'none' on redraft). '' for no such button."""
    v = VERBS.get(canon(verb) or '')
    return ((v.get('states') or {}).get(state) or v['label']) if v else ''


def hint(verb: str, state: str = None) -> str:
    v = VERBS.get(canon(verb) or '')
    return ((v.get('state_hints') or {}).get(state) or v.get('hint') or '') if v else ''


def choices(group: str) -> tuple:
    """The card's own question after a button - ((verb, answer), ...); answers, not buttons."""
    return CHOICES.get(group, ())


def labels() -> set:
    """Every word a button may show: each label and each state's label."""
    return {v['label'] for v in VERBS.values()} | {s for v in VERBS.values() for s in (v.get('states') or {}).values()}


def chip(verb: str, state: str = None) -> dict:
    """A chip as the page draws it: the verb, its name, and what it does on hover."""
    h = hint(verb, state)
    return {'verb': verb, 'label': label(verb, state), **({'hint': h} if h else {})}

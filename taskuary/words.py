"""THE PLACES A SENTENCE SENDS THE OWNER, AND THE WORDS THEY NEVER SEE (words.json) - read here by the server and by the page
(website/src/words.js). A sentence names a place by words.place(id), never a typed "Settings → ..." path: one moved page was
a dozen stale sentences across concierge, setup and ingest, each spelled its own way (2026-10-18)."""
import json, re
from pathlib import Path

_J = json.loads(Path(__file__).with_name('words.json').read_text(encoding='utf-8'))
PLACES = {k: v for k, v in _J['places'].items() if not k.startswith('_')}
JARGON = tuple(_J['jargon'])
# a tool that runs on the owner's own machine, said the one way the server and the page both say it ("claude (your CLI)" was
# code-speak on the agent card - the dead-end walk's WORDS, 2026-10-18)
LOCAL = _J['local']
# what the Advisor's strip says when it has no line, by advisor.status's reason - one sentence and the one move it lights
ADVICE_NONE = {k: v for k, v in _J['advice_none'].items() if not k.startswith('_')}
# what the daily check says about an item that fell through, by why (sweep.py)
LOOSE = {k: v for k, v in _J['loose_ends'].items() if not k.startswith('_')}
def local(tool: str) -> str: return f'{tool} ({LOCAL})'


def place(pid: str) -> tuple:
    """(name, href) of a place - href '' where the place has no link of its own. An unknown id is a bug, so it raises."""
    p = PLACES[pid]; return p['name'], p['href']
def name(pid: str) -> str: return PLACES[pid]['name']
def href(pid: str) -> str: return PLACES[pid]['href']
def link(pid: str) -> str:
    """The place as a chat link the canvas opens ([Connections → AI](#connections=...)), or its bare name with no link."""
    n, h = place(pid); return f'[{n}]({h})' if h else n
def card(title: str) -> str:
    """One connection's own card, by its title - "Connections → Exa": the path's first step still comes from the json."""
    return f"{name('connections')} → {title}"


# an entry ending in '-' is a model id's stem: "claude-" stands for claude-sonnet-4-5 and every id like it
_JRE = re.compile(r'(?<![\w-])(?:' + '|'.join(re.escape(w) + (r'[\w.-]+' if w.endswith('-') else '')
                                              for w in sorted(JARGON, key=len, reverse=True)) + r')(?![\w])', re.I)
# the short all-caps ones only as written: "pr" inside a sentence is a word, "PR" is the jargon
_CAPS = {w for w in JARGON if w.isupper()}
def jargon_in(text: str) -> list:
    """The jargon words a line for the owner says, as found - [] for a plain line."""
    return [m.group(0) for m in _JRE.finditer(str(text or '')) if m.group(0).upper() not in _CAPS or m.group(0).isupper()]

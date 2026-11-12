"""THE PLACES A SENTENCE SENDS THE OWNER, AND THE WORDS THEY NEVER SEE (words.json) - read here by the server and by the page
(website/src/words.js). A sentence names a place by words.place(id), never a typed "Settings → ..." path: one moved page was
a dozen stale sentences across concierge, setup and ingest, each spelled its own way (2026-10-18)."""
import json, re
from pathlib import Path

_J = json.loads(Path(__file__).with_name('words.json').read_text(encoding='utf-8'))
PLACES = {k: v for k, v in _J['places'].items() if not k.startswith('_')}
JARGON = tuple(_J['jargon'])
# one name per thing the owner is shown, and the surfaces that no longer exist - matched as written ("timeline" is a word)
NOUNS = {k: v for k, v in _J['nouns'].items() if not k.startswith('_')}
GONE = tuple(_J['gone']['words'])
def noun(nid: str) -> str: return NOUNS[nid]
# what the Advisor's strip says when it lights nothing, by advisor.status's reason - only no AI is said (the owner, 2026-10-23)
ADVICE_NONE = {k: v for k, v in _J['advice_none'].items() if not k.startswith('_')}
# where an item stands, as facts: each state's meaning and its fact sentence, for the Advisor's model (rulebook.py)
ADVICE_RULE = {k: v for k, v in _J['advice_rule'].items() if not k.startswith('_')}
# what the daily check says about an item that fell through, by why (sweep.py)
LOOSE = {k: v for k, v in _J['loose_ends'].items() if not k.startswith('_')}


def place(pid: str) -> tuple:
    """(name, href) of a place - href '' where the place has no link of its own. An unknown id is a bug, so it raises."""
    p = PLACES[pid]; return p['name'], p['href']
def name(pid: str) -> str: return PLACES[pid]['name']
def href(pid: str) -> str: return PLACES[pid]['href']
def link(pid: str) -> str:
    """The place as a chat link the canvas opens ([Connections → AI](#connections=...)), or its bare name with no link."""
    n, h = place(pid); return f'[{n}]({h})' if h else n
# ONE WAY TO BRING A PAGE UP, for the dock and every task agent (the owner, 2026-11-07): a task agent said "you can connect your books here"
# in prose while the dock linked the real card. Each address is one canvasLinks.js opens in place, and the `show` tool's button takes the
# same ones (viewspec.LINK); #connector=<type> is the form that opens ONE card - #connections=<section> opens a section, its cards closed.
LINK_LINE = ('BRINGING THINGS UP: when the owner should see or set something themselves, link it - a markdown link opens that screen in '
             'the app, in place - never a direction in prose. A task: [TQ-0001](#task=1), with its real id. One connection\'s card, by its '
             'type: [Connect QuickBooks](#connector=quickbooks) (intacct, outlook, gmail, linkedin, sharepoint, github, jira ...; add &step=1 '
             'to light its first step); all connections: #connections. A settings page: #settings=<page> (#settings=policies, '
             '#settings=updates); a report: #report=<id>, a new one #report=new, the list #report=reports. One link and a few words '
             'beside it - what to do there, never what the screen shows.')


def card(title: str) -> str:
    """One connection's own card, by its title - "Connections → Exa": the path's first step still comes from the json."""
    return f"{name('connections')} → {title}"


# an entry ending in '-' is a model id's stem: "claude-" stands for claude-sonnet-4-5 and every id like it
_JRE = re.compile(r'(?<![\w-])(?:' + '|'.join(re.escape(w) + (r'[\w.-]+' if w.endswith('-') else '')
                                              for w in sorted(JARGON, key=len, reverse=True)) + r')(?![\w])', re.I)
# the short all-caps ones only as written: "pr" inside a sentence is a word, "PR" is the jargon
_CAPS = {w for w in JARGON if w.isupper()}
_GRE = re.compile(r'\b(?:' + '|'.join(map(re.escape, GONE)) + r')\b')
def jargon_in(text: str) -> list:
    """The jargon words a line for the owner says, as found - [] for a plain line. A surface that is gone counts too."""
    return [m.group(0) for m in _JRE.finditer(str(text or '')) if m.group(0).upper() not in _CAPS or m.group(0).isupper()] \
        + _GRE.findall(str(text or ''))

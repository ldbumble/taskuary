"""THE RAIL'S RULES, read from lanes.json - the same file the page reads (website/src/lanes.js). Which section a row is in, what
counts as on you, what each kind of row is called: each was a hand-kept tuple in three to eight places (funnel, welcome,
processing_unread, remote_assistant, concierge, assistant, and the page's copies of each) and they had drifted - the opener
counted waiting-on-them as on you and the greeting did not, the header's "on you" left out the lane worded "on you". It
imports nothing of the package but processing_order (which imports nothing): funnel, welcome and processing_unread all read it,
and it must never pull one into another."""
import json
from pathlib import Path

from .processing_order import attention_band

VOCAB = json.loads(Path(__file__).with_name('lanes.json').read_text(encoding='utf-8'))
LANE = {l['key']: l for l in VOCAB['lanes']}
SECTIONS = tuple(VOCAB['sections'])
SECTION = {s['key']: s for s in SECTIONS}
LEVEL_ORDER = tuple(s['key'] for s in SECTIONS)
SECTION_WORDS = {s['key']: s['word'] for s in SECTIONS}
LEVEL_OF_BAND = {s['band']: s['key'] for s in SECTIONS if s['band']}
BAND_OF = {k: b for b, k in LEVEL_OF_BAND.items()}
ALERT_MIN = SECTION['urgent']['minutes']
ON_YOU_SECTIONS = tuple(s['key'] for s in SECTIONS if s.get('on_you'))
TO_READ_SECTIONS = tuple(s['key'] for s in SECTIONS if s.get('to_read'))
# blocked on the owner's answer or yes: what leads the walk, and what a new walk raises again
WAITS = tuple(k for k, l in LANE.items() if l.get('waits'))
# the owner's move on the rail - Urgent or On you by its lane - which Next leaves in For later rather than dropping
OWNER_LANES = tuple(k for k, l in LANE.items() if l.get('section') in ('urgent', 'task'))
KIND = VOCAB['item_kinds']
MAIL_KINDS = tuple(k for k, v in KIND.items() if v.get('mail'))
AGENT_KINDS = tuple(k for k, v in KIND.items() if v.get('agent'))
IDEA = VOCAB['idea_kinds']
# EVERY STATE'S WORD, once - a lane's, a kind's that overrides it, or a closed row's (lanes.json `states`): "agent finished" or "ready
# to send" is read here, never retyped where a sentence needs it (the cleanup round, 2026-10-18)
WORD = {r['key']: r['word'] for g in ('lanes', 'kinds', 'states') for r in VOCAB[g]}
def word(key: str) -> str: return WORD.get(key, '')


def lane_section(lane) -> str: return (LANE.get(lane) or {}).get('section') or 'task'   # a lane this build does not know is work, never buried


def not_yet(item: dict) -> bool:
    """A meeting on the timeline with nothing to say about it YET: it enters two hours out, and is Urgent only inside ALERT_MIN."""
    if item.get('kind') != 'meeting': return False
    if 'calendar_ready' in item: return not item['calendar_ready']
    return item.get('mins') is not None and item['mins'] > ALERT_MIN


def band_of(item: dict) -> int:
    """The attention band (processing_order.attention_band) of a row, from its lane's entry. The server stamps it as order_band;
    a row that came without one (an old persisted card) gets the same answer here, not a second table's."""
    lane, kind = item.get('lane'), item.get('kind')
    if kind == 'meeting': return attention_band(urgent=not not_yet(item), actionable=True)
    l, sec = LANE.get(lane) or {}, lane_section(lane)
    # a task an agent FINISHED is still a task - On you until Next reads it, never a report (the owner, 2026-09-24); an unjudged
    # row the retry gave up on is nobody's to judge now, so it is the owner's
    return attention_band(urgent=sec == 'urgent' or bool(l.get('urgent_request') and item.get('urgent_request')),
                          owner_wait=bool(l.get('waits')), working=sec == 'agents',
                          actionable=sec == 'task' or kind == 'agentdone' or (lane == 'unjudged' and bool(item.get('held'))),
                          result=sec == 'reports')


def level_of(item: dict) -> str:
    """The rail section a row is drawn in - website/src/lanes.js levelOf is the same rule, and tests/fixtures/rail_levels.json
    holds both to the same answers."""
    band = item.get('order_band')
    if not (isinstance(band, int) and 1 <= band <= 5): band = band_of(item)
    # A GOAL is one row and never gone: Goals while it has news you have not walked past, For later once you have (spec
    # 2026-10-12). `surfaced` is the Passed mark: a read open task stays unread on purpose, so unread cannot be the signal.
    if str(item.get('kind') or '').startswith('goal'): return 'goals' if item.get('news') and not item.get('surfaced') else 'later'
    # FOR LATER IS WHAT YOU PUT THERE - Next or Remind me - never a card merely shown: clicking another row on the rail moved the
    # task on the table under For later for three hours (the owner, 2026-10-08: "it moved 1003 automatically to later?")
    if band == 2 and (item.get('put_down') or item.get('deferred')): return 'later'
    if band == 4 and item.get('kind') == 'idea': return 'ideas'
    return LEVEL_OF_BAND.get(band, 'fyi')


def waits_on_you(item: dict) -> bool: return bool((LANE.get(item.get('lane')) or {}).get('waits'))


def on_you(item: dict, level: str = None) -> bool:
    """ON YOU, the one answer the opener's headline, the greeting and the header all give: drawn under Urgent or On you, and in a
    lane that is the owner's move - waiting on THEM sits under On you as the owner's task, but it is on somebody else."""
    if item.get('settling'): return False
    return (level or level_of(item)) in ON_YOU_SECTIONS and (LANE.get(item.get('lane')) or {}).get('on_you', True)


def to_read(item: dict, level: str = None) -> bool:
    return not item.get('settling') and (level or level_of(item)) in TO_READ_SECTIONS


def is_mail(item: dict) -> bool: return item.get('kind') in MAIL_KINDS


def kind_says(kind, n: int) -> str:
    """'2 drafts to approve' - a kind counted in the owner's words, never its internal name."""
    k = KIND.get(str(kind or '')) or KIND['other']
    return f"{n} {k['one' if n == 1 else 'many']}"


def idea_word(kind) -> str: return (IDEA.get(str(kind or '')) or IDEA['idea'])['word']
def idea_section(kind) -> str: return (IDEA.get(str(kind or '')) or IDEA['idea'])['section']
def idea_counted(kind) -> str: return (IDEA.get(str(kind or '')) or IDEA['idea'])['counted']

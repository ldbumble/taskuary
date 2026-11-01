"""HOW THE OWNER WRITES, PER WORKSTREAM (the owner, 2026-11-01: "it might get complicated" - "try it"; the design's S9). A team chat for
a side product and a vendor email for the day job read differently. STYLE.md stays the one shared style; under it, a marked section per
workstream (`<!-- style:<slug>:start -->` ... `:end -->`) says what is different there, written from the owner's own sent words in that
workstream. A draft reads the shared style and its workstream's lines; a workstream with no lines falls back to the shared style alone.

An OPTION, easily reverted: the setting `style_by_workstream` '0' turns it off at once (the sections stay, unread), and every draft that
read a workstream's lines leaves an audit row (`style_ws`) so tools/style_by_workstream.py can say whether the owner edits those drafts
less than the others - the measure that decides whether it stays."""
import re
from loguru import logger

KEY = 'style_by_workstream'
MIN_SENT = 10              # the owner's own sent messages in a workstream before its style is written
SYSTEM = ("You describe how one person writes in ONE of their workstreams, from their own sent messages there, against how they write "
          "in general (given). Write 2-5 markdown bullets, second person, ONLY what is different here: greeting, length, tone, sign-off, "
          "language. Never quote a message; never name a customer, patient or resident. If nothing is different, answer exactly: same.")


def start(slug): return f'<!-- style:{slug}:start -->'
def end(slug): return f'<!-- style:{slug}:end -->'
_SECTION = re.compile(r'<!-- style:([a-z0-9-]+):start -->(.*?)<!-- style:\1:end -->', re.S)


def on(store) -> bool: return str(store.get_setting(KEY) or '1') != '0'


def shared(doc: str) -> str:
    """STYLE.md with every workstream's section taken out - the style every draft reads."""
    return _SECTION.sub('', doc or '')


def lines(store, slug: str) -> str:
    """The workstream's own style lines ('' when it has none, or the option is off)."""
    if not slug or not on(store): return ''
    doc = store.doc('style') or ''
    m = next((m for m in _SECTION.finditer(doc) if m.group(1) == slug), None)
    return re.sub(r'<!--.*?-->', '', m.group(2), flags=re.S).strip() if m else ''


def block(store, slug: str) -> str:
    """What a draft adds after the shared style, '' when nothing - the fallback."""
    t = lines(store, slug)
    if not t: return ''
    from . import workstreams as W
    w = W.get(store, slug)
    return f"\n\nIn {w['name'] if w else slug} you write differently:\n{t}"


def write(store, llm, slug: str) -> str:
    """The workstream's style section, written from the owner's own sent messages in it. Returns what was written ('' when too little
    mail, the same as the shared style, or no brain)."""
    from . import workstreams as W
    from .histgen import style_sample
    w = W.get(store, slug)
    if not w or w['personal'] or llm is None: return ''
    sent = store._rows("SELECT BodyText FROM message WHERE Workstream=? AND (Direction='out' OR Status='context') AND IFNULL(BodyText,'')<>'' "
                       "ORDER BY SentAt DESC LIMIT 30", (slug,))
    if len(sent) < MIN_SENT: return ''
    from .responder import style_doc
    try:
        t = str(llm(SYSTEM, f"HOW THEY WRITE IN GENERAL:\n{style_doc(store)[:2000]}\n\nTHEIR SENT MESSAGES IN {w['name'].upper()}:\n\n"
                            + '\n\n---\n\n'.join(style_sample(r['BodyText'], 500) for r in sent)) or '').strip()
    except Exception as e:
        logger.warning(f'style for {slug} not written: {e}'); return ''
    if not t or t.lower().strip('. ') == 'same' or '<!--' in t or len(t) > 2000: return ''
    doc = store.get_doc('style') or ''
    body = f'{start(slug)}\n### In {w["name"]}\n{t}\n{end(slug)}'
    m = next((m for m in _SECTION.finditer(doc) if m.group(1) == slug), None)
    doc = doc[:m.start()] + body + doc[m.end():] if m else doc.rstrip() + '\n\n' + body + '\n'
    store.save_doc('style', doc, 'stylews')
    return t


def used(store, task_id, slug: str):
    """The receipt the measure reads: this draft read the workstream's style lines."""
    try: store.audit('task', task_id, 'style_ws', 'drafter', 'agent', {'workstream': slug})
    except Exception: pass

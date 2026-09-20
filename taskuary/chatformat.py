"""A report, or anything else we say, as a CHAT can hold it.

The morning digest reached WhatsApp as two bubbles of seven thousand characters, broken
mid-sentence and both folded behind "Read more" (the owner, 2026-09-19, with a screenshot).
Most of it was the `--- raw data ---` evidence dump - everything the model was GIVEN - which
the desktop has always hidden. The desktop already knows how to show a report: cut at the
marker, group it into sections, list the items (assistantCards.jsx, digestText.js). This is
that, for a chat, plus the one thing a chat needs that a page does not: the text has to be
spelled the way the channel renders it.

WhatsApp formats client-side, so `*one star*` IS bold there and `**two**` arrives as literal
punctuation. Telegram renders nothing at all unless the send sets a parse mode, and neither
sender does, so it gets the words with no marks on them. One markup in, two spellings out.
"""
import re

HARD = 3900              # one message, comfortably inside Telegram's 4096-character limit
RAW = '--- raw data ---'
# A producer says "new bubble here" with this and never thinks about the transport again;
# remote_assistant.send is the only thing that reads it. A control character, so no report can
# contain one by accident.
BREAK = '\x1e'

# The digest's own emoji headings, and the legacy uppercase ones that appear when its AI pass
# failed and the evidence files unsummarised. The desktop maps the same list (digestText.js);
# both sides have to agree or one of them silently stops seeing a section as a section.
LEGACY = ('MEETINGS TODAY', 'THEIR ASKS YOU HAVE NOT ANSWERED', 'MY OPEN LOOPS', 'WAITING ON THE OWNER',
          'WHAT PEOPLE SAID', 'OUT OF OFFICE', 'WHAT ARRIVED', 'WHAT THE OWNER HAS ALREADY DECIDED',
          'OPEN WORK', 'FINISHED THIS WINDOW', 'VERDICTS GIVEN THIS WINDOW', 'THE WINDOW IN NUMBERS')

_CODE = re.compile(r'`+([^`\n]+?)`+')
_HEAD = re.compile(r'^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$')
_RULE = re.compile(r'^\s*\|?[\s:|-]*-{2,}[\s:|-]*\|?\s*$')      # a table's ---|--- rule, or an hr
_ROW = re.compile(r'^\s*\|(.+)\|\s*$')
_LINK = re.compile(r'!?\[([^\]]+)\]\([^)]*\)')
_BOLD = re.compile(r'(\*\*|__)(.+?)\1', re.S)
_ITAL = re.compile(r'(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])')
_UNDER = re.compile(r'(?<![\w_])_(?!\s)([^_\n]+?)(?<!\s)_(?![\w_])')
_FENCE = re.compile(r'^\s*```+[a-z]*\s*$', re.M)


def _is_emoji(ch: str) -> bool:
    o = ord(ch)
    return (0x1F300 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF
            or 0x2300 <= o <= 0x23FF or 0x2B00 <= o <= 0x2BFF)


def strip_raw(body) -> str:
    """Everything the model was GIVEN, cut off where the desktop cuts it.

    A report body is the summary and then, under this marker, the rows it was written from.
    The page hides that behind a toggle; the phone was sending all of it, and on the morning
    digest that was four thousand of its seven thousand characters."""
    text = str(body or '').replace('\r', '')
    i = text.find('\n' + RAW)
    if i < 0 and text.lstrip().startswith(RAW): i = 0     # a run whose whole body IS the marker
    return (text[:i] if i >= 0 else text).strip()


def _heading(line: str):
    """The words of this line if it opens a section, else None."""
    s = line.strip()
    if not s: return None
    m = _HEAD.match(line)
    if m: return m.group(1).strip()
    if _is_emoji(s[0]): return s.rstrip(':').strip()
    hit = next((h for h in LEGACY if s.startswith(h)), None)
    return hit and s.rstrip(':').strip()


def sections(text) -> list:
    """[(heading, body)] - what the report says, grouped the way the Assistant groups it.

    A report with no headings at all (an error line, a paragraph of prose) is one nameless
    section rather than none: the caller still has something to send."""
    out, title, held = [], '', []
    def close():
        body = '\n'.join(held).strip()
        if body: out.append((title, body))
    for line in str(text or '').replace('\r', '').split('\n'):
        h = _heading(line)
        if h is None: held.append(line.rstrip()); continue
        close(); title, held = h, []
    close()
    return out


def render(text, channel: str) -> str:
    """Markdown as this channel actually draws it. Code spans come out first and go back last,
    so `snake_case_name` is never read as an italic."""
    kept = []
    def hold(m):
        kept.append(m.group(1)); return f'\x00{len(kept) - 1}\x00'
    out = _CODE.sub(hold, str(text or ''))
    out = _FENCE.sub('', out)
    lines = []
    for line in out.split('\n'):
        if _RULE.match(line) and ('|' in line or set(line.strip()) <= set('- ')): continue
        row = _ROW.match(line)
        # a table is unreadable as pipes in a bubble - fifteen repos by six columns of them was
        # the GitHub report - so each row becomes its cells, in order, separated by a middle dot.
        # It is settled HERE and the line goes no further: a rank column makes the header row read
        # '# | Repo | ...', and run past the heading rule below that is a level-one heading, which
        # swallowed the rank column and bolded the rest of the labels.
        if row:
            lines.append(' · '.join(c.strip() for c in row.group(1).split('|') if c.strip()))
            continue
        h = _HEAD.match(line)
        # A heading is MARKED here and spelled at the very end: writing its star now would put a
        # single star into the text, which is exactly what the italic rule reads, and every
        # heading came back out as _italic_ instead of bold.
        if h: line = f'\x01{h.group(1).strip()}\x01'
        lines.append(line)
    out = '\n'.join(lines)
    out = _LINK.sub(r'\1', out)                     # the link's words; a chat linkifies bare urls itself
    if channel == 'whatsapp':
        # ITALIC FIRST. Bold emits a single star, which is precisely what the italic rule matches -
        # the other way round and every *bold* came back out as _italic_.
        out = _ITAL.sub(r'_\1_', out)
        out = _BOLD.sub(r'*\2*', out)               # ** is literal punctuation there; one star is bold
    else:
        out = _BOLD.sub(r'\2', out)
        out = _ITAL.sub(r'\1', out)
        out = _UNDER.sub(r'\1', out)
    out = out.replace('\x01', '*' if channel == 'whatsapp' else '')
    for i, code in enumerate(kept): out = out.replace(f'\x00{i}\x00', code)
    return re.sub(r'\n{3,}', '\n\n', out).strip()


def split(text: str, limit: int = HARD) -> list:
    """One section that will not fit, broken where a reader would break it: a blank line, then a
    line end, and only as a last resort a space. The old splitter took max() of those three
    positions, so the space always won and every break landed mid-sentence."""
    out = []
    while len(text) > limit:
        window = text[:limit]
        cut = window.rfind('\n\n')
        if cut < limit // 3: cut = window.rfind('\n')
        if cut < limit // 3: cut = window.rfind(' ')
        if cut < limit // 3: cut = limit
        out.append(text[:cut].rstrip()); text = text[cut:].lstrip()
    if text.strip(): out.append(text.strip())
    return out


def blocks(body, limit: int = HARD) -> list:
    """A report as the messages a chat should receive: one per section, in order.

    Sections are what make it readable - the owner asked for the whole report, "just split into
    sections so you can read it normally". A section too long for one message breaks on a line
    rather than a word, and keeps its heading so every bubble still says what it is.

    The markup stays as it came: which channel this is bound for is the door's business
    (remote_assistant.send), not the shape of the report."""
    out = []
    for title, text in sections(strip_raw(body)):
        head = f'## {title}' if title else ''
        text = text.strip()
        if not text: continue
        for piece in split(text, max(200, limit - len(head) - 2)):
            out.append(f'{head}\n{piece}'.strip() if head else piece)
    return out

"""A BLANK LEFT IN A DRAFT (the owner, 2026-10-30): a drafted reply can hold a slot like "[REASON]" or "[DATE]" for the owner to
fill, and Send went out with it. Send refuses while one remains - here, so the task page, the phone and the assistant all meet the
same refusal (verdicts.decide is the one door) - and the draft box marks them (website/src/blanks.js, from the same blanks.json).

Only template slots count, never the brackets real mail carries: a gateway's "[External]" tag, a markdown link "[text](url)", a
footnote "[1]", a checkbox "[x]", code ("rows[INDEX]", anything in backticks) and quoted lines ("> ...") all go out as they are."""
import json, re
from pathlib import Path

_J = json.loads(Path(__file__).with_name('blanks.json').read_text(encoding='utf-8'))
NOT_SLOTS, SAID = frozenset(_J['not_slots']), frozenset(_J['said'])
# a bracket not glued to a word before it (an index) and not a link's text or a reference's label after it
BOX = re.compile(r'(?<![\w\]\\])\[([^\[\]\n]{1,60})\](?!\(|\[|:\s*(?:https?://|<))', re.A)
_SHOUT = re.compile(r"[A-Z][A-Z0-9'’&/.,#_ -]*")
_CUE = re.compile(r"(?ai)(?:%s)\b" % '|'.join(re.escape(c) for c in sorted(_J['cues'], key=len, reverse=True)))
_PHRASE = re.compile(r"[A-Za-z][\w'’&/.,# -]{0,39}", re.A)
# code and quoted lines are someone else's words: blanked to spaces so a slot's place in the text stays where it was
_ASIDE = re.compile(r'```[\s\S]*?(?:```|\Z)|`[^`\n]*`|^[ \t]*>[^\n]*', re.M)


def is_slot(inner: str) -> bool:
    s = inner.strip()
    if not s or s.upper() in NOT_SLOTS or SAID & set(re.findall(r'[a-z]+', s.lower())): return False
    if re.fullmatch(r'_{2,}', s): return True
    if _SHOUT.fullmatch(s): return len(re.findall('[A-Z]', s)) >= 2
    return bool(_PHRASE.fullmatch(s) and _CUE.match(s))


def spans(text: str) -> list:
    """(start, end, '[SLOT]') for every blank still in the text, in order."""
    if not text: return []
    seen = _ASIDE.sub(lambda m: re.sub(r'[^\n]', ' ', m.group()), text)
    return [(m.start(), m.end(), text[m.start():m.end()]) for m in BOX.finditer(seen) if is_slot(m.group(1))]


def find(text: str) -> list:
    """The blanks as written, each once."""
    return list(dict.fromkeys(s for *_, s in spans(text)))


def refusal(text: str) -> str:
    """'Fill in [REASON] first' while a blank remains; '' when the text can go."""
    b = find(text)
    if not b: return ''
    return f"Fill in {b[0] if len(b) == 1 else ', '.join(b[:-1]) + ' and ' + b[-1]} first"

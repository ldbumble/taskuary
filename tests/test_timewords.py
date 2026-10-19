"""HOW A TIME AND A COUNT ARE SAID, once (taskuary/timewords.py, website/src/timeWords.js): every "5m ago" the server writes comes from
the one module, the page's twin says the same words, and no file grows its own formatter again - the walk said "5 min ago" beside
the rail's "5m", the wall "47h ago" beside the page's "2d ago", the asks block "yesterday" (the cleanup round, 2026-10-18)."""
import io, re, tokenize
from datetime import datetime, timedelta
from pathlib import Path

from taskuary import timewords as tw

ROOT = Path(tw.__file__).resolve().parents[1]
NOW = datetime(2026, 10, 18, 9, 0)
def at(m): return (NOW - timedelta(minutes=m)).strftime('%Y-%m-%d %H:%M:%S')


def test_ago_behind_ahead_and_nowhere():
    assert [tw.ago(at(m), NOW) for m in (0, 0.4, 1, 59, 60, 150, 1439, 1440, 47 * 60, 3 * 1440 + 600)] == \
        ['just now', 'just now', '1m ago', '59m ago', '1h ago', '2h ago', '23h ago', '1d ago', '1d ago', '3d ago']
    assert [tw.ago(at(m), NOW) for m in (-0.4, -5, -150, -3 * 1440)] == ['just now', 'in 5m', 'in 2h', 'in 3d']   # a skewed clock reads forward
    assert [tw.ago(x, NOW) for x in (None, '', 'not a date')] == ['', '', '']
    assert tw.ago(NOW - timedelta(minutes=5), NOW) == '5m ago'                                                       # a datetime too
    assert tw.ago(at(2 * 1440), NOW, long=True) == '2 days ago' and tw.ago(at(60), NOW, long=True) == '1 hour ago'
    assert tw.ago_m(65, exact=True) == '1h05m ago' and tw.span(4, exact=True) == '4m'


def test_until_and_back_in():
    assert [tw.until_m(m) for m in (0, -3, 12, 90, 3000)] == ['now', 'now', 'in 12m', 'in 1h', 'in 2d']
    assert [tw.back_in(at(-m), NOW) for m in (10, 45, 185, 3000, -5)] == ['in 30m', 'in 1h', 'in 3h', 'in 2d', '']
    assert tw.back_in(None, NOW) == '' and tw.back_in('garbage', NOW) == ''


def test_the_page_says_what_the_server_says():
    """The cases in website/test/timeWords.test.mjs, run against this side: one rule, two languages."""
    js = (ROOT / 'website' / 'test' / 'timeWords.test.mjs').read_text(encoding='utf-8')
    cases = re.findall(r'\bago\(at\((-?[\d.]+(?: \* \d+)?)\), now\), "([^"]*)"', js)
    assert len(cases) >= 6, cases
    for expr, want in cases: assert tw.ago(at(eval(expr, {'__builtins__': {}})), NOW) == want, (expr, want)


# a hand-written age: a placeholder, maybe a unit, then " ago" - "{m} min ago", "{h}h ago", "{days} day(s) ago", "{ago} ago"
AGE = re.compile(r"\{[^{}]*\}\s?(?:[mhd]|min|mins|minutes?|hours?|days?|day\(s\))?\s+ago\b")
def strings(path: Path):
    for t in tokenize.generate_tokens(io.StringIO(path.read_text(encoding='utf-8')).readline):
        if t.type == tokenize.STRING: yield t.start[0], t.string


def test_no_module_writes_its_own_ago():
    for old in ("f'{m} min ago'", "f'{h}h ago'", 'f"{days} day(s) ago"', "f\"{days} day{'s' if days != 1 else ''} ago\"", "f'({_span(d)} ago)'"):
        assert AGE.search(old), old                                                 # the shapes it replaced would be caught
    hits = [f'{p.relative_to(ROOT)}:{n}: {s[:80]}' for p in sorted((ROOT / 'taskuary').rglob('*.py')) if p.name != 'timewords.py'
            for n, s in strings(p) if AGE.search(s) or s.strip('\'"') == 'just now']
    assert not hits, 'say a time with taskuary.timewords (ago / ago_m / until_m / back_in):\n' + '\n'.join(hits)


# a count and its noun pluralised by hand - "{n} task{'s' if n != 1 else ''}" - the shape that wrote "1 tasks" wherever one was missed
_E = r"[^{}\n]+?"
COUNTED = [re.compile(r"\{(" + _E + r")\} [\w/ -]{0,40}?\w\{(['\"])s\2 if (" + _E + r") ?!= ?1 else \2\2\}"),
           re.compile(r"\{(" + _E + r")\} [\w/ -]{0,40}?\w\{(['\"])\2 if (" + _E + r") ?== ?1 else \2s\2\}")]
def counted_by_hand(s: str) -> bool: return any(m.group(1).strip() == m.group(3).strip() for p in COUNTED for m in p.finditer(s))


def test_plural_says_one_and_many():
    assert [tw.plural(1, 'task'), tw.plural(0, 'task'), tw.plural(3, 'reply', 'replies')] == ['1 task', '0 tasks', '3 replies']


def test_no_module_pluralises_a_count_by_hand():
    assert counted_by_hand("f\"{n} task{'s' if n != 1 else ''}\"") and counted_by_hand("f\"{n} task{'' if n == 1 else 's'}\"")
    hits = [f'{p.relative_to(ROOT)}:{n}: {s[:80]}' for p in sorted((ROOT / 'taskuary').rglob('*.py')) if p.name != 'timewords.py'
            for n, s in strings(p) if counted_by_hand(s)]
    assert not hits, 'say a count with taskuary.timewords.plural:\n' + '\n'.join(hits)

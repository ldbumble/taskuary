"""HOW A TIME AND A COUNT ARE SAID, once - "5m ago", "in 12m", "just now", "2 days ago", "1 task" / "3 tasks". Every sentence the
server writes about when, or about how many, asks here; website/src/timeWords.js is the page's twin and a test holds the two to
the same words. Each surface had grown its own: the wall said "47h ago" where the page said "2d ago", the walk "5 min ago" beside
the rail's "5m", the asks block "yesterday" for anything a day old, and a stamp a minute ahead read "-1 min ago" (2026-10-18)."""
from datetime import datetime


def plural(n, one: str, many: str = None) -> str:
    """'1 task', '3 tasks' - the count and its noun, never "1 tasks"."""
    return f"{n} {one if n == 1 else many or one + 's'}"


def mins(stamp, now: datetime = None):
    """Minutes from `stamp` to `now` - past is positive, ahead negative. None when it is no time at all."""
    try:
        d = stamp if isinstance(stamp, datetime) else datetime.fromisoformat(str(stamp)[:19].replace('T', ' '))
        return ((now or datetime.now()) - d).total_seconds() / 60
    except (TypeError, ValueError): return None


def span(m, long: bool = False, exact: bool = False) -> str:
    """How long `m` minutes is: '5m' / '3h' / '2d' in whole units, '5 minutes' / '3 hours' / '2 days' long, '1h05m' exact (the
    uptime line, where the minutes past the hour are the point)."""
    m = max(0, int(m))
    if exact: return f'{m // 60}h{m % 60:02d}m' if m >= 60 else f'{m}m'
    n, u = (m, 'minute') if m < 60 else (m // 60, 'hour') if m < 1440 else (m // 1440, 'day')
    return plural(n, u) if long else f'{n}{u[0]}'


def ago_m(m, long: bool = False, exact: bool = False) -> str:
    """'just now' inside a minute either way, '5m ago' behind, 'in 5m' ahead - a stamp a clock wrote ahead is not an age."""
    m = round(m)
    return 'just now' if abs(m) < 1 else f'{span(m, long, exact)} ago' if m > 0 else f'in {span(-m, long, exact)}'


def ago(stamp, now: datetime = None, long: bool = False, exact: bool = False) -> str:
    """ago_m of a stamp - '' when it is no time at all."""
    m = mins(stamp, now)
    return '' if m is None else ago_m(m, long, exact)


def until_m(m) -> str:
    """'now' once it is due, else 'in 12m' / 'in 2h' / 'in 3d' - `m` minutes from now (a meeting's start)."""
    m = round(m)
    return 'now' if m < 1 else f'in {span(m)}'


def back_in(stamp, now: datetime = None) -> str:
    """'in 30m', 'in 1h', 'in 3h', 'in 2d' until a For later row comes back - "< 30m" read as an age (the owner, 2026-09-30), so it
    reads forward as a meeting's does. '' once due, or for no time. funnelPile.railBack (timeWords.bandUntil) is the rail's live copy."""
    m = mins(stamp, now)
    m = None if m is None else round(-m)
    return '' if m is None or m <= 0 else 'in 30m' if m < 30 else 'in 1h' if m < 60 else f'in {span(m)}'

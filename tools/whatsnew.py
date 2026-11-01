"""WHAT EACH RELEASE CHANGED, written onto the docs page the Assistant searches (docs/site/whats-new.md, read by docs.search).

The app could not say what an update brought (TQ-1251: "Taskuary doesnt know about itself"): the tags say only "Release X", and
the changes lived in commit messages. tools/release.sh runs this before the docs build; the section it writes is a draft in the
commits' own first lines, and a hand edit to the page before the release commit is kept.

  python tools/whatsnew.py 0.3.10.12               # the commits since the last tag, as 0.3.10.12, on top of the page
  python tools/whatsnew.py --backfill 10           # a section for each of the last 10 tags that has none yet
"""
import argparse, datetime, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / 'docs' / 'site' / 'whats-new.md'
HEAD = ('# What\'s new\n\nWhat each release changed, newest first. Ask the Assistant "what changed in the last update?" and it reads '
        'this page.\n')
# the release's own housekeeping, never a change anyone would notice
CHORE = re.compile(r'^(Release \d|Refresh the README|Rebuild the UI|Merge |Revert "Release|Bump )', re.I)
# a commit that touched only these changed nothing in the app
INTERNAL = ('tests/', 'tools/', 'website/browser/', 'website/test/', '.github/', 'taskuary/web/', 'site/', 'docs/plans/', 'docs/superpowers/')


def git(*a) -> str: return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def changes(lo: str, hi: str = 'HEAD') -> list:
    """The first lines of the commits between two refs that changed the app, oldest first."""
    out = []
    for sha in git('log', '--no-merges', '--reverse', '--format=%H', f'{lo}..{hi}' if lo else hi).split():
        subj = git('log', '-1', '--format=%s', sha).strip()
        files = [f for f in git('show', '--name-only', '--format=', sha).split('\n') if f]
        if CHORE.match(subj) or not files or all(f.startswith(INTERNAL) for f in files): continue
        if subj not in out: out.append(subj)
    return out


def section(v: str, day: str, lines: list) -> str:
    return f'## {v} - {day}\n\n' + ('\n'.join(f'- {l}' for l in lines) if lines else '- Maintenance only: nothing you would notice.') + '\n'


def has(text: str, v: str) -> bool: return re.search(rf'^## {re.escape(v)} ', text, re.M) is not None


def write(sections: list):
    """Sections go on top, newest first, under the page's head; a version already on the page is left as written."""
    text = PAGE.read_text(encoding='utf-8') if PAGE.exists() else HEAD
    body = text[len(HEAD):].lstrip('\n') if text.startswith(HEAD) else text.split('\n', 1)[1].lstrip('\n') if text.startswith('# ') else text
    new = [s for v, s in sections if not has(text, v)]
    PAGE.write_text(HEAD + '\n' + '\n'.join(new + ([body] if body.strip() else [])), encoding='utf-8', newline='\n')
    return len(new)


def tags() -> list: return [t for t in git('tag', '--sort=creatordate').split() if re.fullmatch(r'v\d+(\.\d+)+', t)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('version', nargs='?'); ap.add_argument('--backfill', type=int, default=0)
    a = ap.parse_args()
    ts = tags()
    if a.backfill:
        pick = ts[-a.backfill:]
        prev = {t: (ts[ts.index(t) - 1] if ts.index(t) else '') for t in pick}
        secs = [(t[1:], section(t[1:], git('log', '-1', '--format=%cs', t).strip(), changes(prev[t], t))) for t in reversed(pick)]
    else:
        if not a.version: ap.error('name the version, or --backfill N')
        secs = [(a.version, section(a.version, datetime.date.today().isoformat(), changes(ts[-1] if ts else '')))]
    print(f'{write(secs)} section(s) written to {PAGE.relative_to(ROOT)}')


if __name__ == '__main__': main()

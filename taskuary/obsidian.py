"""AN OBSIDIAN VAULT, READ WHERE IT LIES (the owner, 2026-11-08: "yes do all of them").

A vault is a folder of Markdown notes on this computer, so the card is that folder's path and nothing else: no key, no plugin, no server.
`obsidian_read` lists the latest notes, finds the ones a word is in (title or text, with the line around it), or reads one note - and only
inside the vault: a path that climbs out of it, a link that points out of it, the app's own .obsidian folder and its .trash are never read.
Nothing is written. A Knowledge base card pointed at the same folder indexes it for meaning; this card is the quick, exact look.
"""
import json, os
from pathlib import Path

MAX_NOTES, NOTE_CHARS, AROUND = 50, 20000, 160


def vault(cfg: dict) -> Path:
    v = str((cfg or {}).get('vault') or '').strip().strip('"')
    if not v: raise RuntimeError('no vault folder set on the Obsidian card - the folder your notes (and its .obsidian folder) are in')
    p = Path(os.path.expandvars(os.path.expanduser(v))).resolve()
    if not p.is_dir(): raise RuntimeError(f'the Obsidian card names {p}, which is not a folder on this computer')
    return p


def _inside(root: Path, f: Path) -> bool:
    try: r = f.resolve(); return r.is_relative_to(root) and not any(x.startswith('.') for x in r.relative_to(root).parts)
    except (OSError, ValueError): return False
def notes(root: Path) -> list:
    "The vault's notes, newest first - never a hidden folder's (.obsidian, .trash) nor a link out of the vault."
    return sorted((f for f in root.rglob('*.md') if _inside(root, f)), key=lambda f: f.stat().st_mtime, reverse=True)
def _rel(root, f) -> str: return f.resolve().relative_to(root).as_posix()
def _read(f) -> str: return f.read_text(encoding='utf-8', errors='replace')


def run(cfg: dict) -> tuple:
    """{"search": "budget"} finds notes with the word; {"note": "Projects/Q3.md"} reads one; {} lists the latest. Reads only."""
    root, n = vault(cfg), max(1, min(int(cfg.get('max_rows') or MAX_NOTES), 500))
    if cfg.get('note'):
        f = root / str(cfg['note']).strip().lstrip('/\\')
        f = f if f.suffix.lower() == '.md' else f.with_name(f.name + '.md')
        if not _inside(root, f) or not f.is_file(): raise ValueError(f"no note {cfg['note']!r} in the vault")
        return f'Obsidian note {_rel(root, f)}', _read(f)[:NOTE_CHARS]
    q, hits = str(cfg.get('search') or '').strip().lower(), []
    for f in notes(root):
        row = {'note': _rel(root, f), 'title': f.stem}
        if q:
            t = _read(f); i = t.lower().find(q)
            if i < 0 and q not in f.stem.lower(): continue
            if i >= 0: row['around'] = t[max(0, i - AROUND):i + len(q) + AROUND].strip()
        hits.append(row)
        if len(hits) >= n: break
    return f"Obsidian: {len(hits)} notes{f' with {q!r}' if q else ''}", json.dumps(hits, indent=1, ensure_ascii=False)


def test(store, c) -> str:
    from .reports import _card
    root = vault(_card(store, 'obsidian', 'api_key', c['ConnectorId']))
    return f'found {len(notes(root))} notes in the {root.name} vault - reports and agents can now read them'

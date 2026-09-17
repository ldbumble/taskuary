"""Importing somebody else's expertise, as a profile.

A skill is HOW a job is done - eleven knowledge-work plugins of it, written by people who do those
jobs, stuck in one vendor's directory where only Claude Code can read them. Converted once it becomes
an ordinary Taskuary profile, and an ordinary profile drives a codex session.

It never becomes a PLAYBOOK. A playbook's fields are uses/alone/ask first/done when - every one about
acting on a system - and a SKILL.md states none of them, so converting to one meant inventing `uses:`,
which decides whether CODER.md's repository rules apply. A profile needs a purpose and a body, and
both are already in the file. Nothing is guessed.

This module finds and parses. It writes nothing and fetches nothing it was not pointed at.
"""
import json, re
from pathlib import Path

# Where Claude Code keeps them. Read-only, and the only thing we know about another tool's disk.
SKILL_GLOBS = ('.claude/skills/*/SKILL.md',
               '.claude/plugins/cache/*/*/*/skills/*/SKILL.md')
_FM = re.compile(r'^---\s*\n(.*?)\n---\s*\n?(.*)$', re.S)
_KEY = re.compile(r'^(name|description)\s*:\s*(.*)$', re.M)


def parse(text: str) -> dict:
    """{name, description, body} from a SKILL.md. The frontmatter is metadata about the skill, not
    part of the rules a worker follows, so it does not travel into the body."""
    m = _FM.match(str(text or ''))
    head, body = (m.group(1), m.group(2)) if m else ('', str(text or ''))
    found = {k: v.strip().strip('"\'') for k, v in _KEY.findall(head)}
    return {'name': found.get('name', ''), 'description': found.get('description', ''),
            'body': body.strip()}


def _plugin_of(root: Path) -> tuple:
    """(name, description) from .claude-plugin/plugin.json - what a folder of skills calls itself."""
    p = root / '.claude-plugin' / 'plugin.json'
    if not p.is_file(): return '', ''
    try: j = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError): return '', ''
    return str(j.get('name') or ''), str(j.get('description') or '')


def _entry(path: Path, plugin: str = '', plugin_desc: str = '', name: str = None) -> dict:
    """`name` overrides the frontmatter for folder-based discovery: a `skills/<name>/SKILL.md` glob
    means the directory IS the skill's identity (Claude Code's own convention), so it outranks
    whatever the frontmatter claims. A bare single-file read has no such folder to trust, and falls
    back to the frontmatter (then the enclosing directory, whatever that happens to be)."""
    text = path.read_text(encoding='utf-8', errors='replace')
    got = parse(text)
    return {**got, 'name': name or got['name'] or path.parent.name, 'path': str(path),
            'plugin': plugin, 'plugin_desc': plugin_desc, 'bytes': len(text)}


def read_path(p: str) -> list:
    """One entry for a SKILL.md, or one per skill for a plugin folder. `commands/` is not read: a
    command is a thing invoked by name, which an attached playbook already is."""
    root = Path(p)
    if root.is_file(): return [_entry(root)]
    if not root.is_dir(): return []
    pname, pdesc = _plugin_of(root)
    return sorted((_entry(f, pname, pdesc, f.parent.name) for f in root.glob('skills/*/SKILL.md')),
                  key=lambda e: e['name'])


def found(home: Path = None) -> list:
    """Every skill already installed on this machine, for the picker.

    The plugin name comes from which of SKILL_GLOBS matched, not from counting path segments back
    from the end: '.claude/skills/*/SKILL.md' is a personal skill (no plugin), and in
    '.claude/plugins/cache/*/*/*/skills/*/SKILL.md' the plugin is the second '*' - the marketplace
    cache's own layout, not an assumption about how deep `home` itself is nested."""
    home = home or Path.home()
    out = [_entry(f, name=f.parent.name) for f in sorted(home.glob(SKILL_GLOBS[0]))]
    for f in sorted(home.glob(SKILL_GLOBS[1])):
        rel = f.relative_to(home).parts  # .claude/plugins/cache/<mkt>/<plugin>/<ver>/skills/<name>/SKILL.md
        plugin = rel[4] if len(rel) > 4 else ''
        out.append(_entry(f, plugin, name=f.parent.name))
    return out

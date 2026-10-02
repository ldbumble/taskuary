"""Pages a Claude session publishes with its Artifact tool, kept on the task that ran the session.

The tool answers {url, artifact_id, title, version, path, ...} - path being the local file it published
from. The link is what the owner opens; the copy of that file is what the task page previews in place,
because claude.ai refuses to be framed by any other site (frame-ancestors 'self').
"""
import re, shutil
from pathlib import Path

from loguru import logger

from . import session_artifacts

KIND = 'claude_artifact'
MAX_COPY = 16 * 1024 * 1024                       # the Artifact tool's own page limit
_URL = re.compile(r'^https://claude\.ai/(?:code/)?artifact/([0-9a-f-]{8,})$')
# "Published <path> at <url>" - the tool_result's text, for a road that carries no structure
_SAID = re.compile(r'Published\s+(?P<path>.+?)\s+at\s+(?P<url>https://claude\.ai/(?:code/)?artifact/[0-9a-f-]{8,})')
_COPYABLE = {'.html': 'text/html', '.htm': 'text/html', '.md': 'text/markdown'}


def published(res, text: str = '') -> dict | None:
    """The page this tool result says was published, or None. A claude.ai artifact url is the proof -
    a url merely mentioned in another tool's output is not a publish."""
    r = res if isinstance(res, dict) else {}
    m = _URL.match(str(r.get('url') or ''))
    if m:
        return {'url': r['url'], 'artifact_id': str(r.get('artifact_id') or m.group(1)), 'title': str(r.get('title') or '').strip(),
                'version': str(r.get('version') or ''), 'path': str(r.get('path') or '')}
    m = _SAID.search(str(text or ''))
    if not m: return None
    return {'url': m.group('url'), 'artifact_id': _URL.match(m.group('url')).group(1), 'title': '', 'version': '', 'path': m.group('path').strip()}


def from_stream(j: dict) -> dict | None:
    """A claude stream-json `user` event carrying an Artifact tool's result (tool_use_result = the structure)."""
    if not isinstance(j, dict) or j.get('type') != 'user': return None
    text = ' '.join(str(c.get('content') if isinstance(c.get('content'), str) else '')
                    for c in (j.get('message') or {}).get('content') or [] if isinstance(c, dict) and c.get('type') == 'tool_result')
    return published(j.get('tool_use_result') or j.get('toolUseResult'), text)


def _copy(tid: int, aid: str, src: str) -> Path | None:
    """The published file, copied under the task's artifact folder - one file per page, the newest version."""
    try:
        p = Path(src)
        if p.suffix.lower() not in _COPYABLE or not p.is_file() or p.stat().st_size > MAX_COPY: return None
        folder = session_artifacts.root() / str(int(tid)); folder.mkdir(parents=True, exist_ok=True)
        dst = folder / f"claude-{re.sub(r'[^0-9a-f-]', '', aid)[:40]}{p.suffix.lower()}"
        shutil.copyfile(p, dst)
        return dst
    except OSError as e:
        logger.debug(f'claude artifact: no local copy of {src}: {e}'); return None


def keep(store, tid: int, info: dict, by: str = 'agent') -> dict | None:
    """Record a publish on the task: a new page gets a row, a republish updates its row."""
    if not (store and tid and info): return None
    dst = _copy(tid, info['artifact_id'], info.get('path') or '')
    fields = {'Name': info.get('title') or 'Claude artifact', 'Url': info['url'], 'Version': info.get('version') or '',
              'Path': str(dst) if dst else '', 'Size': dst.stat().st_size if dst else 0,
              'ContentType': _COPYABLE.get(dst.suffix, 'text/html') if dst else 'text/html'}
    old = store.task_artifact_by_ext(tid, KIND, info['artifact_id'])
    if old:
        store.update_task_artifact(old['ArtifactId'], fields)
        aid = old['ArtifactId']
    else:
        aid = store.add_task_artifact({**fields, 'TaskId': tid, 'Kind': KIND, 'ExtId': info['artifact_id'], 'CreatedBy': by})
    store.audit('task_artifact', aid, 'update' if old else 'create', by, detail={'task_id': tid, 'kind': KIND, 'version': fields['Version']})
    return store.get_task_artifact(aid)


def capture(store, tid: int, res, text: str = '', by: str = 'agent') -> dict | None:
    """One door for both roads (hooks.receive, general's stream): never raises into the agent's turn."""
    try:
        info = published(res, text)
        return keep(store, tid, info, by) if info else None
    except Exception as e:
        logger.warning(f'claude artifact not kept on task {tid}: {e}'); return None

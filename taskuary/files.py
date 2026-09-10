"""Files in and files out: a network share and an SFTP server, as cards with tools.

Every file-shaped connector before this one was a WINDOW - `local_file`, `sharepoint_file`,
`s3_object` and `azure_blob` are all `read` (scopes.py). So "save it onto the share" had exactly one
road: hand the job to a coding CLI, because that agent has a shell and a shell can write a UNC path.
That road works and is how this was done until now. It also has no card, no credential in the
connector store, no entry on the authority ladder and no receipt - the four things every other
system Taskuary touches has. These two cards give files the same treatment money got: the write is
proposed, the owner approves, and the run is audited.

Two protocols in one module (`research.py` and `markets.py` do the same), because what they share is
the part worth keeping in one place: the rule that a caller's path stays under the card's root.

- **smb_file** - on Windows a share IS a path, so `smb_read` resolves under the card's root and then
  DELEGATES to `reports.run_local_file`: its csv/tsv/json/xlsx parsers, its glob-for-the-newest, its
  tail-a-log and its newest-first folder listing, not a second copy of any of them. Credentials are
  optional and usually blank - Taskuary runs on the owner's own computer, and on a domain-joined box
  that session already reaches the share; demanding a service account to read a folder they can open
  in Explorer is a setup step invented for nothing.
- **sftp** - paramiko, in `deps.BUNDLE` so a desktop download arrives able to use the card. The host
  key is REJECTED unless it matches the card, never learned (paramiko's AutoAddPolicy): an agent
  tool that trusts whatever answers on port 22 cannot tell its own server from someone standing in
  front of it.

Both write, which is new here, so three rules are enforced below rather than assumed:

1. **A path stays under the card's root** (`under_local` / `under_remote`), checked before any I/O
   and never clamped. `share` and `root` are in `reports.CONNECTION_KEYS`, so a tool call cannot
   bring its own root - the same reason `base_url` is in that list (audit 2026-09-02).
2. **A write never silently replaces a document.** Without `overwrite: true` a collision is written
   under a " (2)" name and the headline says which name it got.
3. **A write's local source is inside ~/.taskuary** - the attachments tree or the sftp staging
   directory, nothing else. Otherwise `{"source_path": "C:/Users/x/.ssh/id_rsa"}` makes this an
   exfiltration tool that reads with the owner's privileges and writes to a company share.
"""
import base64, hashlib, io, os, posixpath, re, shutil, stat as statmod
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from loguru import logger

from . import spawn

STAGE = 'sftp'                 # ~/.taskuary/sftp/<host>/ - where sftp_get lands, and the only place it can
MAX_WRITE = 200 * 1024 * 1024  # a document, not a disk image: a runaway copy onto a company share is the failure
SUFFIX_TRIES = 99              # " (2)" ... " (99)", then refuse rather than loop


class Refused(RuntimeError):
    """A path that could not be PROVED to be inside its root, or a source outside ~/.taskuary.

    Its own class because every raise site here is the same decision - fail closed, and be wrong in
    the direction that asks permission (scopes.py's phrasing). A refused path is never clamped into
    the root instead: silently rewriting where a document goes is worse than not writing it.
    """


# ── the path rule ────────────────────────────────────────────────────────────────────────────

_DRIVE = re.compile(r'^[A-Za-z]:')


def _rel(p) -> str:
    """The caller's half of a path, as a relative posix-ish string.

    A path that tries to BE a root - absolute, UNC, or a drive switch - is refused here rather than
    quietly joined onto one, and so is any '..' segment. Backslashes are normalized because the
    owner will type the Windows path they see in Explorer and the agent will pass the posix one it
    read in a playbook; refusing one of the two would be a trap, not a check.
    """
    s = str(p or '').strip().replace('\\', '/')
    if not s: return ''
    # "/" alone has exactly one meaning here - the folder on the card - and every path in this
    # module is relative to that. Any OTHER absolute path is refused rather than reinterpreted:
    # quietly reading '/etc/passwd' as 'etc/passwd' under the share is the clamping this module
    # promises never to do.
    if not s.strip('/'): return ''
    if s.startswith('/'): raise Refused(f'{p!r} is absolute - give a path relative to the folder on the card')
    if _DRIVE.match(s): raise Refused(f'{p!r} names its own drive - give a path relative to the folder on the card')
    if any(seg == '..' for seg in s.split('/')): raise Refused(f'{p!r} climbs out of the folder on the card - refused')
    return s.strip('/')


def _inside(base: Path, p) -> Path:
    """`p`, proved to be `base` or under it. `is_relative_to` on RESOLVED paths, never a string
    startswith - C:/Ops2 starts with C:/Ops and is a different folder."""
    try: rp = Path(p).resolve()
    except (OSError, ValueError) as e: raise Refused(f'{p} cannot be resolved ({e})')
    if rp != base and not rp.is_relative_to(base): raise Refused(f'{p} is outside {base} - refused')
    return rp


def under_local(root: str, rel) -> Path:
    """The real path for a caller-supplied `rel` under the card's `root` - or `Refused`.

    resolve() comes BEFORE the check so a symlink inside the share pointing out of it is caught too,
    not just a '..' in the text.
    """
    if not str(root or '').strip():
        raise Refused('this card has no folder set - enter the share root on the connector card')
    base = Path(str(root).rstrip('/\\') or str(root)).expanduser()
    try: rbase = base.resolve()
    except (OSError, ValueError) as e: raise Refused(f'the share root {base} cannot be resolved ({e})')
    r = _rel(rel)
    return _inside(rbase, base / r) if r else rbase


def under_remote(base: str, rel) -> str:
    """The same rule on the OTHER machine, and therefore posixpath only: resolve() would ask this
    disk about a path that lives on a server. `base` is already absolute - the card's `root`, or the
    login directory when it has none."""
    b = '/' + str(base or '').strip().strip('/')
    r = _rel(rel)
    full = posixpath.normpath(posixpath.join(b, r)) if r else b
    # _rel already refused '..', so this cannot currently fail. It stays because it is the invariant
    # the module promises, and the next person to touch _rel should be caught by a test, not a share.
    if full != b and not full.startswith(b.rstrip('/') + '/'):
        raise Refused(f'{rel!r} resolves outside {b} - refused')
    return full


def _name(n) -> str:
    """A filename with no path in it. An attachment's own name arrives from a mail and 'name' is
    whatever the sender called it, so the basename is taken on both separators."""
    s = str(n or '').replace('\\', '/').split('/')[-1].strip()
    s = re.sub(r'[\x00-\x1f<>:"|?*]', '_', s)[:150]
    if not s or s in ('.', '..'): raise Refused(f'{n!r} is not a usable filename')
    return s


def _dest_rel(path, default_name: str) -> str:
    """Where a write lands, relative to the root.

    A `path` ending in a separator is a FOLDER and the file keeps its own name; anything else IS the
    name to write - which is how "rename and save" is one call instead of two. That is the
    convention the SharePoint card already uses ("a path ending in / lists the folder"), so there is
    one rule here and not two.
    """
    s = str(path or '').strip()
    if s and not s.replace('\\', '/').endswith('/'): return _rel(s)
    folder = _rel(s)
    if not default_name:
        raise Refused(f'"{s or "/"}" is a folder and this write has no filename - give the name in '
                      '"path", or write from an attachment or a file that brings one')
    return posixpath.join(folder, _name(default_name)) if folder else _name(default_name)


def _free(exists, rel: str, overwrite: bool) -> tuple:
    """(the path actually used, a note for the headline).

    A silent overwrite is the one failure in this module that leaves no receipt at all - the owner
    approved "a document into this folder", not "whatever was already called that, gone". So a
    collision gets " (2)" and the headline SAYS the name changed; `overwrite: true` in the call is
    the way to mean it.
    """
    if overwrite or not exists(rel): return rel, ''
    stem, dot, ext = posixpath.basename(rel).rpartition('.')
    head = posixpath.dirname(rel)
    # '.gitignore'.rpartition('.') is ('', '.', 'gitignore') - a dotfile is all name and no
    # extension, and keeping the separator would number it '.gitignore (2).'
    if not stem: stem, dot, ext = posixpath.basename(rel), '', ''
    for n in range(2, SUFFIX_TRIES + 1):
        cand = posixpath.join(head, f'{stem} ({n}){dot}{ext}') if head else f'{stem} ({n}){dot}{ext}'
        if not exists(cand): return cand, f' - {posixpath.basename(rel)} was already there, so it was saved as {posixpath.basename(cand)}'
    raise Refused(f'{rel} and {SUFFIX_TRIES} numbered variants all exist - nothing was written')


# ── what a write is made of ──────────────────────────────────────────────────────────────────

def _ours(p) -> Path:
    """A local file this connector may read: inside ~/.taskuary and nowhere else.

    The same check `server._attachment_path` makes before serving an attachment, for the same
    reason - a path column pointing outside that tree would turn a tool into an arbitrary local
    file read, and here it would turn one into an arbitrary local file COPY, onto a share other
    people read.
    """
    from . import config
    return _inside(config.home().resolve(), p)


def _source(cfg) -> tuple:
    """(bytes or None, a local Path or None, the file's own name) - exactly one of three sources.

    Three because three things produce a document here: a worker composing `text`, a file an earlier
    `sftp_get` staged (`source_path`), and the `attachment` a mail arrived with - which is one call
    rather than a fetch and a write (the owner, 2026-09-08: "yes attachement id included").

    A Path comes back instead of bytes wherever there IS one, so a large file is streamed rather
    than held in memory.
    """
    given = [k for k in ('text', 'attachment', 'source_path') if cfg.get(k) not in (None, '')]
    if not given: raise Refused('nothing to write - give "text", an "attachment" id, or a "source_path"')
    if len(given) > 1: raise Refused(f'{" and ".join(given)} both given - a write has one source')
    if cfg.get('text') not in (None, ''):
        data = str(cfg['text']).encode('utf-8')
        if len(data) > MAX_WRITE: raise Refused(f'that text is {len(data)} bytes - over the {MAX_WRITE} byte limit')
        return data, None, ''
    if cfg.get('attachment') not in (None, ''):
        store = cfg.get('store')
        if store is None: raise RuntimeError('writing from an attachment needs the store - call this through /api/tools/run')
        try: row = store.get_attachment(int(cfg['attachment']))
        except (TypeError, ValueError): raise Refused('"attachment" must be an attachment id (a number)')
        if not row: raise Refused(f"there is no attachment {cfg['attachment']}")
        if not row.get('Path'):
            raise Refused(f"attachment {cfg['attachment']} ({row.get('Name') or 'unnamed'}) has no file on disk - "
                          'a linked or inline attachment is recorded without its bytes')
        return None, _ours(row['Path']), row.get('Name') or Path(row['Path']).name
    p = _ours(cfg['source_path'])
    if not p.is_file(): raise Refused(f'{p} is not a file')
    return None, p, p.name


def _size(data, src) -> int:
    return len(data) if data is not None else src.stat().st_size


def _check_size(n: int):
    if n > MAX_WRITE: raise Refused(f'{n} bytes is over the {MAX_WRITE} byte limit for one write')


# ── smb_file: the share ──────────────────────────────────────────────────────────────────────

_mapped_roots = set()


def _mapped(cfg) -> str:
    """The share root, with the card's credentials applied first if it carries any.

    Blank credentials is the NORMAL case and returns immediately. When they are set, `net use`
    establishes a session for the whole PROCESS - which is the known limit of this approach: two
    cards on the SAME server under different accounts is not handled (the second would win), while
    two cards on two servers are fine. Per-call authentication is what a real SMB library would buy
    and it was traded away to keep run_local_file's parsers and add no dependency.
    """
    root = str(cfg.get('share') or '').strip()
    if not root: raise Refused('this card has no share set - enter the root, e.g. \\\\fileserv\\Ops\\Documents')
    user, pw = str(cfg.get('username') or '').strip(), str(cfg.get('password') or '')
    if not user or not pw or root in _mapped_roots: return root
    # credentials only mean something for a SERVER. A local or already-mounted path with a username
    # on the card is a card someone filled in too eagerly, not an instruction to authenticate to
    # C:\ - and deriving a \\host\share from a local path produced exactly that nonsense.
    if not root.replace('/', '\\').startswith('\\\\'):
        logger.info(f'smb_file: {root} is a local path - the credentials on the card are not used for it')
        return root
    if os.name != 'nt':
        logger.info('smb_file: credentials on the card are only applied on Windows - mount the share yourself here')
        return root
    # `net use` authenticates a SERVER AND SHARE (\\fileserv\Ops), not a folder inside one, so a
    # root that points deeper is trimmed back to its first two segments before asking.
    parts = [s for s in root.lstrip('\\').split('\\') if s]
    unc = '\\\\' + '\\'.join(parts[:2])
    # the password reaches `net use` as an argument, so it is briefly visible to anything reading this
    # machine's process list. It is already at rest in the connector store on the same machine, and the
    # alternative (WNetAddConnection2 through ctypes) is untested Windows-only plumbing - noted, not hidden.
    p = spawn.run(['net', 'use', unc, pw, f'/user:{user}', '/persistent:no'],
                  capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    out = ((p.stdout or '') + (p.stderr or '')).strip()
    # 1219 is "already connected with another user" - the session exists, which is what was wanted
    if p.returncode != 0 and '1219' not in out:
        raise RuntimeError(f'could not reach {unc} as {user}: {out[:300] or "net use failed"}')
    _mapped_roots.add(root)
    return root


def run_smb_read(cfg):
    """{"path": "Vendors/2026/*.pdf", "tail": 50, "sheet": "Sheet1", "pick": "name"} - a file,
    folder or glob under the share, through the same parsers a local path gets: after the root
    check it IS a local path.

    A glob is resolved HERE rather than inside run_local_file, so the file the glob chose is
    re-checked against the root - a pattern is inside the share, but the newest thing matching it
    could be a symlink that is not.
    """
    from .reports import run_local_file, _newest
    root = _mapped(cfg)
    base = under_local(root, '')
    p = under_local(root, cfg.get('path') or '')
    if any(ch in str(p) for ch in '*?['): p = _inside(base, _newest(str(p), cfg.get('pick')))
    # only the keys run_local_file reads travel on: the card's password has no business in a
    # nested call's config just because it shared a dict with the path
    keep = ('tail', 'sheet', 'max_rows', 'pick', 'delimiter', 'path_expr')
    return run_local_file({**{k: cfg[k] for k in keep if k in cfg}, 'path': str(p)})


def run_smb_write(cfg):
    """{"path": "Vendors/2026/", "attachment": 412} - put a document on the share. Also takes
    {"text": "..."} or {"source_path": "..."} as the source, and {"overwrite": true}.

    `path` ending in / is the folder and the file keeps its name; otherwise `path` is the name it
    gets, which is the rename. Needs `write` on the card, so at the shipped `read` this arrives as
    a proposal the owner approves (proposals.py) - the road a QuickBooks bill already takes.
    """
    root = _mapped(cfg)
    data, src, own = _source(cfg)
    n = _size(data, src)
    _check_size(n)
    rel = _dest_rel(cfg.get('path'), own)
    base = under_local(root, '')
    rel, note = _free(lambda r: (base / r).exists(), rel, bool(cfg.get('overwrite')))
    target = under_local(root, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    if data is not None: target.write_bytes(data)
    else: shutil.copyfile(src, target)
    logger.info(f'smb_write: {n} bytes to {target}')
    return f'{n} bytes to {rel}{note}', f'{target}'


def run_smb_move(cfg):
    """{"path": "Inbox/statement.pdf", "to": "Filed/2026/acme-statement.pdf", "overwrite": false} -
    rename or move WITHIN the share. Both ends are checked against the root, so this cannot be used
    to walk a document out of the folder the card names."""
    root = _mapped(cfg)
    src = under_local(root, cfg.get('path') or '')
    if not src.exists(): raise Refused(f"{cfg.get('path')} does not exist on the share")
    if not str(cfg.get('to') or '').strip(): raise Refused('nothing to rename to - give "to"')
    base = under_local(root, '')
    rel, note = _free(lambda r: (base / r).exists(), _dest_rel(cfg.get('to'), src.name), bool(cfg.get('overwrite')))
    target = under_local(root, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(target))
    return f'moved to {rel}{note}', f'{src} -> {target}'


# ── sftp: the server ─────────────────────────────────────────────────────────────────────────

def _paramiko():
    try: import paramiko
    except ImportError:
        from .deps import Missing
        raise Missing('paramiko', 'paramiko is not installed - the SFTP card needs it. Install it from the '
                                  'card, or run: pip install paramiko')
    return paramiko


def fingerprint(key) -> str:
    """The host key as OpenSSH prints it, so the owner can compare it with what their own ssh said
    rather than translating between two formats."""
    return 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')


def key_matches(want: str, key) -> bool:
    """Does the card's expected fingerprint name this key? SHA256 as OpenSSH writes it, or the older
    colon-hex MD5 that older docs and some appliances still print - accepting both is not laxness,
    it is accepting the string the owner actually has in front of them."""
    w = str(want or '').strip()
    if not w: return False
    md5 = hashlib.md5(key.asbytes()).hexdigest()
    forms = {fingerprint(key).lower(), fingerprint(key).split(':', 1)[1].lower(), md5,
             ':'.join(md5[i:i + 2] for i in range(0, len(md5), 2))}
    return w.lower().replace('md5:', '').rstrip('=') in {f.rstrip('=') for f in forms}


@contextmanager
def _client(cfg):
    """A connected SFTPClient, and the directory every path in this call stays under.

    Two deliberate refusals live here. The host key must MATCH the card - a card with no `hostkey`
    cannot connect at all, and the error carries the fingerprint the server offered so the owner can
    check it and paste it in. And `look_for_keys=False, allow_agent=False`: this connects with the
    credential on the card, never with whatever happens to be in the owner's ~/.ssh or ssh-agent,
    which would make the card's authority quietly larger than what it was given.
    """
    paramiko = _paramiko()
    host = str(cfg.get('host') or '').strip()
    if not host: raise Refused('this card has no host set - enter the SFTP server')
    user = str(cfg.get('username') or '').strip()
    if not user: raise Refused('this card has no username set')
    try: port = int(cfg.get('port') or 22)
    except (TypeError, ValueError): raise Refused(f"port {cfg.get('port')!r} is not a number")
    secret, want = str(cfg.get('password') or ''), str(cfg.get('hostkey') or '').strip()

    class _Pin(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            got = fingerprint(key)
            if not want:
                raise Refused(f'{hostname} offered host key {got}, and this card has no expected fingerprint. '
                              "Check it against your server, then paste it into the card's host key field.")
            if not key_matches(want, key):
                raise Refused(f'{hostname} offered host key {got}, but this card expects {want} - refused. '
                              'Either the server changed its key or this is not the server.')

    pkey = None
    if secret.lstrip().startswith('-----BEGIN'):
        for cls in ('Ed25519Key', 'RSAKey', 'ECDSAKey', 'DSSKey'):
            try: pkey = getattr(paramiko, cls).from_private_key(io.StringIO(secret)); break
            except Exception: continue
        if pkey is None:
            raise RuntimeError('the private key saved on this card could not be read - paste the whole '
                               'file including its BEGIN/END lines, and note an encrypted key is not supported')
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(_Pin())
    try:
        client.connect(hostname=host, port=port, username=user, pkey=pkey,
                       password=None if pkey else (secret or None),
                       look_for_keys=False, allow_agent=False, timeout=30)
        sftp = client.open_sftp()
        base = str(cfg.get('root') or '').strip() or sftp.normalize('.')
        try: yield sftp, base
        finally: sftp.close()
    finally:
        client.close()


def _remote_exists(sftp, path: str) -> bool:
    try:
        sftp.stat(path)
        return True
    except IOError:
        return False


def run_sftp_list(cfg):
    """{"path": "outgoing/", "max_rows": 200} - a remote directory, newest first. The same
    "did today's export arrive?" answer a folder listing gives on a local disk, in the same shape."""
    from .reports import rows_out, row_limit
    lim, mine = row_limit(cfg)
    with _client(cfg) as (sftp, base):
        d = under_remote(base, cfg.get('path') or '')
        rows = [{'name': a.filename, 'bytes': int(a.st_size or 0),
                 'modified': datetime.fromtimestamp(a.st_mtime).strftime('%Y-%m-%d %H:%M') if a.st_mtime else ''}
                for a in sftp.listdir_attr(d) if not statmod.S_ISDIR(a.st_mode or 0)]
    rows.sort(key=lambda r: r['modified'], reverse=True)
    return rows_out(rows, lim, unit=f'files in {posixpath.basename(d.rstrip("/")) or d}', mine=mine)


def staging(cfg) -> Path:
    """~/.taskuary/sftp/<host>/ - the one directory sftp_get may write, which is what keeps it a
    `read` on the ladder."""
    from . import config
    d = config.home() / STAGE / re.sub(r'[^A-Za-z0-9._-]+', '_', str(cfg.get('host') or 'server'))
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_sftp_get(cfg):
    """{"path": "outgoing/statement.pdf"} - fetch ONE file into ~/.taskuary/sftp/ and answer with
    its local path. That path is a legal `source_path` for smb_write, which is what makes
    pull-rename-save four calls and no shell at all.

    It writes a file and is still a `read` on the ladder: the ladder measures what a call reaches
    UPSTREAM (the reasoning above `metric` and `kb_search` in scopes.py). This moves nothing on the
    server and can land in exactly one directory. Staging is a cache and behaves like one - a
    re-fetch overwrites its own staged copy, because the no-silent-overwrite rule is about DOCUMENTS
    and nothing reads a staged file except the call that was handed its path.
    """
    if not str(cfg.get('path') or '').strip(): raise Refused('nothing to fetch - give the remote "path"')
    with _client(cfg) as (sftp, base):
        remote = under_remote(base, cfg['path'])
        try: n = int(sftp.stat(remote).st_size or 0)
        except IOError: raise Refused(f"{cfg['path']} does not exist on {cfg.get('host')}")
        _check_size(n)
        local = staging(cfg) / _name(posixpath.basename(remote))
        sftp.get(remote, str(local))
    logger.info(f'sftp_get: {n} bytes from {remote} to {local}')
    return f'{n} bytes from {posixpath.basename(remote)}', str(local)


def run_sftp_put(cfg):
    """{"path": "incoming/", "attachment": 412} - upload a document. Same three sources as
    smb_write (`text`, `attachment`, `source_path`) and the same `overwrite` rule, because "put a
    file somewhere" should not have two different spellings depending on which card it lands on."""
    data, src, own = _source(cfg)
    n = _size(data, src)
    _check_size(n)
    with _client(cfg) as (sftp, base):
        rel, note = _free(lambda r: _remote_exists(sftp, under_remote(base, r)),
                          _dest_rel(cfg.get('path'), own), bool(cfg.get('overwrite')))
        target = under_remote(base, rel)
        if data is not None: sftp.putfo(io.BytesIO(data), target)
        else: sftp.put(str(src), target)
    return f'{n} bytes to {rel}{note}', target


def run_sftp_move(cfg):
    """{"path": "outgoing/x.pdf", "to": "processed/x.pdf"} - rename the remote file. This is the
    "mark it done so tomorrow's poll does not fetch it again" step, and the reason a job can be
    idempotent without Taskuary keeping a list of what it has already seen."""
    if not str(cfg.get('path') or '').strip(): raise Refused('nothing to rename - give "path"')
    if not str(cfg.get('to') or '').strip(): raise Refused('nothing to rename to - give "to"')
    with _client(cfg) as (sftp, base):
        src = under_remote(base, cfg['path'])
        if not _remote_exists(sftp, src): raise Refused(f"{cfg['path']} does not exist on {cfg.get('host')}")
        rel, note = _free(lambda r: _remote_exists(sftp, under_remote(base, r)),
                          _dest_rel(cfg.get('to'), posixpath.basename(src)), bool(cfg.get('overwrite')))
        target = under_remote(base, rel)
        sftp.rename(src, target)
    return f'moved to {rel}{note}', f'{src} -> {target}'


# ── the Test button ──────────────────────────────────────────────────────────────────────────

def test_smb(store, c) -> str:
    """Reach the share and count what is in it. Says WHICH credentials got there, because "blank
    means your own Windows session" is invisible otherwise and is the thing an owner needs to know
    when it works here and fails on the server."""
    from .reports import smb_connection
    cfg = smb_connection(store, c.get('ConnectorId'))
    root = _mapped(cfg)
    p = under_local(root, '')
    if not p.is_dir(): raise RuntimeError(f'{root} is not reachable as a folder from this machine')
    n = sum(1 for _ in p.iterdir())
    who = f"as {cfg['username']}" if cfg.get('username') and cfg.get('password') else 'with your own Windows session'
    return f'{root} reachable {who} - {n} items in the root'


def test_sftp(store, c) -> str:
    """Connect, verify the host key against the card, and list the base directory. A card with no
    host key fails here with the fingerprint to paste in, which makes Test the way that field gets
    filled rather than a thing the owner has to know to do first."""
    from .reports import sftp_connection
    cfg = sftp_connection(store, c.get('ConnectorId'))
    with _client(cfg) as (sftp, base):
        files = [a for a in sftp.listdir_attr(base) if not statmod.S_ISDIR(a.st_mode or 0)]
        how = 'private key' if str(cfg.get('password') or '').lstrip().startswith('-----BEGIN') else 'password'
    return f"{cfg.get('username')}@{cfg.get('host')} OK ({how}, host key verified) - {base}, {len(files)} files"

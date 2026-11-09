"""A Node.js of Taskuary's own, for the WhatsApp bridge: the official portable build from nodejs.org, checksum-checked and
unpacked under the data folder. No installer, no administrator, no PATH change - the way an app brings its runtime along.

A fresh Windows client has no Node, and the bridge is `node bridge.mjs` (#278). Asking the person to install Node in a terminal
was the step nobody took - "just install in background and get it to work" (the owner, 2026-11-09). The zip is ~36 MB once; a
Node already on the machine is used before this one is fetched (wabridge.node).
"""
import hashlib, io, os, platform, shutil, tarfile, zipfile
from pathlib import Path
from loguru import logger

VERSION = 'v24.22.2'                        # an LTS; its archives' sha256, from nodejs.org/dist/<VERSION>/SHASUMS256.txt
SHA256 = {'win-x64.zip': 'ca1bff5d8ead13c9f2ea404a176db46bd430704d5b5113734049fa365e7799e2',
          'win-arm64.zip': 'f47968c213105077f64c6510f007632c0ca2574802a0b5067c327c49abe1c468',
          'linux-x64.tar.gz': '361718c444e49af2ca5a110c83ba6a8901143f23ab285ebbef0341f391f482a9',
          'darwin-arm64.tar.gz': 'aa9549349e47dffaa42dcf95d6e06ade8c4bdafc980979883b88767670df385a'}
BASE = 'https://nodejs.org/dist'


def home() -> Path:
    from . import config
    return config.home() / 'node'


def asset(system: str = None, machine: str = None) -> str:
    "This computer's archive, e.g. 'win-x64.zip'; '' where nodejs.org builds none."
    s, m = (system or platform.system()).lower(), (machine or platform.machine()).lower()
    arch = 'arm64' if m in ('arm64', 'aarch64') else 'x64' if m in ('amd64', 'x86_64', 'x64') else ''
    if not arch: return ''
    return f'win-{arch}.zip' if s == 'windows' else f'linux-{arch}.tar.gz' if s == 'linux' else f'darwin-{arch}.tar.gz' if s == 'darwin' else ''


def _dir(a: str) -> Path: return home() / f"node-{VERSION}-{a.rsplit('.', 2)[0] if a.endswith('.tar.gz') else a.rsplit('.', 1)[0]}"


def _exe(d: Path) -> Path: return d / 'node.exe' if os.name == 'nt' else d / 'bin' / 'node'


def find() -> str:
    "Our node, when it has been fetched; else ''."
    a = asset()
    return str(_exe(_dir(a))) if a and _exe(_dir(a)).is_file() else ''


def _sha(a: str, get) -> str:
    if a in SHA256: return SHA256[a]
    # an arch this file does not pin: nodejs.org's own list, over HTTPS
    txt = get(f'{BASE}/{VERSION}/SHASUMS256.txt', stream=False).text
    return next((l.split()[0] for l in txt.splitlines() if l.strip().endswith(f'node-{VERSION}-{a}')), '')


def fetch(say=lambda s: None, get=None) -> str:
    """Download, check and unpack our node; its path. Raises RuntimeError with what went wrong, in words.
    `say` hears the progress ("downloading Node.js - 12 of 36 MB"); `get` stands in for requests.get in a test."""
    if (have := find()): return have
    a = asset()
    if not a: raise RuntimeError(f'nodejs.org has no Node.js build for this computer ({platform.system()} {platform.machine()})')
    import requests
    get = get or (lambda url, stream=True: requests.get(url, stream=stream, timeout=(10, 60)))
    url = f'{BASE}/{VERSION}/node-{VERSION}-{a}'
    try:
        want = _sha(a, get)
        if not want: raise RuntimeError(f'nodejs.org lists no checksum for node-{VERSION}-{a}')
        r = get(url); r.raise_for_status()
        total, buf, h, last = int(r.headers.get('content-length') or 0), io.BytesIO(), hashlib.sha256(), -1
        for chunk in r.iter_content(1 << 16):
            buf.write(chunk); h.update(chunk)
            mb = buf.tell() >> 20
            if mb != last and mb % 2 == 0:
                last = mb; say(f'Setting up WhatsApp - downloading Node.js, {mb} of {total >> 20} MB' if total else f'downloading Node.js, {mb} MB')
    except requests.RequestException as e:
        raise RuntimeError(f"could not download Node.js from nodejs.org ({str(e)[:120]}) - check the internet connection, a VPN, or a "
                           'company firewall, then press Start bridge again')
    if h.hexdigest() != want:
        raise RuntimeError(f'the Node.js download did not match its published checksum, so it was thrown away - press Start bridge to try again')
    say('Setting up WhatsApp - unpacking Node.js')
    home().mkdir(parents=True, exist_ok=True)
    tmp = home() / f'.unpack-{os.getpid()}'
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        buf.seek(0)
        if a.endswith('.zip'):
            with zipfile.ZipFile(buf) as z: _safe(tmp, z.namelist()); z.extractall(tmp)
        else:
            with tarfile.open(fileobj=buf, mode='r:gz') as t: _safe(tmp, t.getnames()); t.extractall(tmp)
        src, dst = tmp / _dir(a).name, _dir(a)
        if not _exe(src).is_file(): raise RuntimeError(f'the Node.js archive had no {_exe(src).name} where nodejs.org puts it')
        shutil.rmtree(dst, ignore_errors=True); src.rename(dst)
    except OSError as e: raise RuntimeError(f'could not unpack Node.js into {home()} ({e})')
    finally: shutil.rmtree(tmp, ignore_errors=True)
    logger.info(f'wa bridge: Node.js {VERSION} set up at {_dir(a)}')
    return str(_exe(_dir(a)))


def _safe(root: Path, names):
    "Nothing in the archive writes outside the folder it is unpacked into."
    r = root.resolve()
    for n in names:
        if not (r / n).resolve().is_relative_to(r): raise RuntimeError(f'the Node.js archive tried to write outside its folder ({n})')

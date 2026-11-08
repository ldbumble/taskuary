"""VIDEO TOOLS FOR THE AGENTS (the owner, 2026-11-08: "agents can make and edit video with Descript, InVideo, Vidova, video-use").

Three roads, each one table and one code path, so a new product is a row:

  MCPS    a vendor's remote MCP server, registered in the agent CLIs the owner has (Claude Code: `claude mcp add --transport http
          --scope user`; Codex: `codex mcp add --url`). Sign-in is the vendor's OAuth, which the CLI does itself - Taskuary never holds
          the token, so it cannot list the server's tools either, and the send filter (sendfilter.py) would leave it out whole. The
          owner's Add press is their word on it: the server is marked kept there (sendfilter.correct '*'), which the card says.
  SKILLS  a Claude Code skill on disk (~/.claude/skills/<dir>, read by skillimport.py): Browser Use's video-use - cloned, its Python
          set up with uv (or a venv + pip), and the ElevenLabs card's key written into its own .env, which is where it reads it.
  VIDEO   a vendor API that makes a clip from a sentence with a key on a card: Kling (its own card) and Runway (the runway_image card,
          the same key) - `kling_video` / `runway_video` on /api/tools/run, the clip filed in the task's outputs like a picture.

The Add / Install press is the owner's (guard.DENIED); the demo world reaches nothing and shows every card not added.
"""
import json, os, shutil, time
from pathlib import Path
import requests
from loguru import logger

# type -> (title, url). URLs from each vendor's own docs (2026-11-08); the CLI's server name is the type.
MCPS = {'descript': ('Descript', 'https://api.descript.com/v2/mcp'),
        'invideo': ('InVideo', 'https://mcp.invideo.io/mcp'),
        'vidova': ('Vidova', 'https://mcp.vidova.ai/mcp'),
        'opusclip': ('OpusClip', 'https://mcp.opus.pro/mcp')}
# type -> how the skill lands. `dir` is the folder under the skills root that says it is here (a prefix for a pack).
SKILLS = {'video_use': {'title': 'video-use', 'dir': 'video-use', 'repo': 'https://github.com/browser-use/video-use', 'ffmpeg': True,
                        'key': ('elevenlabs_stt', 'ELEVENLABS_API_KEY')},
          'vidova': {'title': 'Vidova skills', 'dir': 'vidova', 'pack': 'youneslaaroussi/vidova-skills'}}
TYPES = tuple(dict.fromkeys([*MCPS, *SKILLS]))
CLIS = {'claude': 'Claude Code', 'codex': 'Codex'}
SIGN_IN = {'claude': 'in a Claude Code terminal type /mcp and pick {n}', 'codex': 'run `codex mcp login {n}` once'}


def _which(c):
    from . import clis
    return clis.which(c) or ''
def skills_root() -> Path:
    from .climodels import claude_home
    return claude_home() / 'skills'
def add_argv(cli: str, exe: str, name: str, url: str) -> list:
    return ([exe, 'mcp', 'add', '--transport', 'http', '--scope', 'user', name, url] if cli == 'claude' else [exe, 'mcp', 'add', name, '--url', url])
def registered(name: str) -> dict:
    from . import sendfilter
    return {'claude': name in sendfilter.claude_servers(), 'codex': name in sendfilter.codex_servers()}
def skill_here(t: str) -> bool:
    s, root = SKILLS[t], skills_root()
    if s.get('pack'): return root.is_dir() and any(p.name.startswith(s['dir']) and (p / 'SKILL.md').exists() for p in root.iterdir())
    return (root / s['dir'] / 'SKILL.md').exists()


def _key(store, t) -> str:
    "The key a skill reads from another card (video-use: the ElevenLabs card's), or ''."
    k = SKILLS.get(t, {}).get('key')
    c = store.get_connector_by_type(k[0], with_secret=True) if k and store else None
    return (c or {}).get('Secret') or ''


def state(store, t: str) -> dict:
    "What the card shows: per CLI whether the server is registered there, whether the skill is on disk, and what is still missing."
    from . import demo
    if t not in TYPES: raise ValueError(f'{t} is not a video tool')
    title, url = MCPS.get(t, (SKILLS.get(t, {}).get('title'), ''))
    out = {'type': t, 'title': title, 'url': url, 'clis': {}, 'skill': None, 'missing': [], 'sign_in': []}
    if demo.enabled(): return {**out, 'demo': True}          # the demo world shows nobody's machine
    if url:
        on = registered(t)
        out['clis'] = {c: {'here': bool(_which(c)), 'added': on[c]} for c in CLIS}
        out['sign_in'] = [SIGN_IN[c].format(n=t) for c, v in out['clis'].items() if v['added']]
        if not any(v['here'] for v in out['clis'].values()): out['missing'].append('Claude Code or Codex on this computer')
    if s := SKILLS.get(t):
        out['skill'] = {'name': s['title'], 'here': skill_here(t), 'repo': s.get('repo') or f"https://github.com/{s['pack']}"}
        if s.get('ffmpeg') and not _which('ffmpeg'): out['missing'].append('ffmpeg on PATH (winget install Gyan.FFmpeg, or brew install ffmpeg)')
        if s.get('key') and not _key(store, t): out['missing'].append('an ElevenLabs key on the ElevenLabs Scribe card')
    out['ready'] = not out['missing'] and (not url or all(v['added'] for v in out['clis'].values() if v['here'])) and (not s or out['skill']['here'])
    return out


def _skill_steps(store, t: str) -> list:
    "[(argv, cwd)] that put the skill on disk; video-use's .env is written after them."
    s, d = SKILLS[t], skills_root() / SKILLS[t]['dir']
    if s.get('pack'):
        npx = _which('npx') or _which('npx.cmd') or 'npx'
        return [([npx, '--yes', 'skills', 'add', s['pack'], '-g', '-y', '-a', 'claude-code'], None)]
    steps = [] if (d / '.git').exists() else [([_which('git') or 'git', 'clone', '--depth', '1', s['repo'], str(d)], None)]
    if uv := _which('uv'): return steps + [([uv, 'sync'], str(d))]
    py = _which('python') or _which('python3') or 'python'
    pip = str(d / '.venv' / ('Scripts' if os.name == 'nt' else 'bin') / 'pip')
    return steps + [([py, '-m', 'venv', '.venv'], str(d)), ([pip, 'install', '-e', '.'], str(d))]


def _write_env(d: Path, var: str, key: str):
    "The key on its own line in the skill's .env (where video-use reads it), every other line kept."
    f = d / '.env'
    lines = [l for l in (f.read_text(encoding='utf-8').splitlines() if f.exists() else []) if not l.startswith(f'{var}=')]
    f.write_text('\n'.join([*lines, f'{var}={key}']) + '\n', encoding='utf-8')


def _run(argv, cwd=None, timeout=900) -> tuple:
    from . import spawn
    r = spawn.run(argv, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    return int(r.returncode or 0), ((r.stdout or '') + (r.stderr or '')).strip()


def add(store, t: str, actor: str = 'owner', runner=None) -> dict:
    """The card's Add / Install press: register the MCP server in each CLI here that lacks it, mark it kept for the send filter, and put
    the skill on disk. The card turns on once all of that answered. Returns state() with `said`, one line per step."""
    from . import demo, sendfilter
    if demo.enabled(): raise RuntimeError('This is the demo - nothing is installed here.')
    run, said, st = runner or _run, [], state(store, t)
    for c, v in st['clis'].items():
        if not v['here'] or v['added']: continue
        rc, out = run(add_argv(c, _which(c), t, MCPS[t][1]), None, 120)
        said.append(f"{CLIS[c]}: {'added' if rc == 0 else f'did not add it ({out[-200:]})'}")
    if st['url'] and any(v['added'] for v in state(store, t)['clis'].values()):
        sendfilter.correct(store, t, '*', 'keep', actor)       # its tools cannot be listed without the vendor's sign-in: the owner's Add keeps it
    if t in SKILLS:
        for argv, cwd in _skill_steps(store, t):
            rc, out = run(argv, cwd, 900)
            if rc: said.append(f"{Path(argv[0]).name} {argv[1]} failed: {out[-300:]}"); break
        else:
            if (k := SKILLS[t].get('key')) and (key := _key(store, t)): _write_env(skills_root() / SKILLS[t]['dir'], k[1], key)
            said.append(f"{SKILLS[t]['title']}: installed")
    st = state(store, t)
    if st['ready'] and (c := store.get_connector_by_type(t)) and not c.get('Active'):
        store.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1}, actor)
    store.audit('connector', 0, 'video_tool_added', actor, detail={'type': t, 'said': said})
    return {**st, 'said': said}


def test(store, t: str) -> str:
    "The card's Test: what is in place, or what is still missing (raised, so the card shows it as a failure)."
    st = state(store, t)
    if st['missing']: raise RuntimeError('still needs ' + '; '.join(st['missing']))
    have = [CLIS[c] for c, v in st['clis'].items() if v['added']] + ([st['skill']['name']] if st['skill'] and st['skill']['here'] else [])
    if not have: raise RuntimeError(f"{st['title']} is not added yet - press Add on its card")
    return f"{st['title']} is ready in {', '.join(have)}" + (f" - to sign in, {' or '.join(st['sign_in'])}" if st['sign_in'] else '')


# ── a clip from a sentence, on a key card ─────────────────────────────────────────────────────────────────────────────────────────
KLING = 'https://api-singapore.klingai.com'        # kling.ai/document-api: the endpoint for servers outside China
RUNWAY, RUNWAY_VERSION = 'https://api.dev.runwayml.com/v1', '2024-11-06'
WAIT, EVERY = 600, 5                                # a clip takes minutes, not seconds
RATIOS = {'16:9': '1280:720', '9:16': '720:1280', '1:1': '960:960'}


def _poll(get, done):
    "Ask `get()` every few seconds until `done(job)` says (url, '') or ('', why); a clip still cooking after WAIT is a failure."
    end = time.time() + WAIT
    while time.time() < end:
        url, why = done(get())
        if url or why: return url, why
        time.sleep(EVERY)
    return '', f'the clip was still not ready after {WAIT}s'


def _kling(cfg, prompt, seconds, ratio, image):
    h = {'Authorization': f"Bearer {cfg['api_key']}", 'Content-Type': 'application/json'}
    model = cfg.get('model') or 'kling-2.6'
    body = {'prompt': prompt[:2500], 'settings': {'duration': 10 if seconds > 7 else 5, 'aspect_ratio': ratio if ratio in RATIOS else '16:9'}}
    if image: body['contents'] = [{'type': 'first_frame', 'url': image}]
    r = requests.post(f"{KLING}/{'image' if image else 'text'}-to-video/{model}", headers=h, json=body, timeout=120); r.raise_for_status()
    tid = ((r.json() or {}).get('data') or {}).get('id')
    if not tid: raise RuntimeError(f'Kling started no task: {r.text[:200]}')
    def done(j):
        d = (j.get('data') or [{}])[0]
        if d.get('status') == 'failed': return '', d.get('message') or 'Kling refused it'
        return next((o.get('url') for o in d.get('outputs') or [] if o.get('type') == 'video'), '') if d.get('status') == 'succeeded' else '', ''
    return _poll(lambda: requests.get(f'{KLING}/tasks', headers=h, params={'task_ids': tid}, timeout=60).json() or {}, done), h, model


def _runway(cfg, prompt, seconds, ratio, image):
    h = {'Authorization': f"Bearer {cfg['api_key']}", 'X-Runway-Version': RUNWAY_VERSION, 'Content-Type': 'application/json'}
    model = cfg.get('video_model') or 'gen4.5'
    body = {'model': model, 'promptText': prompt[:1000], 'ratio': RATIOS.get(ratio, '1280:720'), 'duration': max(2, min(10, seconds))}
    if image: body['promptImage'] = image
    r = requests.post(f"{RUNWAY}/{'image' if image else 'text'}_to_video", headers=h, json=body, timeout=120); r.raise_for_status()
    tid = (r.json() or {}).get('id')
    if not tid: raise RuntimeError(f'Runway started no task: {r.text[:200]}')
    def done(j):
        if j.get('status') in ('FAILED', 'CANCELLED'): return '', j.get('failure') or 'Runway refused it'
        return ((j.get('output') or [''])[0] if j.get('status') == 'SUCCEEDED' else ''), ''
    return _poll(lambda: requests.get(f'{RUNWAY}/tasks/{tid}', headers=h, timeout=60).json() or {}, done), {}, model


def _make(vendor, fn, cfg) -> tuple:
    """{"prompt": "...", "seconds": 5, "ratio": "16:9|9:16|1:1", "image_url": "(optional: animate this picture)", "task_id": N} - makes a
    short clip with the owner's card and files it in the task's outputs, where the task page offers it."""
    from . import outputs
    prompt, tid = str(cfg.get('prompt') or '').strip(), cfg.get('task_id')
    if not prompt: raise RuntimeError('a clip needs a prompt')
    if not str(tid or '').isdigit(): raise RuntimeError('a clip needs a task to land on - pass task_id; nothing was made')
    if not cfg.get('api_key'): raise RuntimeError(f'the {vendor} card has no API key')
    (url, why), h, model = fn(cfg, prompt, int(cfg.get('seconds') or 5), str(cfg.get('ratio') or '16:9'), cfg.get('image_url') or '')
    if not url: raise RuntimeError(f'{vendor}: {why}')
    v = requests.get(url, headers=h, timeout=300); v.raise_for_status()
    d = outputs.folder(int(tid)); d.mkdir(parents=True, exist_ok=True)
    (f := d / f'video-{int(time.time())}.mp4').write_bytes(v.content)
    logger.info(f'videotools: {vendor} made {len(v.content):,} bytes into task {tid}')
    return f"made {f.name} with {vendor} {model} into TQ-{int(tid):04d}'s outputs", json.dumps({'file': str(f), 'name': f.name, 'model': model, 'bytes': len(v.content)})


def run_kling_video(cfg): return _make('Kling', _kling, cfg)
def run_runway_video(cfg): return _make('Runway', _runway, cfg)
run_kling_video.__doc__ = run_runway_video.__doc__ = _make.__doc__


def test_kling(c) -> str:
    "The Kling card's Test: its task list, which spends nothing."
    r = requests.post(f'{KLING}/tasks', headers={'Authorization': f"Bearer {c.get('Secret') or ''}"}, json={'limit': 1}, timeout=30)
    if r.status_code >= 300 or (r.json() or {}).get('code') not in (0, None): raise RuntimeError(f'Kling answered {r.status_code}: {r.text[:200]}')
    return 'Kling accepted the key - agents can make clips with kling_video'

"""VIDEO TOOLS FOR THE AGENTS (the owner, 2026-11-08: "agents can make and edit video with Descript, InVideo, Vidova, video-use").

Three roads, each one table and one code path, so a new product is a row:

  MCP     a vendor's remote MCP server in the agent CLIs (remotemcp.py, the road every MCP card rides): Descript, InVideo, Vidova and
          OpusClip are rows of the catalogue with an `mcp` url.
  SKILLS  a Claude Code skill on disk (~/.claude/skills/<dir>, read by skillimport.py): Browser Use's video-use - cloned, its Python
          set up with uv (or a venv + pip), and the ElevenLabs card's key written into its own .env, which is where it reads it.
  VIDEO   a vendor API that makes a clip from a sentence with a key on a card: Kling (its own card) and Runway (the runway_image card,
          the same key) - `kling_video` / `runway_video` on /api/tools/run, the clip filed in the task's outputs like a picture.

The Add / Install press is the owner's (guard.DENIED); the demo world reaches nothing and shows every card not added.
"""
import json, os, time
from pathlib import Path
import requests
from loguru import logger
from . import remotemcp as rm

# type -> how the skill lands. `dir` is the folder under the skills root that says it is here (a prefix for a pack). Vidova is a server too.
SKILLS = {'video_use': {'title': 'video-use', 'dir': 'video-use', 'repo': 'https://github.com/browser-use/video-use', 'ffmpeg': True,
                        'key': ('elevenlabs_stt', 'ELEVENLABS_API_KEY')},
          'vidova': {'title': 'Vidova skills', 'dir': 'vidova', 'pack': 'youneslaaroussi/vidova-skills'}}


def skills_root() -> Path:
    from .climodels import claude_home
    return claude_home() / 'skills'
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
    "The server's state (remotemcp.state) where it has one, and whether the skill is on disk and what it still needs."
    from . import demo
    if t not in SKILLS: raise ValueError(f'{t} has no skill')
    out = rm.state(store, t) if t in rm.MCPS else {'type': t, 'title': SKILLS[t]['title'], 'url': '', 'clis': {}, 'missing': [], 'sign_in': []}
    if demo.enabled(): return {**out, 'demo': True}
    s = SKILLS[t]
    out['skill'] = {'name': s['title'], 'here': skill_here(t), 'repo': s.get('repo') or f"https://github.com/{s['pack']}"}
    if s.get('ffmpeg') and not rm._which('ffmpeg'): out['missing'].append('ffmpeg on PATH (winget install Gyan.FFmpeg, or brew install ffmpeg)')
    if s.get('key') and not _key(store, t): out['missing'].append('an ElevenLabs key on the ElevenLabs Scribe card')
    out['ready'] = out.get('ready', True) and not out['missing'] and out['skill']['here']
    return out


def _skill_steps(store, t: str) -> list:
    "[(argv, cwd)] that put the skill on disk; video-use's .env is written after them."
    s, d, w = SKILLS[t], skills_root() / SKILLS[t]['dir'], rm._which
    if s.get('pack'): return [([w('npx') or w('npx.cmd') or 'npx', '--yes', 'skills', 'add', s['pack'], '-g', '-y', '-a', 'claude-code'], None)]
    steps = [] if (d / '.git').exists() else [([w('git') or 'git', 'clone', '--depth', '1', s['repo'], str(d)], None)]
    if uv := w('uv'): return steps + [([uv, 'sync'], str(d))]
    py = w('python') or w('python3') or 'python'
    pip = str(d / '.venv' / ('Scripts' if os.name == 'nt' else 'bin') / 'pip')
    return steps + [([py, '-m', 'venv', '.venv'], str(d)), ([pip, 'install', '-e', '.'], str(d))]


def _write_env(d: Path, var: str, key: str):
    "The key on its own line in the skill's .env (where video-use reads it), every other line kept."
    f = d / '.env'
    lines = [l for l in (f.read_text(encoding='utf-8').splitlines() if f.exists() else []) if not l.startswith(f'{var}=')]
    f.write_text('\n'.join([*lines, f'{var}={key}']) + '\n', encoding='utf-8')


def add(store, t: str, actor: str = 'owner', runner=None) -> dict:
    """The card's Add / Install press: the server where it has one (remotemcp.register), then the skill on disk. The card turns on once
    all of that answered. Returns state() with `said`, one line per step."""
    from . import demo
    if demo.enabled(): raise RuntimeError('This is the demo - nothing is installed here.')
    run = runner or rm._run
    said = rm.register(store, t, actor, run) if t in rm.MCPS else []
    for argv, cwd in _skill_steps(store, t):
        rc, out = run(argv, cwd, 900)
        if rc: said.append(f"{Path(argv[0]).name} {argv[1]} failed: {out[-300:]}"); break
    else:
        if (k := SKILLS[t].get('key')) and (key := _key(store, t)): _write_env(skills_root() / SKILLS[t]['dir'], k[1], key)
        said.append(f"{SKILLS[t]['title']}: installed")
    return rm.finish(store, t, state(store, t), said, actor, 'video_tool_added')


sign_in = rm.sign_in
def test(store, t: str) -> str: return rm.test(store, t, state(store, t))


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

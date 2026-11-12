"""The triage brain -> one provider-agnostic llm(system, user) -> str callable, the shape
triage.classify_intent expects. Which brain is the owner's choice (setting `triage_ai`):

    ''                  first ACTIVE AI connector with a key (anthropic/openai/azure_openai/
                        openrouter) - or keyless ollama, for a local model

    connector:<id>      that specific AI connector instance
    connector:<type>    legacy/default form - first active instance of that type
    cli:<agent>         your CODING CLI does the triage too - one headless run per message,
                        same brain that works the tasks, no second API key to buy

Cloud keys are cheap and instant per message; a CLI run is slower and heavier but keeps
everything on one model (and one bill). Configure it in Settings -> How mail is sorted.
"""
import base64, contextvars, hashlib, json, mimetypes, re, requests
from contextlib import contextmanager
from pathlib import Path
from time import sleep
from typing import NamedTuple

from . import aiusage, redact

# Everything that can answer a PROMPT. This list is what populates every brain picker, so a model
# that cannot emit text does not belong in it however good it is: `typesafe` (Jev) answers typed
# questions and would have nothing to say as the Assistant's brain. It is chosen on its own card.
# Providers that speak the OpenAI chat-completions schema exactly. A base url, a default model
# and a bearer key is the WHOLE integration, so they are data rather than nine near-identical
# branches - the tenth is a row here, not a code change. Every one was verified to exist by an
# unauthenticated POST returning 401/400 (a wrong path returns 404). base_url stays overridable
# for the same reason ollama's is: a gateway in front of any of them still speaks this surface.
# The model defaults are a starting point, not a promise - model names churn, the box overrides.
HIPAA_AI_URL = ''           # the HIPAA AI gateway's OpenAI-compatible address (https://<gateway>/v1) - blank until it is deployed
OPENAI_COMPATIBLE = {
    'groq':       ('https://api.groq.com/openai/v1', 'llama-3.3-70b-versatile'),
    'mistral':    ('https://api.mistral.ai/v1', 'mistral-small-latest'),
    'together':   ('https://api.together.xyz/v1', 'meta-llama/Llama-3.3-70B-Instruct-Turbo'),
    'cerebras':   ('https://api.cerebras.ai/v1', 'llama-3.3-70b'),
    'xai':        ('https://api.x.ai/v1', 'grok-2-latest'),
    'gemini':     ('https://generativelanguage.googleapis.com/v1beta/openai', 'gemini-3.8-flash'),
    'cohere':     ('https://api.cohere.ai/compatibility/v1', 'command-r-plus'),
    'deepseek':   ('https://api.deepseek.com/v1', 'deepseek-chat'),
    'perplexity': ('https://api.perplexity.ai', 'sonar'),
    # (the owner, 2026-11-08: "all the ones that say coming soon just add them now") - each base and model read off the vendor's own
    # OpenAI-compatibility page that day, not probed: Fireworks' is /inference/v1 (the /v1 once probed was a 404), Bedrock's
    # is us-east-1's - another region is its base_url - and takes a Bedrock API key as the bearer
    'fireworks_ai': ('https://api.fireworks.ai/inference/v1', 'accounts/fireworks/models/glm-5p3-flash'),
    'nvidia_nim': ('https://integrate.api.nvidia.com/v1', 'meta/llama-3.3-70b-instruct'),
    'sambanova':  ('https://api.sambanova.ai/v1', 'Meta-Llama-3.3-70B-Instruct'),
    'deepinfra':  ('https://api.deepinfra.com/v1/openai', 'meta-llama/Llama-3.3-70B-Instruct-Turbo'),
    'novita':     ('https://api.novita.ai/openai', 'meta-llama/llama-3.3-70b-instruct'),
    'hyperbolic': ('https://api.hyperbolic.ai/inference/v1', 'glm-5.3-flash'),
    'bedrock':    ('https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1', 'openai.gpt-oss-120b-1:0'),
    # HIPAA AI: an organisation's own AI (Vertex behind its gateway), switched on with an ACCESS CODE - the person's own gateway
    # key, so usage is metered per person and one code is revoked alone (the owner, 2026-10-16). The app ships no key; the address
    # is the gateway's, filled in here once it is deployed (HIPAA_AI_URL), and `hipaa-ai` is the alias the gateway maps to its model.
    'hipaa_ai':   (HIPAA_AI_URL, 'hipaa-ai'),
}

# THE GATEWAY ADDRESS IS THE CARD'S when the build ships none (HIPAA_AI_URL blank, as this public repo is): it comes with the access
# code, so the card asks for it - the card that only asked for the code could never connect (the owner, 2026-10-20). Pasted as sent,
# with or without its /v1; https, since the access code rides it - plain http only to this computer.
GATEWAY_MISSING = 'Add the gateway address you were sent, then press Connect.'
GATEWAY_NOT_HTTPS = 'The gateway address has to start with https:// - copy it again from the message your access code came in.'
GATEWAY_SILENT = "Couldn't reach that address - check it and your connection, then press Connect."
GATEWAY_NOT_GATEWAY = ('That address answered with a web page, not the AI gateway - check you pasted the gateway address you were sent, '
                       'not the admin site.')
GATEWAY_CODE = "The access code didn't work - copy all of it again and press Connect."
GATEWAY_FAULT = 'The gateway answered with an error of its own - try again in a minute, or ask whoever sent your access code.'
LOCAL_HOSTS = ('localhost', '127.0.0.1', '::1')
# A GATEWAY THAT SCALES TO ZERO (Cloud Run) answers its first request only once it has started, which took past the 15 s every other
# provider's list gets: Connect said "Couldn't reach that address" about a gateway that was booting, and the model list came back empty,
# so no job got its model. Quick to give up on an address that is not there, patient with one that is.
GATEWAY_WAIT = (15, 90)
# A SPENT BUDGET IS NOT A BROKEN AI (the owner's gateway, 2026-11-06): LiteLLM answers 422 {"error": {"type": "budget_exceeded", "message":
# "Budget has been exceeded! Team=<id> Current cost: ..."}} once a team's budget is used. Read as an effort or a format refusal it was asked
# twice more, and shown raw - a team id and a cost the person cannot act on. It is said in one line, and the card rests (brainroute.spend).
BUDGET_LINE = "{name}'s monthly budget is used up - it answers again when the budget resets or is raised"
BUDGET_REST = 3600         # seconds before a spent card is asked again: a budget raised comes back within the hour, and no poll hammers it
_BUDGET = re.compile(r'budget_exceeded|budget has been exceeded|exceeded budget', re.I)


class BudgetSpent(RuntimeError):
    "The gateway turned the call away on its budget. `until` is when the router asks it again; `unavailable` lets a backup take the call."
    unavailable = True
    def __init__(self, line: str, rest: int = BUDGET_REST):
        from datetime import datetime, timedelta
        super().__init__(line); self.until = datetime.now() + timedelta(seconds=rest)


def budget_said(text) -> str:
    "The spent-budget line inside an error however it was wrapped ('AI triage failed (...)'), else ''."
    m = re.search(r"[A-Za-z][\w .-]{0,40}?" + re.escape(BUDGET_LINE.split('{name}')[1]), str(text or ''))
    return m.group(0) if m else ''


def budget_spent(r) -> bool:
    "Did the gateway refuse on its budget? Its error's type, else its words - never a status alone: a 422 is also a refused effort or format."
    st, text = getattr(r, 'status_code', 200), getattr(r, 'text', '')
    if not isinstance(st, int) or st < 400 or not isinstance(text, str): return False
    try: e = json.loads(text).get('error')
    except (ValueError, AttributeError): e = None
    return (isinstance(e, dict) and str(e.get('type') or '') == 'budget_exceeded') or bool(_BUDGET.search(text))


def gateway_url(raw) -> str:
    """A gateway address as pasted -> its OpenAI-compatible base (https://host/v1); '' when blank. ValueError (GATEWAY_NOT_HTTPS)
    on one that is not https, or plain http anywhere but this computer."""
    from urllib.parse import urlsplit
    s = str(raw or '').strip().rstrip('/')
    if not s: return ''
    if '://' not in s: s = f'https://{s}'
    u = urlsplit(s)
    if not u.hostname or u.scheme not in ('https', 'http') or (u.scheme == 'http' and u.hostname not in LOCAL_HOSTS):
        raise ValueError(GATEWAY_NOT_HTTPS)
    path = re.sub(r'/(chat/completions|models)$', '', u.path.rstrip('/'))
    return f"{u.scheme}://{u.netloc}{path if path.endswith('/v1') else path + '/v1'}"


def gateway_base(cfg: dict) -> str:
    """The card's own address, else the one the build ships; '' when neither."""
    return gateway_url((cfg or {}).get('base_url') or OPENAI_COMPATIBLE['hipaa_ai'][0])


def gateway_problem(cfg: dict, key: str) -> str:
    """'' when the gateway answers this access code on its model list, else the one thing to fix, in the owner's words:
    no address, an address that does not answer, an address that is not the gateway, or a code the gateway turned away.
    An admin site pasted in its place answered with its page or a sign-in redirect, and a 401 from that blamed a good code: only
    the gateway's own JSON turns a code away, so redirects are not followed and anything but JSON is the wrong address."""
    try: base = gateway_base(cfg)
    except ValueError as e: return str(e)
    if not base: return GATEWAY_MISSING
    try: r = requests.get(f'{base}/models', headers={'Authorization': f'Bearer {key}'}, timeout=GATEWAY_WAIT, allow_redirects=False)
    except requests.RequestException: return GATEWAY_SILENT
    if r.status_code >= 500: return GATEWAY_FAULT
    if (body := _json(r)) is None: return GATEWAY_NOT_GATEWAY
    if r.status_code in (401, 403): return GATEWAY_CODE
    return '' if r.status_code == 200 and isinstance(body.get('data'), list) else GATEWAY_NOT_GATEWAY


def _json(r):
    """The answer's JSON object, or None when it is a page, a redirect or anything else that is not."""
    if 'json' not in (r.headers.get('Content-Type') or '').lower(): return None
    try: o = r.json()
    except ValueError: return None
    return o if isinstance(o, dict) else None

# `chatgpt` is the owner's ChatGPT plan through Sign in with ChatGPT (chatgptauth.py): no key, a signed-in account
AI_TYPES = ('anthropic', 'openai', 'azure_openai', 'vertex_ai', 'openrouter', 'ollama', 'meta', 'chatgpt') + tuple(OPENAI_COMPATIBLE)

# What a vision model will look at. "See below." is half the mail this app reads, and below was
# a screenshot - a text-only funnel filed the sentence and threw the actual ask away.
VISION_TYPES = ('image/png', 'image/jpeg', 'image/gif', 'image/webp')
VISION_MAX, VISION_BYTES = 4, 5 * 1024 * 1024      # per call: how many images, and how big each


def _jpeg_parts(b: bytes):
    "A JPEG's header segments [(marker, bytes)] and the rest from its first scan on, or None when it is not one we can walk."
    if b[:2] != b'\xff\xd8': return None
    out, i = [], 2
    while i + 4 <= len(b) and b[i] == 0xFF:
        m, n = b[i + 1], int.from_bytes(b[i + 2:i + 4], 'big')
        if m == 0xDA: return out, b[i:]
        out.append((m, b[i:i + 2 + n])); i += 2 + n
    return None


def vision_safe(ct: str, b64: str) -> str:
    """A GRAYSCALE JPEG WITH AN ADOBE MARKER IS REFUSED BY GOOGLE: Vertex answers "The provided file is malformed or corrupted and could
    not be decoded" (400) for a one-channel JPEG carrying Photoshop's APP14 segment - a signature logo saved from Photoshop, on every mail
    of a thread, so a HIPAA AI agent could never start on it (2026-11-09). APP14 only says how to read 3- or 4-channel colour; on one channel
    it means nothing, so it is dropped and every decoder reads the same picture. Anything else goes as it came."""
    if ct != 'image/jpeg': return b64
    try: b = base64.b64decode(b64)
    except ValueError: return b64
    got = _jpeg_parts(b)
    if not got: return b64
    segs, rest = got
    sof = next((s for m, s in segs if m in (0xC0, 0xC1, 0xC2)), None)
    if not sof or len(sof) < 10 or sof[9] != 1 or not any(m == 0xEE for m, _ in segs): return b64
    return base64.b64encode(b'\xff\xd8' + b''.join(s for m, s in segs if m != 0xEE) + rest).decode()
# ...and a picture the model still cannot open costs the image, never the turn: the question is asked again without it (llm._build)
_IMAGE_REFUSED = re.compile(r'could not be decoded|malformed or corrupted|invalid image|unable to process (input )?image|image.{0,30}(not supported|unsupported)', re.I)


def readable_images(store, message_ids, cap: int = VISION_MAX) -> list:
    """[(media_type, base64)] for the images on these messages, or [] when the owner has vision
    switched off. SVG and PDF are skipped: no provider takes them as image input."""
    if str(store.get_setting('vision_enabled') or '1') != '1': return []
    out = []
    for mid in message_ids or []:
        for a in store.list_attachments(mid):
            if len(out) >= cap: return out
            ct = str(a.get('ContentType') or '').split(';')[0].lower()
            path = a.get('Path')
            if not path: continue
            if ct not in VISION_TYPES:
                ct = mimetypes.guess_type(path)[0] or ''
                if ct not in VISION_TYPES: continue
            f = Path(path)
            try:
                if not f.is_file() or f.stat().st_size > VISION_BYTES: continue
                out.append((ct, base64.b64encode(f.read_bytes()).decode()))
            except OSError:
                continue
    return out
# Triage answers with a one-line JSON object, so it needs almost nothing. A report SUMMARY
# needs room - and on a reasoning model a small budget is spent thinking and the visible
# answer comes back EMPTY, which is how reports ended up filing raw data with no summary.
MAX_TOKENS = 400
# the newest Flash on Google's Agent Platform: 2.5 Flash retires there on 2026-10-20 (the owner, 2026-10-15: "use the latest flash")
VERTEX_DEFAULT = 'gemini-3.8-flash'
# What a blank model box runs per AI connection, read by make_llm and said by the AI cards (aidefaults) - ONE table. The cards
# kept a copy, and it drifted: it said Vertex ran 'google/gemini-3.8-flash' while it ran this (the router, 2026-10-25).
PROVIDER_DEFAULT = {'anthropic': 'claude-opus-5', 'openai': 'gpt-4o-mini', 'openrouter': 'openrouter/auto', 'meta': 'muse-spark-1.2',
                    'vertex_ai': VERTEX_DEFAULT}
# AN ANSWER CUT OFF BY THE LIMIT IS ASKED AGAIN WITH ROOM. A thinking model (Gemini 2.5+, the reasoning GPTs) spends its token budget
# thinking before it writes, so a 400-token triage came back with no message at all - read as a refused format, then as an error with
# no reason, and a connected Vertex AI sorted no mail (2026-10-15). Once more with this much room; empty after that says so.
ROOM = 8000
# ...and an answer CUT SHORT by its thinking is no answer either: the HIPAA AI gateway's Gemini spent 360 of the Assistant's 380 tokens
# reasoning and handed back 16 words with finish_reason 'length' - "Tell me what you'd like the routine to do-what", a CALL cut at
# `{"params` - and the chat showed the stub (the owner, 2026-11-09). A route seen thinking is asked with ROOM from then on.
_THINKS = set()            # (type, endpoint, model) whose answers were seen cut by reasoning tokens
def cut_by_thinking(j: dict) -> bool:
    "A 'length' finish whose budget went mostly to reasoning: the visible words are a stub, not the answer the cap allowed."
    ch, u = (j.get('choices') or [{}])[0], j.get('usage') or {}
    r = ((u.get('completion_tokens_details') or {}).get('reasoning_tokens')) or 0
    return ch.get('finish_reason') == 'length' and r > 0 and r * 2 >= (u.get('completion_tokens') or r)


class _ImageRefused(Exception): "A 400 that is the picture, not the question (_IMAGE_REFUSED)."


class _Empty(Exception):
    """A 200 with no answer in it - why, in the provider's own word (finish_reason)."""


# The model a CLI runs its light jobs on when nobody named one - triage, drafts, summaries - and the Assistant's, one
# tier up: on haiku it broke its own contract in the 2026-09-24 chat audit ("I don't have the lookup tools"), sonnet held.
LIGHT_DEFAULT = {'claude': 'haiku', 'codex': 'effort:low', 'gemini': VERTEX_DEFAULT}       # the newest Flash, as Vertex's
ASSISTANT_DEFAULT = {'claude': 'sonnet', 'codex': 'effort:medium', 'gemini': VERTEX_DEFAULT}
# ...and its EFFORT when the pick names none: a turn is a short answer, and sonnet's own default is high - a plain
# "next" on the phone waited on a model thinking hard about nothing (the owner, 2026-09-25: "change assistant to
# effort level of low so it goes faster"). Codex's is already in ASSISTANT_DEFAULT as its gear.
ASSISTANT_EFFORT = {'claude': 'low'}


FAST_DEFAULT = {'codex': True}     # auto: Codex's fast tier rides the plan; Claude's fast mode is billed as extra usage


def fast_on(store, cli: str) -> bool:
    """The Assistant's fast mode for this CLI: the owner's on/off, else FAST_DEFAULT (the owner, 2026-10-13: "on by default
    if you choose codex but not for claude")."""
    v = str(store.get_setting('concierge_fast') or 'auto').strip().lower()
    return v == 'on' or (v != 'off' and FAST_DEFAULT.get(cli, False))


def fast_args(cli: str) -> list:
    """The CLI's own words for its fast tier. Claude's comes as a settings FILE: inline JSON through Windows' claude.cmd shim
    is quoted by cmd.exe. Codex parses a -c value as TOML and keeps a bare word as a string, so no quotes either."""
    if cli == 'codex': return ['-c', 'service_tier=fast']
    if cli == 'claude':
        from . import config
        f = config.home() / 'assistant' / 'fast-settings.json'
        f.parent.mkdir(parents=True, exist_ok=True)
        if not f.exists() or f.read_text(encoding='utf-8') != '{"fastMode": true}': f.write_text('{"fastMode": true}', encoding='utf-8')
        return ['--settings', str(f)]
    return []


ONE_SHOT = 1500        # seconds a one-shot look-up through a CLI may run (make_cli_llm); an agent run has no such limit

# the CLIs whose PreToolUse hook can REFUSE a shell call, so a browser act can be held (browsergate.py's header says why the rest can't)
HOLDS_CLI = frozenset({'claude'})

def _general(store, task_id) -> bool:
    try: return str((store.get_task(int(task_id)) or {}).get('Kind') or '') != 'coding'
    except (TypeError, ValueError): return False


def make_cli_llm(store, agent_name: str, model: str = None, cwd: str = None, trace=None, cancel=None,
                 resume=None, cli_tools: bool = False, extra_env: dict = None, read_only: bool = None,
                 research: bool = False, gear: str = 'light', keep: str = None, extra_args: list = None, task_id=None,
                 user_settings: bool = True, hold_sid: str = None):
    """A CLI agent as the classifier: prompt in on stdin, JSON out. The repo working dir
    is dropped - triage is about the message, not about any checkout.

    And the MODEL drops a tier: `light_model` on the agent profile (Connections > AI CLI
    agents) is what runs here - triage, drafts, summaries, the digest - while the profile's
    main `model` stays reserved for the coding sessions. One brain, two gears: the classifier
    reads one email; it does not need the model that rewrites your codebase."""
    from . import agents as hub_agents
    row = hub_agents.agent_row(store, agent_name)
    if not row: return None
    prof = {k: v for k, v in json.loads(row.get('Config') or '{}').items() if k not in ('cwd', 'cwd_map')}
    # A ROLE'S ROW THAT NAMES NO CLI (synced before any brain was chosen) runs on the brain chosen for it, else on a ready one - it
    # used to run `claude` by default, on a machine where the person had only set up Codex (2026-10-21). No brain: no CLI brain.
    if not prof.get('cmd'): prof = {**prof, **hub_agents.brain_command(store, agent_name)}      # the role's own brain first
    prof = hub_agents.with_cmd(prof, store)            # ...else the one resolver's; NoAI when nothing is connected
    # a CONVERSATION that stays open between turns (clipool) - the Assistant's chat, a general agent's task
    if keep: prof['keep_alive'] = keep
    # ...and without the owner's user-level CLI settings and hooks, for the brain that asks (the Assistant's: agents._own_settings)
    if not user_settings: prof['user_settings'] = False
    # `read_only` is explicit for scheduled reports: a folder tells the agent where it may READ,
    # not whether it may write. None preserves the older caller contract where a cwd meant hands.
    no_hands = read_only if read_only is not None else not (cwd or cli_tools)
    # A ONE-SHOT WITH NO HANDS READS NONE OF THE OWNER'S OWN CLI SETUP either (agents._own_settings, as the Assistant and a general task):
    # their CLAUDE.md, skills and plugins rode every verdict, after the cached instructions and so billed whole each time - 5,624 tokens
    # written a call against 865 without them, measured on the real CLI (2026-11-11). A classifier has no use for a coding style guide
    if no_hands and not keep: prof['user_settings'] = False
    raw_args = prof.get('args')          # the profile's own, before any road below restricts them
    if not no_hands and cwd: prof['cwd'] = cwd
    elif not no_hands and cli_tools:
        # An owner-requested setup walkthrough needs the CLI's browser tool, but it still has no
        # business in a checkout. Keep its capable process in Taskuary's scratch directory.
        from . import config
        scratch = config.home() / 'scratch'; scratch.mkdir(exist_ok=True); prof['cwd'] = str(scratch)
    else:
        # The classifier reads untrusted text with every tool off. A report is different: it may
        # safely read files and the web, but never gets command, edit, write, or connector tools.
        from .clis import preset_args, quick_read_args, readonly_args, report_read_args
        from . import config
        restrict = quick_read_args if research == 'web' else report_read_args if research else readonly_args
        prof['args'] = restrict(prof['cmd'], list(prof.get('args') or preset_args(prof['cmd']) or ['-p']))
        scratch = config.home() / 'scratch'; scratch.mkdir(exist_ok=True)
        prof['cwd'] = cwd or str(scratch)
    # The ACP road is for the general agent's tool-using runs only. `no_hands` is exactly the
    # classifier - triage and the drafter, one verdict with every tool off - and it keeps argv.
    # WHO WROTE THE TASK decides the flags (origin.py), here as in a pane: a stranger's run has the CLI's own reviewer, its
    # session hooks, a trimmed environment and a folder outside Taskuary's home - or it does not run.
    stranger_mode = ''
    if task_id:
        from . import origin, clis
        try:
            if not no_hands: stranger_mode = origin.launch_mode(store, task_id, hub_agents.cli_of(prof, agent_name), str(prof.get('cmd') or ''))
            # ...and a run that would LOOK (research: Read, WebFetch) gets no tools at all: the floor is a hook, and a
            # headless look has none, so a stranger's mail could read a key and fetch it out
            elif research and origin.of_task(store, task_id)[0] == 'stranger':
                stranger_mode = 'look'
            if stranger_mode in ('auto', 'look'): sd = str(origin.stranger_dir(task_id))
        except origin.Refusal as e: raise origin.refused(e)
        from .clis import preset_args
        c = prof['cmd']; args = list(raw_args or preset_args(c) or ['-p'])
        if stranger_mode == 'auto':
            # its folder is its cwd already; --add-dir says so to Claude whatever cwd a resume or a profile brings (R25)
            prof['args'] = clis.auto_args(c, args) + ['--add-dir', sd, '--settings', origin.session_settings(store, task_id)]
            from . import agenttools                    # ...and the owner's harmless tools, Remind me's among them (agenttools.STRANGER_TOOLS)
            prof['args'] = agenttools.insert(['', *prof['args']], agenttools.stranger_args(hub_agents.cli_of(prof, agent_name), task_id, prof['args']))[1:]
            prof['acp_ok'] = False      # the reviewer rides argv; ACP's own permission answer allows everything
        elif stranger_mode == 'look': prof['args'], prof['acp_ok'] = clis.readonly_args(c, args), False     # its floor is argv's too
        if stranger_mode in ('auto', 'look'):
            prof['strict_env'], prof['cwd'] = True, sd
            # ...and its token is bound to this task, never the shared one a caller's session env carried (R28)
            from . import terminal
            extra_env = terminal.stranger_env({**terminal.session_env(agent_name, task_id), **(extra_env or {})}, task_id)
            # a conversation is kept in the folder it ran in: one from before the move cannot be picked up from here
            if resume and resume != store.get_setting(f'stranger_sid:{task_id}'): resume = None
    if not no_hands: prof.setdefault('acp_ok', True)
    else: prof['acp_ok'] = False         # a run with every tool off has nothing to permit, whatever a saved profile says
    if extra_args:
        from .clis import preset_args
        prof['args'] = list(prof.get('args') or preset_args(prof['cmd']) or ['-p']) + list(extra_args)
    # a trusted run with hands gets Taskuary's own tools and loses the owner's send tools, as a pane does (agenttools.session_args)
    if task_id and not no_hands and stranger_mode not in ('auto', 'look'):
        from .clis import preset_args
        from . import agenttools
        args = list(prof.get('args') or preset_args(prof['cmd']) or ['-p'])
        prof['args'] = agenttools.insert(['', *args], agenttools.session_args(store, hub_agents.cli_of(prof, agent_name), task_id, args))[1:]
    # ...and a general chat with a browser gets the browser hold as its own hook (hooks.browser_settings): only Claude's hook can refuse
    # a call (browsergate.HOLDS), and a stranger's run already carries its one --settings file
    # ...and A GENERAL TASK'S CLAUDE READS NONE OF THE OWNER'S OWN SETUP (hooks.general_settings): no user settings, plugins or MCP
    # servers but Taskuary's, their own CLAUDE.md left out. A coding task keeps it all - it works in their code, as they would
    trusted = task_id and not no_hands and stranger_mode not in ('auto', 'look')
    cli = hub_agents.cli_of(prof, agent_name)
    if trusted and cli == 'claude' and _general(store, task_id) and hub_agents.cli_has_flag(prof['cmd'], '--setting-sources'):
        from . import hooks
        if (f := hooks.general_settings(task_id, hold_sid or '')):
            prof['args'] = list(prof.get('args') or []) + ['--setting-sources', 'project,local', '--strict-mcp-config', '--settings', f]
    elif hold_sid and trusted and cli in HOLDS_CLI:
        from . import hooks
        if (f := hooks.browser_settings(hold_sid)): prof['args'] = list(prof.get('args') or []) + ['--settings', f]
    # WHICH GEAR this job rides. Session work - coding and general alike - takes the MAIN model;
    # the light gear is for the one-message jobs (triage, drafts, summaries, the digest). A
    # general worker session used to fall through to light whenever no main model was set, so
    # the analyst answered on the classifier's cheap model (the owner, 2026-09-16: general agents
    # use the same brain on high level like coding by default).
    light = str(prof.get('light_model') or '') if gear == 'light' else ''
    # a profile that names no light model still gets the CLI's small one: blank used to mean the MAIN model, so triage,
    # drafts and summaries ran on the coding tier (the owner, 2026-09-24: "lower model for triage/assistant")
    cli = hub_agents.cli_of(prof, agent_name)
    if gear == 'light' and not light and not model: light = LIGHT_DEFAULT.get(cli, '')
    if light.startswith('effort:'):
        # codex on a ChatGPT plan serves ONLY the plan's models - no mini/nano tier exists -
        # so its cheap gear is reasoning effort on the same model (verified: -c
        # model_reasoning_effort=low answers in a fraction of the tokens)
        prof['args'] = list(prof.get('args') or []) + ['-c', f"model_reasoning_effort={light.split(':', 1)[1].strip()}"]
    elif light:
        # 'gpt-5.4-mini@low' - a model from codex's own /model list and one of its reasoning levels
        from .climodels import split_pick
        m, eff = split_pick(light)
        prof['model'] = f'{m}@{eff}' if eff else m      # agents.run_cli spells the effort in this CLI's own flag
    # ...and the STRONG gear is what hard work steps up to (brainroute): the owner's own strong_model on this brain. Blank is
    # no strong tier - the router never asks for one then, and a caller that does gets the main model, never a guessed one.
    if gear == 'strong' and str(prof.get('strong_model') or '').strip():
        from .climodels import split_pick
        m, eff = split_pick(str(prof['strong_model']).strip())
        prof['model'] = f'{m}@{eff}' if eff else m
    if model: prof['model'] = model     # an explicit per-job model outranks the light gear
    # 300s is the CLASSIFIER's leash - one message, one verdict, and a brain that hangs for twenty
    # minutes on a mail run is a bug. An agent the owner scheduled INTO a repo (cwd) is not
    # classifying: it researches, reads the systems it has tools for and writes a document. Same
    # rule as the flags above - the classifier gets the short leash, the owner's agent keeps its
    # profile. The cap cut two of one report's four runs off at exactly "timed out after 300s" (2026-09-03).
    # ...and AN AGENT RUN IS NEVER KILLED FOR RUNNING LONG (the owner, 2026-11-04: "we can't have timeout as it's an active agent"): a
    # general agent's turn, or a run with hands, ends when the agent finishes or the owner presses Stop. The CLI profiles' 1500 s killed a
    # marketing plan, a site and a zip of materials mid-build - a saved profile may still carry it, so it is dropped here, not just unset
    if str(keep or '').startswith('general:') or cwd or cli_tools: prof.pop('timeout', None)
    elif not research: prof['timeout'] = min(int(prof.get('timeout') or 300), 300)
    else: prof['timeout'] = int(prof.get('timeout') or ONE_SHOT)     # a look-up is one-shot: it keeps a leash
    def llm(system, user, max_tokens=MAX_TOKENS, images=None, want=None):
        """max_tokens is advisory here - a CLI has no such flag; the system prompt already says
        how long the answer should be. `images` go to a one-shot claude or codex exec (agents.sees_images: triage has no tools to
        open a file, 2026-11-09); any other CLI drops them and reads files off disk itself, by the paths the prompt names. `want` is accepted and dropped
        too, and takes_want is never set: there is no wire to put a schema on, so the prompt and
        the caller's recheck (ask_json) are the whole contract here."""
        from .agents import run_cli, run_context
        kwargs = {'cancel': cancel} if cancel is not None else {}
        if extra_env: kwargs['extra_env'] = extra_env
        run_prof, prompt = shaped(system, user)
        if run_prof.get('model'): aiusage.note(str(run_prof['model']).split('@')[0])
        # A KEPT conversation goes on with the session its last call was on, not the id this brain was built with: a new
        # chat's second round (a look-up, the gate's retry) went out with no id, which clipool reads as New chat - so it
        # killed the live CLI and started another, 15 s against 2.6 s warm, and the round lost the turn it was answering.
        # A chat already under way did this all along: its rounds resume one session. One-shot brains keep their own id.
        # ...and the store and task the ACP road's permission answers read (acpgate: the send filter, a step held on THIS task)
        with run_context(store, task_id if not no_hands else None):
            out, sid, _diff = run_cli(run_prof, prompt, trace or (lambda *a: None),
                                      resume=llm.session_id if keep else resume, **({'images': images} if images else {}), **kwargs)
        # what the caller needs to CONTINUE this conversation instead of starting another one
        llm.session_id = sid or resume
        if stranger_mode in ('auto', 'look') and sid: store.set_setting(f'stranger_sid:{task_id}', sid, 'router')   # born in the stranger's folder
        return out
    def shaped(system, user):
        """The profile a call runs on and the prompt it sends - one answer for a call and for warm(), so the process warmed is
        the one the call takes."""
        run_prof, prompt = prof, f'{system}\n\n{user}'
        if system and cli == 'claude':
            # THE INSTRUCTIONS AS A SYSTEM PROMPT, not pasted above the owner's words: Claude read a persona in the user
            # turn as a prompt injection once, and said so to the owner (the 2026-09-24 audit). A file, because the
            # Assistant's is ~27K characters against Windows' 32K command line; named by its content, so a live
            # conversation (clipool keys on the command) stays warm until the instructions actually change. Without
            # hands it REPLACES Claude Code's own coding prompt; with tools it is appended to it.
            from . import config
            # ...and ONLY WHAT EVERY CALL SHARES is in that file (stable()'s blocks): Claude Code caches its system prompt as one piece,
            # so this call's own part at its end - the evidence picked for one sender - re-billed the whole guide on every mail (23,376
            # tokens written, none read, against 17,720 read with it under the instructions; measured on the real CLI, 2026-11-11).
            # It leads the turn instead, above the message it is about
            if getattr(system, 'blocks', None) and system.rest.strip(): system, user = ''.join(system.blocks), f'{system.rest.strip()}\n\n{user}'
            folder = config.home() / 'prompts'; folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"system-{hashlib.sha1(system.encode('utf-8')).hexdigest()[:16]}.md"
            if not path.exists(): path.write_text(system, encoding='utf-8')
            flag = '--system-prompt-file' if no_hands else '--append-system-prompt-file'
            # ON TOP of the args run_cli would have used - a profile with none gets the preset there, hands and all,
            # and a bare [flag, path] would have replaced it (no -p, no stream-json)
            from .clis import preset_args
            base = list(prof.get('args') or preset_args(prof['cmd']) or ['-p'])
            run_prof, prompt = {**prof, 'args': base + [flag, str(path)]}, user
        return run_prof, prompt
    def warm(system, swap: bool = False) -> bool:
        """A kept conversation's process started before its first call, on these instructions (agents.warm_cli). False when
        nothing keeps: a one-shot brain starts its CLI per call, as it always has. `swap`: only a live one launched otherwise is replaced."""
        if not keep: return False
        from .agents import warm_cli, run_context
        with run_context(store, task_id if not no_hands else None):
            return warm_cli(shaped(system, '')[0], resume=llm.session_id, extra_env=extra_env, swap=swap)
    llm.session_id, llm.warm = resume, warm
    # ...and whether it can look a fact up: only a quick call's own flags give the web (clis.quick_web), and a stranger's look has no tools
    from .clis import quick_web
    llm.looks_up = no_hands and research == 'web' and stranger_mode != 'look' and quick_web(prof['cmd'])
    # said out loud, not merely absent: a brain that CANNOT carry a schema is the one whose answer
    # is worth rechecking in code (llm.ask_json). Silence means "do not second-guess me".
    llm.takes_want = False
    return llm


def build_llm(store, pick=None, model=None, trace=None, cancel=None, resume=None,
              cli_tools: bool = False, extra_env: dict = None, research: bool = False, fallback_user=None,
              gear: str = 'light', keep: str = None, task_id=None, job: str = None, hold_sid: str = None):
    """The brain, or the demo's script. Everything in the app asks for its brain here, which is
    the one place a demo can be told to answer without a key, a CLI, or a request that leaves
    the machine (demo.py).

    `job` says what the call is FOR (brainroute.JOBS) and brainroute.choose says which brain runs it. Every call
    site in taskuary/ names one (tests/test_brainroute.py); a caller that does not is triage, as it always was."""
    from . import demo, brainroute, origin, aiusage
    r = brainroute.choose(store, job or 'triage', task=task_id, want_pick=pick, want_model=model, gear=gear)
    # the demo answers from a script: no key, no CLI, no request leaving the machine - and its route is logged, so its reason shows
    if demo.enabled(): return aiusage.metered(store, brainroute.Lazy(store, r, task_id, pick='demo'), demo.brain())
    rid = brainroute.Lazy(store, r, task_id)          # written on the brain's first call, or by a build that ends here refused (outcome)
    # held by the owner's data rule: no AI here may read it, so it waits - never what blank means, which would be one the rule keeps out
    if r.tier == 'held': brainroute.outcome(store, rid, 'refused:sensitive'); return None
    try: brain = _build_llm(store, r.pick, r.model or None, trace, cancel, resume, cli_tools, extra_env, research, fallback_user, r.gear, keep, task_id,
                            backups=r.chain, hold_sid=hold_sid)
    except Exception as e:
        brainroute.outcome(store, rid, f'refused:{type(e).__name__}' if isinstance(e, (origin.RefusedForStranger, origin.Refusal)) else 'error'); raise
    if brain is None: brainroute.outcome(store, rid, 'error' if r.pick else 'refused:no AI')
    elif getattr(brain, 'is_failover', False): brain.route = (store, rid)
    brain = aiusage.metered(store, rid, brain)       # what each call used - model, tokens, time - on this route row
    # Auto mode: a one-shot job whose answer comes back unreadable or unsure may ask a strong model ONCE (brainroute.step_up)
    if brain and r.escalate:
        brain = _StepUp(brain, lambda why: brainroute.step_up(store, r, rid, task_id, why, lambda p: _scrub(_build_llm(
            store, p, None, trace, cancel, None, cli_tools, extra_env, research, fallback_user, 'strong', None, task_id, backups=[]))))
    return _Scrubbed(brain) if brain else brain


def effective_pick(store, pick=None) -> str:
    """The pick a brain setting resolves to - the slot's own value (`triage_ai` unless `pick` names one), else
    what blank means (agents.default_pick). '' = no brain: build_llm returns None and mail files untriaged.
    ONE answer for the brain that runs and for every surface that says which one does (setup.state)."""
    primary = str(pick if pick is not None else store.get_setting('triage_ai') or '').strip()
    if primary: return primary
    from .agents import default_pick
    return default_pick(store)


def brain_status(store, pick=None) -> dict:
    """What `effective_pick` names and whether it can answer: {pick, Name, Type, ready, why}. A chosen brain that
    cannot start stays the answer - with `ready` False and `why` saying so - rather than reading as set up."""
    from . import agents as hub_agents
    primary = effective_pick(store, pick)
    out = {'pick': primary, 'Name': '', 'Type': '', 'ready': False, 'why': ''}
    if not primary:                                    # build_llm reads '' as the first connector that can answer
        c = hub_agents.ready_connector(store)
        if not c: return {**out, 'why': 'no CLI agent runs on this machine and no AI connector holds a key'}
        primary = f"connector:{c['ConnectorId']}"
    if primary.startswith('cli:'):
        # the SAME lookup the brain is built with (agents.agent_row): a connected CLI with no worker profile is a
        # brain too, and store.get_agent alone called it "not set up" while triage ran on it (2026-09-24)
        row = hub_agents.agent_row(store, primary[4:])
        if not row: return {**out, 'why': f'{primary[4:]} is chosen, but no CLI agent of that name is set up here'}
        try: prof = json.loads(row.get('Config') or '{}')
        except ValueError: prof = {}
        ok, cli = hub_agents.runs_here(prof), hub_agents.cli_of(prof, row['Name'])
        return {**out, 'Name': f"{row['Name']} (CLI)", 'Type': 'cli', 'ready': ok,
                'why': '' if ok else f"{row['Name']} is chosen, but '{cli}' is not installed on this machine"}
    want = primary[10:] if primary.startswith('connector:') else primary
    c = next((c for c in store.list_connectors() if c['Type'] in AI_TYPES
              and (c['ConnectorId'] == int(want) if want.isdigit() else c['Type'] == want)), None)
    if not c: return {**out, 'why': f'{primary} is chosen, but no such AI connector exists'}
    ok = bool(c['Active'] and (c['HasSecret'] or c['Type'] == 'ollama'))
    return {**out, **c, 'ready': ok, 'why': '' if ok else f"{c['Name'] or c['Type']} is chosen, but it is switched off or has no key"}


class _Scrubbed:
    """A brain with the credentials taken out of what it is asked.

    Wrapping HERE is the point: `build_llm` is the one door every hosted call in the app goes
    through, so triage, the assistant, the concierge, the drafter and the digest are all covered
    by one seam instead of each remembering. See redact.py for what is taken and what is not.

    It proxies attributes rather than copying them because `failover` sets `.session_id` and
    `.last_pick` DURING a call, and a resumed CLI thread is carried on exactly those.
    """
    def __init__(self, brain): object.__setattr__(self, '_brain', brain)
    def __call__(self, system, user, *a, **kw):
        return self._brain(system.map(redact.scrub) if isinstance(system, Stable) else redact.scrub(system), redact.scrub(user), *a, **kw)
    def __getattr__(self, k): return getattr(object.__getattribute__(self, '_brain'), k)
    def __setattr__(self, k, v): setattr(object.__getattribute__(self, '_brain'), k, v)


def _scrub(brain): return _Scrubbed(brain) if brain else brain


class _Cooling:
    """A CLI brain that, refused on its usage allowance with a time it comes back, says so to the router (brainroute.cool): the
    next call goes to a backup until then, instead of to the brain that will refuse it again. The refusal itself still raises.
    ...and an AI card whose budget is spent (BudgetSpent) rests the same way - and while it rests it is not asked at all: the call
    raises the same line at once, so a poll with no backup holds its mail without a request per message (brainroute.spend)."""
    def __init__(self, store, pick, brain):
        for k, v in (('_store', store), ('_pick', pick), ('_brain', brain)): object.__setattr__(self, k, v)
    def __call__(self, *a, **kw):
        from . import brainroute
        if (line := brainroute.spent(self._store, self._pick)): raise BudgetSpent(line)
        try: out = self._brain(*a, **kw)
        except Exception as e:
            if isinstance(e, BudgetSpent): brainroute.spend(self._store, self._pick, str(e), e.until)
            elif getattr(e, 'until', None): brainroute.cool(self._store, self._pick, e.until)
            raise
        brainroute.unspend(self._store, self._pick)
        from . import agents
        agents.answered(self._store, self._pick)
        return out
    def __bool__(self): return bool(object.__getattribute__(self, '_brain'))
    def __getattr__(self, k): return getattr(object.__getattribute__(self, '_brain'), k)
    def __setattr__(self, k, v): setattr(object.__getattribute__(self, '_brain'), k, v)


class _StepUp:
    """A one-shot brain that may ask a stronger one once (the router's escalation, Auto mode only). It answers exactly as the brain
    it wraps; `step_up(why)` is what ask_json calls when the answer could not be used - it returns the strong brain, or None when
    there is none, the day's cap is spent, or this item already stepped up once."""
    is_step_up = True
    def __init__(self, brain, up): object.__setattr__(self, '_brain', brain); object.__setattr__(self, '_up', up)
    def __call__(self, *a, **kw): return self._brain(*a, **kw)
    def step_up(self, why: str):
        up = object.__getattribute__(self, '_up'); object.__setattr__(self, '_up', lambda why: None)    # once per brain built
        return up(why)
    def __getattr__(self, k): return getattr(object.__getattribute__(self, '_brain'), k)
    def __setattr__(self, k, v): setattr(object.__getattribute__(self, '_brain'), k, v)


def _build_llm(store, pick=None, model=None, trace=None, cancel=None, resume=None,
               cli_tools: bool = False, extra_env: dict = None, research: bool = False, fallback_user=None,
               gear: str = 'light', keep: str = None, task_id=None, backups: list = None, hold_sid: str = None):
    """The brain named by `pick` ('' = first active AI connector, 'connector:<id>',
    'cli:<agent>'), defaulting to the triage_ai setting - callers like reports may name
    their OWN brain and model per job instead of riding the triage tier. The owner's ordered
    backup-brain setting applies to both cases, but a fallback uses its own model and starts a
    fresh conversation - provider-specific model/session identifiers never cross that line."""
    settings = store.get_settings()
    primary = effective_pick(store, pick if pick is not None else settings.get('triage_ai') or '')   # blank = the default brain
    # the route's chain (brainroute.Route.chain) is the one list a failover walks; read here only for a caller that has none
    if backups is None: backups = [x.strip() for x in str(settings.get('triage_backup_ai') or '').split(',') if x.strip()]
    # This dedupe SURVIVES the role/brain split, unlike its twin in agent_chain. A session's chain
    # is of brains now, so that one went; but `triage_ai` and `triage_backup_ai` still spell a
    # brain as `cli:<agent>` - the classifier is built from an agent ROW (make_cli_llm) - so two
    # settings can still name two profiles backed by one executable, and trying claude twice is
    # not failover: it repeats the same paid failure. It can go when the brain settings name
    # brains, which is a change beyond the 2026-09-16 spec. Still true on 2026-10-25: brain VALUES
    # became connection keys, but make_cli_llm resolves `cli:<x>` through an agent row, and an
    # install saved before then still holds a profile name here - so the router keeps it.
    picks, identities = [], set()
    for candidate in [primary, *backups]:
        identity = candidate
        if candidate.startswith('cli:'):
            from . import agents as hub_agents
            row = hub_agents.agent_row(store, candidate[4:])
            try: prof = json.loads((row or {}).get('Config') or '{}')
            except ValueError: prof = {}
            identity = f"cli:{hub_agents.cli_of(prof, candidate[4:])}"
        if identity not in identities:
            picks.append(candidate); identities.add(identity)

    from . import origin as origin_mod

    def one(candidate, first=False):
        # the conversation - its resume id and its live process - belongs to the FIRST brain only; a failover
        # brain starts its own
        chosen_model, chosen_resume, chosen_keep = (model, resume, keep) if first else (None, None, None)
        if candidate.startswith('cli:'):
            try:
                return _Cooling(store, candidate, make_cli_llm(store, candidate[4:], chosen_model, trace=trace, cancel=cancel,
                                    resume=chosen_resume, cli_tools=cli_tools, extra_env=extra_env,
                                    research=research, gear=gear, keep=chosen_keep, task_id=task_id, hold_sid=hold_sid))
            # a BACKUP that cannot run a stranger's task is no backup for it; the first brain's refusal is the answer
            except origin_mod.RefusedForStranger:
                if first: raise
                return None
            # ...nor is a backup with no CLI to run on (agents.NoAI)
            except hub_agents.NoAI:
                if first: raise
                return None
        want = candidate[10:] if candidate.startswith('connector:') else None
        want_id = int(want) if want and want.isdigit() else None
        from .agents import PICKED_ONLY
        for c in store.list_connectors():
            # a local model server (ollama) is the one brain that needs no key to be real
            ready = c['Active'] and (c['HasSecret'] or c['Type'] == 'ollama')
            selected = (c['Type'] not in PICKED_ONLY) if not want else (c['ConnectorId'] == want_id if want_id is not None else c['Type'] == want)
            if c['Type'] in AI_TYPES and ready and selected:
                full = store.get_connector(c['ConnectorId'], with_secret=True)
                config = {**json.loads(full.get('ConfigJson') or '{}'), '_cid': full['ConnectorId']}   # a rotated sign-in token is saved back to its card
                # an API key's strong and light gears are the card's own strong_model / light_model, swapped in for the call (blank:
                # no such tier) - into the box its requests name, Azure's deployment (firstrun.TIER_BOX)
                box, tier = ('deployment' if full['Type'] == 'azure_openai' else 'model'), {'strong': 'strong_model', 'light': 'light_model'}.get(gear)
                if tier and not chosen_model and str(config.get(tier) or '').strip(): config = {**config, box: str(config[tier]).strip()}
                if chosen_model: config = {**config, 'model': chosen_model}
                return _Cooling(store, candidate, make_llm(full['Type'], config, full.get('Secret')))
        return None

    brains = [(candidate, one(candidate, i == 0)) for i, candidate in enumerate(picks)]
    brains = [(candidate, brain) for candidate, brain in brains if brain]
    if not brains: return None
    if len(brains) == 1 and brains[0][0] == primary: return brains[0][1]

    def failover(system, user, **kwargs):
        from .agents import availability_failure
        last = None
        for i, (candidate, brain) in enumerate(brains):
            try:
                # A backup has no access to the primary CLI's native conversation.
                context = fallback_user if candidate != primary and fallback_user is not None else user
                # ...and a schema is dropped for the brain that cannot carry one - per brain, so a
                # CLI backup does not take the schema away from the API brain behind it
                kw = {k: v for k, v in kwargs.items()
                      if not (k == 'want' and not getattr(brain, 'takes_want', False))
                      and not (k == 'web' and not getattr(brain, 'takes_web', False))}
                out = brain(system, context, **kw)
                failover.last_pick = candidate
                failover.session_id = getattr(brain, 'session_id', None)
                if candidate != primary and failover.route:
                    from . import brainroute
                    brainroute.outcome(*failover.route, f'fallback:{candidate}')
                return out
            except Exception as e:
                last = e
                if i == len(brains) - 1 or not availability_failure(e): raise
                if trace: trace('progress', 'fallback',
                                f'{candidate or "automatic AI"} is unavailable; trying {brains[i + 1][0]}')
        raise last
    failover.last_pick, failover.session_id = primary, resume
    failover.is_failover, failover.route = True, None     # build_llm hands it its route row, for a backup to be written on
    failover.takes_want = True          # it forwards one to each brain that can carry it, and drops it for the rest
    failover.takes_web = any(getattr(b, 'takes_web', False) for _, b in brains)
    # a prompt that says lookups exist is written before the answering brain is known: every brain of the chain must have them
    failover.looks_up = all(getattr(b, 'looks_up', getattr(b, 'takes_web', False)) for _, b in brains)
    # a tool loop runs on the primary alone: a backup's own tools and conversation are not this one's (apiagent.py)
    failover.chat = getattr(brains[0][1], 'chat', None) if brains[0][0] == primary else None
    return failover


# A cloud brain answers 500 for reasons that have nothing to do with what you asked, and every
# caller here read the first answer as the verdict. On 2026-09-15 one Azure endpoint failed from
# 01:55 to 04:25 and triage filed five messages unjudged, then failed again at 07:28 and the
# Morning digest and Process Error Check went out carrying '(AI summary failed: azure_openai
# error 500)' where their summary belonged. A scheduled report gets no second chance, so the blip
# is ridden out here, in the one place every cloud brain passes through.
RETRY_STATUS = (429, 500, 502, 503, 504)   # the ENDPOINT's problem; a 4xx is the request's own
RETRY_TRIES = 3                            # attempts per call - bounded: a poll thread waits on this
RETRY_WAIT = (1, 4)                        # seconds before attempt 2, then before attempt 3
RETRY_WAIT_MAX = 30                        # a longer Retry-After is an outage, not a pause
# a reasoning deployment on a report's prompt answered past 60s, and every such report failed "Read timed out" (2026-10-16)
CONNECT_TIMEOUT, READ_TIMEOUT = 15, 180


class JsonAnswer(NamedTuple):
    """What the model said: the parsed object (None when it was not JSON), the text it actually
    sent - which the Triage tab shows when a verdict cannot be read - and why parsing failed."""
    data: dict
    raw: str
    error: str


def ask_json(brain, system: str, user: str, want: dict = None, need=(), **kw) -> JsonAnswer:
    """Ask for a JSON object of a known shape, and get one - or get back what the model did say.

    Three layers, because no single one reaches every brain (TQ-0665):
      - `want` is a JSON schema, handed to the provider when the provider can enforce it
        (takes_want is True). That is the only layer the model cannot talk its way out of.
      - `need` names the keys the caller cannot do without, and is asked for a second time ONLY
        of a brain that has said it cannot carry a schema (takes_want is False - a CLI, which is
        a prompt in and text out). A brain that says nothing either way is left alone: a second
        call is the owner's money, and it is worth spending only where we know the first one had
        no schema behind it. Where the provider enforced the shape, a missing key is the model's
        considered answer and asking again buys nothing.
      - What comes back is parsed here, once, so a caller never re-implements the fence-stripping.

    Never more than one retry: the caller's fallback is what a missing key has always meant, and a
    model that ignored the shape twice will ignore it a third time at the owner's expense.
    """
    def ask(text):
        raw = str(brain(system, text, **kw) or '')
        try: return JsonAnswer(json_of(raw), raw, '')
        except ValueError: return JsonAnswer(None, raw, unreadable(raw))

    carries = getattr(brain, 'takes_want', None)
    if want is not None and carries: kw['want'] = want
    # `false` and 0 are answers: reading them as left out asked every "no" a second time, and the second time it said yes
    def blank(v): return v is None or (not v and not isinstance(v, (bool, int, float)))
    def short(a): return [k for k in need if blank((a.data or {}).get(k))] if carries is False else []
    first = ask(user)
    if first.data is not None and not short(first): return _stepped(brain, system, user, want, need, kw, first)
    again = (f"\n\nYour last answer left out: {', '.join(short(first))}. Answer the whole JSON object "
             'again, including those.' if first.data is not None
             else '\n\nAnswer with the JSON object only - no prose, no code fence.')
    second = ask(user + again)
    out = second if second.data is not None and not short(second) else (second if second.data is not None else first)
    return _stepped(brain, system, user, want, need, kw, out)


def remembered(store, key: str, words, ask):
    """SAME WORDS, SAME ANSWER: `ask()`'s answer, or the one kept under the setting `key` when `words` are what it was last asked with -
    then nothing is asked. One answer per key, the last one, so nothing grows; an answer of None (the model did not answer) is never
    kept, and is asked again. For a question a clock asks - never one the owner asks again on purpose (a redraft)."""
    h = hashlib.sha1('\0'.join(map(str, words)).encode('utf-8', 'replace')).hexdigest()
    try: had = json.loads(store.get_setting(key) or '{}')
    except ValueError: had = {}
    if isinstance(had, dict) and had.get('h') == h and 'out' in had: return had['out']
    out = ask()
    if out is not None: store.set_setting(key, json.dumps({'h': h, 'out': out}), 'router')
    return out


_FENCE = re.compile(r'```[a-zA-Z]*\s*\n?(.*?)```', re.S)


def json_of(raw: str) -> dict:
    """The JSON object in a model's answer, however it came wrapped: bare, in a code fence (any language tag, prose around it), or
    after a sentence of its own - a proxy in front of another model hands back all three. ValueError when there is none."""
    s = str(raw or '').strip().lstrip('﻿')
    for t in (s, *(m.strip() for m in _FENCE.findall(s))):
        try: o = json.loads(t)
        except ValueError: continue
        if isinstance(o, dict): return o
        raise ValueError(f'a JSON {type(o).__name__}, not an object')
    if (i := s.find('{')) >= 0:
        o, _end = json.JSONDecoder().raw_decode(s[i:])
        if isinstance(o, dict): return o
    raise ValueError('no JSON object')


def unreadable(raw: str) -> str:
    """What came back instead of a JSON object, in words a person can act on - "JSONDecodeError: Expecting value" was all a
    first run's failed test email said (2026-11-03)."""
    s = ' '.join(str(raw or '').split())
    if not s: return 'the AI sent back an empty answer'
    q = f'"{s[:160]}{"…" if len(s) > 160 else ""}"'
    if s.lower().startswith(('<!doctype', '<html')): return f'the AI sent back a web page, not an answer: {q}'
    if s.startswith('['): return f'the AI sent back a list, not the JSON object it was asked for: {q}'
    if '{' not in s: return f'the AI answered in plain words instead of the JSON it was asked for: {q}'
    return f'the AI sent back JSON that was cut off or broken: {q}'


def _stepped(brain, system, user, want, need, kw, out: JsonAnswer) -> JsonAnswer:
    """An answer still unreadable after its own retry, or one the model said it was not sure of, is asked ONCE of a strong model -
    where the owner turned that on (brainroute's 'unsure' rule, Auto mode). These jobs only read and write, so asking again cannot
    act twice; a strong answer that is no better leaves the first one standing."""
    if getattr(brain, 'is_step_up', False) is not True: return out      # said out loud: a stand-in brain answers any attribute
    up = brain.step_up
    bad = out.data is None or any(not out.data.get(k) for k in need)
    unsure = not bad and out.data.get('sure') is False
    if not (bad or unsure): return out
    strong = up('unsure' if unsure else 'unreadable')
    if strong is None: return out
    again = ask_json(strong, system, user, want=want, need=need, **{k: v for k, v in kw.items() if k != 'want'})
    return again if again.data is not None and not any(not again.data.get(k) for k in need) else out


def retry_wait(last, attempt: int) -> float:
    """Our own spacing, unless the endpoint said when to come back - a 429 always does."""
    w = RETRY_WAIT[min(attempt, len(RETRY_WAIT)) - 1]
    after = str((getattr(last, 'headers', None) or {}).get('Retry-After') or '').strip()
    return max(w, min(int(after), RETRY_WAIT_MAX)) if after.isdigit() else w


def post_retrying(url, headers, body, timeout):
    """One completion call, tried again while the failure is the endpoint's rather than the
    request's. Returns the last response for the caller to read; a connection that never comes
    back raises its own error, as it always did."""
    last = None
    for attempt in range(RETRY_TRIES):
        if attempt: sleep(retry_wait(last, attempt))
        try: r = requests.post(url, headers=headers, json=body, timeout=timeout)
        # an answer that is slow is not a blip: asking again queues the same work, and tripled the wait (2026-10-16)
        except requests.ReadTimeout: raise
        except requests.RequestException as e: last = e; continue
        if r.status_code not in RETRY_STATUS: return r
        last = r
    if isinstance(last, Exception): raise last
    return last


def tried(r) -> str:
    """So the row the owner reads says we rode it out and it stayed down, not that we gave up."""
    return f' after {RETRY_TRIES} tries' if r.status_code in RETRY_STATUS else ''


def _chatgpt_llm(cfg: dict, refresh_token: str):
    """The owner's ChatGPT plan as a brain. `key` is the sign-in's refresh token, not an API key; the model is the card's,
    else the first one the plan lists. Images and web search go along when the plan's model accepts them."""
    from . import chatgptauth as ca
    if not refresh_token: raise RuntimeError('not signed in - click "Sign in with ChatGPT" on the ChatGPT card')
    picked = {}
    def llm(system, user, max_tokens=MAX_TOKENS, images=None, want=None, web=False):
        tok = ca.access_token(cfg, refresh_token); model_of(tok)
        # images and web search are both in the plan preview "when the model accepts them" - asked for, and dropped
        # one at a time only when the plan answers that it cannot serve them
        try: return ca.complete(tok, picked['model'], system, user, max_tokens, want, images=images, web=web)
        except ca.Unsupported:
            if web:
                try: return ca.complete(tok, picked['model'], system, user, max_tokens, want, images=images)
                except ca.Unsupported:
                    if not images: raise
            if not images: raise
            note = f'[{len(images)} attached image(s) not shown - this model reads text only]\n\n{user}'
            return ca.complete(tok, picked['model'], system, note, max_tokens, want)
    def model_of(tok):
        if 'model' not in picked:
            listed = [s for s, _ in ca.models(tok)] if not cfg.get('model') else []
            picked['model'] = cfg.get('model') or (listed[0] if listed else '')
            if not picked['model']: raise RuntimeError('the ChatGPT plan lists no models this account can use')
        return picked['model']
    # A TOOL LOOP ON THE PLAN (apiagent.py) through its Responses API, the conversation carried in the OpenAI chat shape like every card
    def chat(messages, tools, max_tokens=MAX_TOKENS, tool_choice=None, **_):
        tok = ca.access_token(cfg, refresh_token)
        system, items, fns = to_responses(messages, tools)
        try: return from_responses(ca.respond(tok, model_of(tok), system, items, fns, **({'tool_choice': tool_choice} if tool_choice else {})))
        except ca.Unsupported as e: raise RuntimeError(f'chatgpt error 400: {e}') from e
    def search(question, max_tokens=2000):
        tok = ca.access_token(cfg, refresh_token)
        return ca.complete(tok, model_of(tok), SEARCH_ASK, question, max_tokens, web=True)
    llm.chat, llm.search = chat, search
    llm.takes_want = llm.takes_web = True
    return llm


# a model that cannot answer a prompt is no brain: Azure lists an embedding deployment beside the chat ones, and the picker offered it
_NOT_A_BRAIN = re.compile(r'embed|whisper|tts|transcri|dall-e|image|moderation|realtime|audio', re.I)


def list_models(t, cfg: dict, key: str) -> list:
    return [m for m in _list_models(t, cfg, key) if not _NOT_A_BRAIN.search(m)]


MODELS_TTL, _models_cache = 600, {}      # a provider's list, per connector, for ten minutes - a cache, not a setting


def connector_models(store, cid: int) -> dict | None:
    """{'models': [...]} this connector's own key can call, cached; a failed read is {'models': [], 'error': ...} so every picker
    falls back to its typed box. None for no such AI connector. The one list the AI cards, the workflow editor and the strong
    box offer - no model id is typed into the app for them (the router, 2026-10-25)."""
    import time
    hit = _models_cache.get(cid)
    if hit and time.time() - hit[0] < MODELS_TTL: return hit[1]
    c = store.get_connector(int(cid), with_secret=True)
    if not c or c['Type'] not in AI_TYPES: return None
    try: conf = json.loads(c.get('ConfigJson') or '{}')
    except ValueError: conf = {}
    try: out = {'models': list_models(c['Type'], conf, c.get('Secret') or '')}
    except Exception as e: return {'models': [], 'error': str(e)[:200]}
    _models_cache[cid] = (time.time(), out)
    return out


def _list_models(t, cfg: dict, key: str) -> list:
    """The model ids this key can actually call, from the provider's own list endpoint - so the picker never offers a name the
    account does not have. Azure names what you DEPLOYED (that is what a request carries), so it is its deployments, or the resource's base models when the
    deployments list is closed to this key. RAISES on a provider that answers with an error: an empty list would read as "none exist"."""
    if t == 'chatgpt':
        from . import chatgptauth as ca
        return [s for s, _ in ca.models(ca.access_token(cfg, key))] if key else []
    if t == 'anthropic': url, h, k = 'https://api.anthropic.com/v1/models?limit=100', {'x-api-key': key, 'anthropic-version': '2023-06-01'}, 'data'
    elif t == 'azure_openai':
        ep, ids = (cfg.get('endpoint') or '').rstrip('/'), []
        if not ep: return []
        for u, k in ((f'{ep}/openai/deployments?api-version=2023-03-15-preview', 'data'), (f'{ep}/openai/v1/models', 'data')):
            try: r = requests.get(u, headers={'api-key': key}, timeout=15)
            except requests.RequestException: continue
            if r.status_code == 200: ids += [m.get('id') for m in (r.json().get(k) or []) if m.get('id')]
            if ids: break          # deployments are what a request can name; the base-model catalogue is only the fallback
        if not ids: raise RuntimeError('Azure listed no deployments or models for this key')
        return list(dict.fromkeys(ids))
    else:
        base = {'openai': 'https://api.openai.com/v1', 'openrouter': 'https://openrouter.ai/api/v1', 'meta': 'https://api.meta.ai/v1',
                'ollama': 'http://127.0.0.1:11434/v1'}.get(t) or (OPENAI_COMPATIBLE.get(t) or ('',))[0]
        base = gateway_base(cfg) if t == 'hipaa_ai' else (cfg.get('base_url') or base).rstrip('/')
        if t == 'ollama' and base.endswith('11434'): base += '/v1'
        if not base: return []
        url, h, k = f'{base}/models', ({'Authorization': f'Bearer {key}'} if key else {}), 'data'
    r = requests.get(url, headers=h, timeout=GATEWAY_WAIT if t == 'hipaa_ai' else 15)
    if r.status_code != 200: raise RuntimeError(f'{t} answered {r.status_code}: {str(r.text)[:160]}')
    return sorted({m.get('id') for m in (r.json().get(k) or []) if m.get('id')})


# AN OPENAI-COMPATIBLE PROXY IN FRONT OF ANOTHER MODEL (an access-code card, any proxy that routes to several models) speaks the schema loosely: it
# may refuse json_schema with a 422 or a 500 of its own rather than a 400, hand `content` back as a list of parts, or turn the schema
# into a forced tool call and answer in its arguments. A first run's test email failed on that as "wrong format" (2026-11-03).
# EFFORT ON AN API CARD (the owner, 2026-11-06: "if it's api or something that only has one model use effort instead if they support
# it"). The router spells it the way a CLI pick does - 'gpt-5@high', '@low' for the card's own model - and make_llm splits it off:
# Anthropic takes output_config.effort, OpenAI and Azure OpenAI reasoning_effort (the Responses API reasoning.effort). A model that
# turns it down is asked once more without it, and is not offered it again in this process. Every other provider never sees it.
# ...and the HIPAA AI card: its gateway (LiteLLM) carries reasoning_effort on to the Gemini and Claude models behind it (2026-11-06)
EFFORT_TAKERS = ('anthropic', 'openai', 'azure_openai', 'hipaa_ai')
EFFORT_WORDS = ('minimal', 'low', 'medium', 'high', 'xhigh', 'max')
_NO_EFFORT = set()         # (type, endpoint, model) that refused an effort - asked plainly from then on
_EFFORT_REFUSED = re.compile(r'reasoning_effort|reasoning\.effort|\beffort\b|output_config|thinking', re.I)
# A GATEWAY TURNS AN EFFORT INTO A THINKING BUDGET for a Claude model behind it (LiteLLM: low 1024, high 4096 tokens), and Claude
# refuses a budget that is not under max_tokens, or thinking beside the forced tool a json_schema becomes - in words that never say
# "effort". THIS call is asked again without it; the model is not written off, since a call with more room takes it.
_THINK_REFUSED = re.compile(r'budget_tokens|thinking may not be enabled', re.I)


def split_effort(model: str) -> tuple:
    "'gpt-5@high' -> ('gpt-5', 'high'). Only a known level is split off: a Vertex id like 'claude-x@20251101' stays whole."
    m, at, e = str(model or '').rpartition('@')
    return (m, e) if at and e in EFFORT_WORDS else (str(model or ''), '')


def _no_effort(key, why) -> None:
    from loguru import logger
    _NO_EFFORT.add(key); logger.info(f'{key[0]}: {key[2] or "this model"} takes no effort setting, asking without it - {str(why)[:200]}')


_FORMAT_FROM = {}          # (url, model) -> the first of json_schema, json_object, prompt-only that the endpoint has not refused
_FORMAT_WORDS = re.compile(r'response_format|json_schema|json_object|structured output|response.?schema|strict', re.I)


def refused_format(r) -> bool:
    "Did the endpoint turn the response_format down, rather than the call? A 400-class answer, or any error that names the format."
    return r.status_code in (400, 415, 422) or bool(_FORMAT_WORDS.search(str(getattr(r, 'text', '') or '')))


def said_text(msg: dict) -> str:
    "A chat-completions message as text: its content, the text of its parts when content is a list, else a tool call's arguments."
    c = msg.get('content')
    if isinstance(c, list): c = ''.join(p.get('text') or '' if isinstance(p, dict) else str(p) for p in c)
    if str(c or '').strip(): return str(c)
    calls = msg.get('tool_calls') or ([{'function': msg['function_call']}] if msg.get('function_call') else [])
    return next((str((x.get('function') or {}).get('arguments') or '') for x in calls if (x.get('function') or {}).get('arguments')), '')


# THE STABLE PART OF A CALL IS READ FROM THE PROVIDER'S CACHE (the owner, 2026-11-10: "32 million tokens? sounds very expensive" ... "keep the
# triage context cached and then just the new info should query it"). Triage's guide is the same on every mail, an agent's system, tools and
# conversation the same on every step. A prompt builder says which part is stable with stable(): its blocks, least often changing first, then
# what is this call's own. Each card turns that into what its provider needs:
# - the Messages API caches only what is marked (cache_control on each stable block; '1h' for a guide that stays the same for hours - a write
#   costs 2x then, a read 0.1x; the default 5 minutes for an agent's steps seconds apart);
# - OpenAI, and Gemini 2.5+ behind a gateway, cache a repeated prefix by themselves (OpenAI from 1,024 tokens; Gemini Flash from 4,096) - there
#   the order alone hits. A LiteLLM gateway also takes cache_control and makes a Vertex cachedContent of the marked part, but on Gemini that
#   turns the free implicit cache off for it and bills storage, so it is the card's choice (`cache: explicit` in its settings), not the default;
# - a card that refuses the marker (a 400 naming it) is asked again without it, and never marked again (_NO_CACHE).
# Whatever reads it as text - a CLI's prompt file, a log - reads the same words: Stable is a str.
EPHEMERAL, CACHE_FROM = {'type': 'ephemeral'}, 2_000      # characters: under ~512 tokens no provider caches at all
_NO_CACHE = set()          # (type, endpoint, model) that refused a cache marker
# how each card's provider caches: 'explicit' takes the marker; 'implicit' caches a repeated prefix by itself (OpenAI-style APIs; Gemini behind a
# gateway - its newest Flash models cache implicitly only, at a 90% discount, from ~4-6K tokens, for up to a day). The Messages API is marked in
# make_llm's own branch. A card's `cache` setting overrides its type's; a type not listed is implicit
CACHE_MARKS = {'anthropic': 'explicit', 'hipaa_ai': 'implicit', 'vertex_ai': 'implicit', 'gemini': 'implicit', 'openai': 'implicit',
               'azure_openai': 'implicit', 'openrouter': 'implicit', 'deepseek': 'implicit'}
_CACHE_REFUSED = re.compile(r'cache_control|cached_?content|cache', re.I)


class Stable(str):
    "A system prompt as its stable blocks then this call's own `rest` - the same words as ''.join(blocks) + rest wherever it is read as text."
    def __new__(cls, blocks, rest: str = '', ttl: str = None):
        bs = [str(b) for b in blocks if b]
        s = super().__new__(cls, ''.join(bs) + str(rest or '')); s.blocks, s.rest, s.ttl = bs, str(rest or ''), ttl
        return s
    def map(self, f): return Stable([f(b) for b in self.blocks], f(self.rest) if self.rest else '', self.ttl)


def stable(*blocks, rest: str = '', ttl: str = None) -> Stable: return Stable(blocks, rest, ttl)


def blocks(system, marks: int = 4, ttl: bool = True, seconds: bool = False):
    """`system` as content blocks with cache_control on its stable blocks (the last `marks` of them, each long enough to cache); a plain
    string long enough is one marked block; None when nothing is worth marking. `seconds`: the TTL as LiteLLM's Gemini wants it ('3600s')."""
    parts = getattr(system, 'blocks', None)
    if parts is None: parts, rest, life = ([str(system)], '', None) if len(system or '') >= CACHE_FROM else (None, '', None)
    else: rest, life = system.rest, system.ttl
    if not parts: return None
    life = life and ttl and ({'1h': '3600s', '5m': '300s'}.get(life, life) if seconds else life)
    mark = {**EPHEMERAL, **({'ttl': life} if life else {})}
    out = [{'type': 'text', 'text': b, **({'cache_control': mark} if k >= len(parts) - marks and len(''.join(parts[:k + 1])) >= CACHE_FROM else {})}
           for k, b in enumerate(parts)]
    return out + ([{'type': 'text', 'text': rest}] if rest.strip() else [])


def cached(system, marks: int = 4): return blocks(system, marks) or str(system)


def make_llm(t, cfg: dict, key: str):
    m, effort = split_effort(cfg.get('model'))
    if effort: cfg = {**cfg, 'model': m}
    if t not in EFFORT_TAKERS: effort = ''
    if t == 'chatgpt': return _chatgpt_llm(cfg, key)
    if not key and t != 'ollama': raise RuntimeError('no API key saved - paste one under Credentials')
    if t == 'anthropic':
        import anthropic
        cli = anthropic.Anthropic(api_key=key)
        model = cfg.get('model') or PROVIDER_DEFAULT['anthropic']
        ek = ('anthropic', '', model)
        def asked(**kw):
            if effort and ek not in _NO_EFFORT:
                try: return cli.messages.create(**kw, output_config={'effort': effort})
                except anthropic.BadRequestError as e:
                    if not _EFFORT_REFUSED.search(str(e)): raise
                    _no_effort(ek, e)
            return cli.messages.create(**kw)
        def ask(**kw):
            r = asked(**kw); aiusage.anthropic(r); return r       # a paused web turn's every leg is counted
        def llm(system, user, max_tokens=MAX_TOKENS, images=None, want=None, web=False):
            # images FIRST: every provider reads a picture better when the question follows it
            content = ([{'type': 'image', 'source': {'type': 'base64', 'media_type': ct, 'data': b64}}
                        for ct, b64 in (images or [])] + [{'type': 'text', 'text': user}]) if images else user
            if web and not want:
                got = _anthropic_web(ask, model, system, content, max_tokens)
                if got is not None: return got
            # `want` is a schema the answer MUST fit. Anthropic has no response_format; a tool the
            # model is forced to call is the same thing - the tool's input schema is the answer's,
            # and what comes back is the tool call's arguments rather than prose.
            forced = ({'tools': [{'name': want.get('name') or 'answer', 'description': 'Answer with these fields.',
                                  'input_schema': want.get('schema') or want}],
                       'tool_choice': {'type': 'tool', 'name': want.get('name') or 'answer'}} if want else {})
            r = ask(model=model, max_tokens=max_tokens, system=cached(system), messages=[{'role': 'user', 'content': content}], **forced)
            if r.stop_reason == 'refusal': raise RuntimeError('model refused the request')
            if want:
                call = next((b for b in r.content if b.type == 'tool_use'), None)
                if call is not None: return json.dumps(call.input)
            return next((b.text for b in r.content if b.type == 'text'), '')
        # ONE STEP OF A TOOL LOOP (apiagent.py) on the Messages API: the conversation and tools arrive in the OpenAI shape every other
        # card speaks and go back in it, so the loop, its gate and its tools are the one road (to_anthropic / from_anthropic)
        def chat(messages, tools, max_tokens=MAX_TOKENS, tool_choice=None, **_):
            system, msgs, fns = to_anthropic(messages, tools)
            if fns: fns[-1] = {**fns[-1], 'cache_control': EPHEMERAL}
            if msgs and msgs[-1]['content']: msgs[-1]['content'][-1] = {**msgs[-1]['content'][-1], 'cache_control': EPHEMERAL}
            kw = {'tools': fns, **({'tool_choice': {'type': tool_choice}} if tool_choice in ('none', 'auto', 'any') else {})} if fns else {}
            try: r = ask(model=model, max_tokens=max_tokens, messages=msgs, **({'system': cached(system, marks=2)} if system else {}), **kw)
            except anthropic.BadRequestError as e: raise RuntimeError(f'anthropic error 400: {str(e)[:300]}') from e
            if r.stop_reason == 'refusal': raise RuntimeError('model refused the request')
            return from_anthropic(r.content)
        # ...and its OWN web search: Anthropic's server tools, on a call of its own as on every card (the CLI's WebSearch)
        def search(question, max_tokens=2000):
            got = _anthropic_web(ask, model, SEARCH_ASK, [{'type': 'text', 'text': question}], max_tokens)
            if not (got or '').strip(): raise RuntimeError('anthropic: web search is not available on this model')
            return got
        llm.chat, llm.search = chat, search
        llm.takes_want = llm.takes_web = True
        return llm
    if t == 'openai':
        urls = ['https://api.openai.com/v1/chat/completions']
        headers, model = {'Authorization': f'Bearer {key}'}, cfg.get('model') or PROVIDER_DEFAULT['openai']
    elif t == 'openrouter':
        # one key, the whole catalog behind the OpenAI schema - open-weights models included.
        # Model strings are OpenRouter's names ('meta-llama/llama-3.3-70b-instruct', ...);
        # 'openrouter/auto' lets their router pick, so an empty model box still works.
        urls = ['https://openrouter.ai/api/v1/chat/completions']
        headers, model = {'Authorization': f'Bearer {key}', 'X-Title': 'Taskuary'}, cfg.get('model') or PROVIDER_DEFAULT['openrouter']
    elif t == 'meta':
        # Meta Model API - Muse Spark behind the OpenAI chat-completions schema, so it needs no
        # branch of its own beyond the base url. This is the road to Muse Spark on a machine that
        # cannot run the muse CLI at all (its installer is posix-only), and it is a triage brain
        # only: the CODING side is the CLI. base_url is overridable for the same reason ollama's
        # is - the surface is standard, so a gateway or proxy in front of it still speaks it.
        # muse-spark-1.2-contributor is ~12x cheaper AND trains Meta's products on what you send;
        # the default stays on the private tier, and the card says so rather than deciding for you.
        base = (cfg.get('base_url') or 'https://api.meta.ai/v1').rstrip('/')
        urls = [f'{base}/chat/completions']
        headers, model = {'Authorization': f'Bearer {key}'}, cfg.get('model') or PROVIDER_DEFAULT['meta']
    elif t == 'ollama':
        # a LOCAL server speaking the OpenAI surface. Ollama's port out of the box, but base_url
        # reaches LM Studio (:1234), llama.cpp, vLLM - anything /v1-compatible - so open-source
        # models triage your mail without a byte leaving the machine. No key unless the server
        # demands one; the model must be named because only `ollama list` knows what's pulled.
        base = (cfg.get('base_url') or 'http://127.0.0.1:11434').rstrip('/')
        if not cfg.get('model'): raise RuntimeError('a local brain needs its model named - `ollama list` shows what is installed')
        urls, model = [f'{base}/v1/chat/completions'], cfg['model']
        headers = {'Authorization': f'Bearer {key}'} if key else {}
    elif t in OPENAI_COMPATIBLE:
        default_base, default_model = OPENAI_COMPATIBLE[t]
        base = gateway_base(cfg) if t == 'hipaa_ai' else (cfg.get('base_url') or default_base).rstrip('/')
        if not base: raise RuntimeError('no gateway address on its card - add the one you were sent with your access code')
        urls = [f'{base}/chat/completions']
        headers, model = {'Authorization': f'Bearer {key}'}, cfg.get('model') or default_model
    elif t == 'vertex_ai':
        # Google's Agent Platform (Vertex AI): the same chat completions, under a project and a location. Its API key rides
        # x-goog-api-key - Bearer there wants an OAuth token - and its models are named by publisher (google/, meta/ ...)
        if not cfg.get('project'): raise RuntimeError('vertex_ai needs its Google Cloud project id')
        loc = (cfg.get('location') or 'global').strip()
        host = 'aiplatform.googleapis.com' if loc == 'global' else f'{loc}-aiplatform.googleapis.com'
        urls = [f"https://{host}/v1/projects/{cfg['project'].strip()}/locations/{loc}/endpoints/openapi/chat/completions"]
        model = (cfg.get('model') or VERTEX_DEFAULT).strip()
        headers, model = {'x-goog-api-key': key}, model if '/' in model else f'google/{model}'
    elif t == 'azure_openai':
        ep = (cfg.get('endpoint') or '').rstrip('/')
        if not (ep and cfg.get('deployment')): raise RuntimeError('azure_openai needs endpoint + deployment')
        # Azure's v1 surface first (no api-version, OpenAI-compatible, all params work);
        # legacy deployments URL as fallback for resources without it. An explicit
        # api_version in the config skips straight to legacy with that version.
        legacy = f"{ep}/openai/deployments/{cfg['deployment']}/chat/completions?api-version={cfg.get('api_version') or '2024-12-01-preview'}"
        urls = [legacy] if cfg.get('api_version') else [f'{ep}/openai/v1/chat/completions', legacy]
        headers, model = {'api-key': key}, cfg['deployment']
    else:
        raise RuntimeError(f'unknown AI connector type: {t}')
    ek = (t, urls[0], model)
    marked = lambda system: ((cfg.get('cache') or CACHE_MARKS.get(t, 'implicit')) == 'explicit' and ek not in _NO_CACHE
                             and blocks(system, seconds=True)) or str(system)
    def unmarked(r, msgs) -> bool:
        "A refused cache marker (a 400 naming it): taken off this request and never put on this card again."
        if r.status_code not in (400, 422) or not msgs or isinstance(msgs[0].get('content'), str) or msgs[0].get('role') != 'system': return False
        if not _CACHE_REFUSED.search(r.text or ''): return False
        _NO_CACHE.add(ek); msgs[0] = {**msgs[0], 'content': ''.join(b.get('text') or '' for b in msgs[0]['content'])}
        from loguru import logger
        logger.info(f'{t}: the card refused a cache marker - asked without one from now on'); return True

    def llm(system, user, max_tokens=MAX_TOKENS, images=None, want=None, web=False):
        if web and not want and t in ('openai', 'azure_openai'):
            got = _responses_web(t, cfg, headers, model, system, user, images, max_tokens, effort if ek not in _NO_EFFORT else '')
            if got is not None: return got
        # three independent compat axes: newer models reject max_tokens ("use
        # max_completion_tokens"), older Azure api-versions reject max_completion_tokens,
        # older Azure resources 404 the v1 url - and not every model behind this one schema can
        # be handed a response_format. Walk the grid until one works.
        content = ([{'type': 'image_url', 'image_url': {'url': f'data:{ct};base64,{vision_safe(ct, b64)}'}}
                    for ct, b64 in (images or [])] + [{'type': 'text', 'text': user}]) if images else user
        # AN EMPTY TURN IS NO TURN: Gemini and Claude behind a gateway both refuse one ("contents.parts must not be empty", "text content
        # blocks must be non-empty") where OpenAI let it by - a blank system is left out, and a blank ask is the system's words
        if not str(user or '').strip() and not images: system, content = '', system
        msgs = ([{'role': 'system', 'content': marked(system)}] if str(system or '').strip() else []) + [{'role': 'user', 'content': content}]
        last = None

        def once(fmt):
            """The url x token-parameter grid with this response_format. The answer, or None when
            the endpoint refused the FORMAT and the same question is worth asking without it."""
            nonlocal last
            for url in urls:
                for tok_param in ('max_completion_tokens', 'max_tokens'):
                    body = {'messages': msgs, tok_param: max_tokens, **({'model': model} if model else {}),
                            **({'response_format': fmt} if fmt else {}), **({'reasoning_effort': effort} if effort and ek not in _NO_EFFORT else {})}
                    # a local model may spend its first call loading weights off disk, a reasoning deployment its time on a long
                    # prompt - room to answer, and a quick give-up on an endpoint that is not there
                    r = post_retrying(url, headers, body, (CONNECT_TIMEOUT, READ_TIMEOUT))
                    if unmarked(r, msgs): r = post_retrying(url, headers, body, (CONNECT_TIMEOUT, READ_TIMEOUT))
                    # a spent budget first: it is no refused effort or format, and asking again in another shape only spends a request
                    if budget_spent(r): raise BudgetSpent(BUDGET_LINE.format(name='HIPAA AI' if t == 'hipaa_ai' else t))
                    # ...a proxy may turn it down with a 422 of its own (the gateway in front of another provider's model)
                    said = r.text or ''
                    if r.status_code in (400, 422) and body.pop('reasoning_effort', None) and _EFFORT_REFUSED.search(said):
                        if not _THINK_REFUSED.search(said): _no_effort(ek, said)
                        r = post_retrying(url, headers, body, (CONNECT_TIMEOUT, READ_TIMEOUT))
                    if r.status_code == 200:
                        aiusage.openai(r.json())
                        ch = (r.json().get('choices') or [{}])[0]
                        said = said_text(ch.get('message') or {})
                        if cut_by_thinking(r.json()): _THINKS.add(ek); raise _Empty('length')
                        if said.strip(): return said
                        raise _Empty(ch.get('finish_reason') or 'none given')
                    last = r
                    if r.status_code == 404: break                      # wrong surface -> next url
                    if r.status_code == 400 and images and _IMAGE_REFUSED.search(r.text): raise _ImageRefused(r.text[:300])
                    if r.status_code == 400 and 'max_completion_tokens' in r.text: continue
                    if fmt and refused_format(r): return None           # cannot carry this format -> ask with the next one
                    raise RuntimeError(f'{t} error {r.status_code} at {url.split("?")[0]}{tried(r)}: {r.text[:300]}')
            return None

        # `want` is a JSON schema the answer MUST fit, and the strongest form is worth asking for:
        # a strict schema is obeyed even when the prose contract in the prompt says something
        # narrower (verified against gpt-5.4, TQ-0665). A route that cannot carry it may still take
        # json_object - valid JSON, any shape - and below that the prompt is all there is. Where an
        # endpoint refused a format is remembered, so every mail after the first asks only what it takes.
        fmts = [{'type': 'json_schema', 'json_schema': {**want, 'strict': True}}, {'type': 'json_object'}] if want else []
        where = (urls[0], model)
        if ek in _THINKS: max_tokens = max(max_tokens, ROOM)
        def ask():
            try: return asked()
            except _ImageRefused:
                msgs[-1]['content'] = f'{user}\n\n({len(images)} attached image(s) could not be opened by this AI and were left out.)'
                return asked()
        def asked():
            for i, fmt in enumerate(fmts + [None]):
                if fmt and i < _FORMAT_FROM.get(where, 0): continue
                out = once(fmt)
                if out is not None:
                    if fmt or want: _FORMAT_FROM[where] = i
                    return out
            raise RuntimeError(f'{t} error {last.status_code} at {urls[-1].split("?")[0]}{tried(last)}: {last.text[:300]}')
        # ...and an empty 'stop' is asked once more as it was: Gemini behind the HIPAA AI gateway now and then thinks and writes nothing
        spent = 0
        while True:
            try: return ask()
            except _Empty as e:
                spent += 1
                if str(e) == 'length' and max_tokens < ROOM: max_tokens = ROOM; continue
                if str(e) != 'length' and spent < 3: continue
                if str(e) == 'length':
                    raise RuntimeError(f'{t}: the model ran out of room before answering, even with {ROOM} tokens (finish_reason {e}) - '
                                       f'model {model}; pick a non-thinking model on its card') from None
                raise RuntimeError(f'{t} sent back no answer (finish_reason {e}) - model {model}') from None
    # ONE STEP OF A TOOL LOOP (apiagent.py): the model's message - its words and/or tool_calls - for a whole conversation and the tools
    # it may call, in the OpenAI schema every endpoint here speaks. Without it an API brain was one system + one user message and nothing
    # it could DO: a HIPAA-only install, with no CLI, answered "logging in cannot be done from here" (the owner, 2026-11-09). LiteLLM
    # carries `tools` on to the Gemini and Claude models behind a gateway (verified live on the HIPAA AI card, 2026-11-09).
    def chat(messages, tools, max_tokens=MAX_TOKENS, **extra):
        last = None
        if messages and messages[0].get('role') == 'system': messages = [{**messages[0], 'content': marked(messages[0].get('content') or '')}, *messages[1:]]
        for url in urls:
            for tok_param in ('max_completion_tokens', 'max_tokens'):
                body = {'messages': messages, 'tools': tools, tok_param: max_tokens, **extra, **({'model': model} if model else {}),
                        **({'reasoning_effort': effort} if effort and ek not in _NO_EFFORT else {})}
                r = post_retrying(url, headers, body, (CONNECT_TIMEOUT, READ_TIMEOUT))
                if unmarked(r, messages): body['messages'] = messages; r = post_retrying(url, headers, body, (CONNECT_TIMEOUT, READ_TIMEOUT))
                if budget_spent(r): raise BudgetSpent(BUDGET_LINE.format(name='HIPAA AI' if t == 'hipaa_ai' else t))
                if r.status_code in (400, 422) and body.pop('reasoning_effort', None) and _EFFORT_REFUSED.search(r.text or ''):
                    r = post_retrying(url, headers, body, (CONNECT_TIMEOUT, READ_TIMEOUT))
                if r.status_code == 200:
                    aiusage.openai(r.json())
                    return (r.json().get('choices') or [{}])[0].get('message') or {}
                last = r
                if r.status_code == 404: break
                if r.status_code == 400 and 'max_completion_tokens' in (r.text or ''): continue
                raise RuntimeError(f'{t} error {r.status_code} at {url.split("?")[0]}{tried(r)}: {r.text[:300]}')
        raise RuntimeError(f'{t} error {last.status_code} at {urls[-1].split("?")[0]}{tried(last)}: {last.text[:300]}')
    llm.chat = chat

    # THE MODEL'S OWN WEB SEARCH, through the gateway (the owner, 2026-11-09: "why can't the model itself do web search?"): LiteLLM's
    # web_search_options is Google Search grounding for a Gemini model and Anthropic's web search for a Claude one. Asked on a call of its
    # own - beside function tools it is ignored (Gemini called the other tool, Claude said it could not search; verified live 2026-11-09)
    def search(question, max_tokens=2000):
        # each provider's own search where it has one: OpenAI's and Azure's Responses `web_search` (what a plain question already used,
        # LOOKING THINGS UP below), Google Search grounding on Google's own Gemini API - the gateway's web_search_options otherwise
        if t in ('openai', 'azure_openai'):
            got = _responses_web(t, cfg, headers, model, SEARCH_ASK, question, None, max(max_tokens, 4000), effort if ek not in _NO_EFFORT else '')
            if (got or '').strip(): return got
        if g := _google_url(t, cfg, model): return _google_search(g, headers, question)
        body = {'messages': [{'role': 'user', 'content': f'{SEARCH_ASK} {question}'}],
                'max_tokens': max_tokens, 'web_search_options': {'search_context_size': 'medium'}, **({'model': model} if model else {})}
        r = post_retrying(urls[0], headers, body, (CONNECT_TIMEOUT, READ_TIMEOUT))
        if budget_spent(r): raise BudgetSpent(BUDGET_LINE.format(name='HIPAA AI' if t == 'hipaa_ai' else t))
        if r.status_code != 200: raise RuntimeError(f'{t} error {r.status_code}: {r.text[:300]}')
        aiusage.openai(r.json())
        m = (r.json().get('choices') or [{}])[0].get('message') or {}
        cites = list(dict.fromkeys(str((a.get('url_citation') or a).get('url') or '') for a in m.get('annotations') or [] if isinstance(a, dict)))
        said = said_text(m).strip()
        if not said: raise RuntimeError('the search came back empty')
        return said + ('\n\nSOURCES\n' + '\n'.join(c for c in cites if c) if any(cites) else '')
    # ...only where the card HAS a search of its own: a model asked with an option it ignores answers from memory as if it had looked
    # (groq, mistral, a local model); without one apiagent's web_search goes to a connected search card and says when there is none
    if t in NATIVE_SEARCH: llm.search = search
    llm.takes_want = True
    llm.takes_web = t in ('openai', 'azure_openai')
    return llm


# LOOKING THINGS UP ON AN API BRAIN. Every provider here can search the web itself inside the one call - Anthropic's
# server tools, OpenAI's and Azure's Responses API web_search - and Taskuary used to ask none of them, so a general
# agent on an API key answered "research this vendor" from memory while the same agent on a CLI searched (the owner,
# 2026-09-30: "even plain api can look things up before answering"). Asked only where the job is research - the
# general agent - never for triage, which reads one message and would pay for a search on every mail. A provider,
# model or account that refuses the tool answers the same question without it: None here means "ask it plainly".
# WHAT IT LOOKED UP, for whoever is watching the call (general.send_prompt): an API brain's searches run inside the provider and
# came back as prose only, so its canvas showed nothing between the question and the answer while a CLI's showed every search
# (2026-10-21). The same tool_call/tool_result events a CLI emits, so both read the same.
_WATCH = contextvars.ContextVar('tq_llm_watch', default=None)


@contextmanager
def watching(trace):
    tok = _WATCH.set(trace)
    try: yield
    finally: _WATCH.reset(tok)


def _saw(kind, name, detail):
    t = _WATCH.get()
    if not t: return
    try: t(kind, name, detail)
    except Exception: pass                      # a watcher that fails never fails the answer


SEARCH_ASK = 'Search the web and answer, naming each source with its address:'
# the cards whose model searches the web itself (llm.search): the Responses API's web_search, Google Search grounding, Anthropic's server
# tool, LiteLLM's web_search_options on a gateway (HIPAA AI, OpenRouter), and Perplexity, whose every answer is a search
NATIVE_SEARCH = ('openai', 'azure_openai', 'hipaa_ai', 'openrouter', 'perplexity', 'gemini', 'vertex_ai')


def _args(a) -> dict:
    if isinstance(a, dict): return a
    try: return json.loads(a or '{}') or {}
    except ValueError: return {}


def _anthropic_parts(c) -> list:
    "A chat message's content as Messages API blocks: its text, and a data-url picture as an image block."
    if not isinstance(c, list): return [{'type': 'text', 'text': str(c)}] if str(c or '').strip() else []
    out = []
    for p in c:
        if not isinstance(p, dict): continue
        u = str((p.get('image_url') or {}).get('url') or '') if p.get('type') == 'image_url' else ''
        if u.startswith('data:') and ';base64,' in u:
            ct, b64 = u[5:].split(';base64,', 1)
            out.append({'type': 'image', 'source': {'type': 'base64', 'media_type': ct, 'data': b64}})
        elif str(p.get('text') or '').strip(): out.append({'type': 'text', 'text': p['text']})
    return out


def to_anthropic(messages: list, tools: list) -> tuple:
    """An OpenAI-shaped conversation and its function tools as the Messages API takes them: (system, messages, tools). A tool's answer is a
    tool_result block in the next user turn; turns of one role in a row are one turn (the API alternates)."""
    sys, out = [], []
    def add(role, blocks):
        if out and out[-1]['role'] == role: out[-1]['content'] += blocks
        else: out.append({'role': role, 'content': blocks})
    for m in messages:
        r, c = m.get('role'), m.get('content')
        if r == 'system': sys.append(str(c or '')); continue
        if r == 'tool': add('user', [{'type': 'tool_result', 'tool_use_id': m.get('tool_call_id') or '', 'content': str(c or '')}]); continue
        blocks = _anthropic_parts(c) + [{'type': 'tool_use', 'id': x.get('id') or '', 'name': (x.get('function') or {}).get('name') or '',
                                         'input': _args((x.get('function') or {}).get('arguments'))} for x in m.get('tool_calls') or []]
        if blocks: add('assistant' if r == 'assistant' else 'user', blocks)
    fns = [{'name': f['name'], 'description': f.get('description') or '', 'input_schema': f.get('parameters') or {'type': 'object', 'properties': {}}}
           for x in tools or [] for f in [x.get('function') or x]]
    return '\n\n'.join(x for x in sys if x.strip()), out, fns


def from_anthropic(blocks) -> dict:
    "The Messages API's answer as the chat message apiagent reads: its words, and each tool_use as a tool_call."
    g = lambda b, k: b.get(k) if isinstance(b, dict) else getattr(b, k, None)
    calls = [{'id': g(b, 'id'), 'type': 'function', 'function': {'name': g(b, 'name'), 'arguments': json.dumps(g(b, 'input') or {})}}
             for b in blocks or [] if g(b, 'type') == 'tool_use']
    said = '\n\n'.join(g(b, 'text') or '' for b in blocks or [] if g(b, 'type') == 'text').strip()
    return {'role': 'assistant', 'content': said, **({'tool_calls': calls} if calls else {})}


def to_responses(messages: list, tools: list) -> tuple:
    "The same conversation as Responses API input items: (instructions, items, tools)."
    sys, items = [], []
    for m in messages:
        r, c = m.get('role'), m.get('content')
        if r == 'system': sys.append(str(c or '')); continue
        if r == 'tool': items.append({'type': 'function_call_output', 'call_id': m.get('tool_call_id') or '', 'output': str(c or '')}); continue
        if r == 'assistant':
            if (said := said_text({'content': c})).strip(): items.append({'role': 'assistant', 'content': said})
            items += [{'type': 'function_call', 'call_id': x.get('id') or '', 'name': (x.get('function') or {}).get('name') or '',
                       'arguments': (x.get('function') or {}).get('arguments') or '{}'} for x in m.get('tool_calls') or []]
            continue
        parts = c if isinstance(c, list) else [{'type': 'text', 'text': str(c or '')}]
        items.append({'role': 'user', 'content': [{'type': 'input_image', 'image_url': p['image_url']['url']} if p.get('type') == 'image_url'
                                                  else {'type': 'input_text', 'text': str(p.get('text') or '')} for p in parts if isinstance(p, dict)]})
    fns = [{'type': 'function', 'name': f['name'], 'description': f.get('description') or '',
            'parameters': f.get('parameters') or {'type': 'object', 'properties': {}}}
           for x in tools or [] for f in [x.get('function') or x]]
    return '\n\n'.join(x for x in sys if x.strip()), items, fns


def from_responses(items: list) -> dict:
    "Responses output items as the chat message apiagent reads."
    calls = [{'id': o.get('call_id') or o.get('id'), 'type': 'function', 'function': {'name': o.get('name'), 'arguments': o.get('arguments') or '{}'}}
             for o in items or [] if o.get('type') == 'function_call']
    said = '\n\n'.join(c.get('text') or '' for o in items or [] if o.get('type') == 'message'
                        for c in o.get('content') or [] if c.get('type') == 'output_text').strip()
    return {'role': 'assistant', 'content': said, **({'tool_calls': calls} if calls else {})}


def _google_url(t, cfg, model) -> str:
    """Google's own generateContent for a Gemini model on Google's API - where Google Search grounding lives; the OpenAI-compatible surface
    has no search. '' for a card that reaches Gemini some other way (a gateway in front of it keeps web_search_options)."""
    if t == 'gemini' and not (cfg.get('base_url') or '').strip():
        return f"https://generativelanguage.googleapis.com/v1beta/models/{(model or '').removeprefix('models/')}:generateContent"
    if t == 'vertex_ai' and model.startswith('google/'):
        loc = (cfg.get('location') or 'global').strip()
        host = 'aiplatform.googleapis.com' if loc == 'global' else f'{loc}-aiplatform.googleapis.com'
        return f"https://{host}/v1/projects/{cfg['project'].strip()}/locations/{loc}/publishers/{model.replace('/', '/models/', 1)}:generateContent"
    return ''


def _google_search(url, headers, question) -> str:
    h = {'x-goog-api-key': headers.get('x-goog-api-key') or headers.get('Authorization', '').removeprefix('Bearer ')}
    body = {'contents': [{'role': 'user', 'parts': [{'text': f'{SEARCH_ASK} {question}'}]}], 'tools': [{'google_search': {}}]}
    r = post_retrying(url, h, body, (CONNECT_TIMEOUT, READ_TIMEOUT))
    if r.status_code != 200: raise RuntimeError(f'google search error {r.status_code}: {r.text[:300]}')
    c = (r.json().get('candidates') or [{}])[0]
    said = ''.join(p.get('text') or '' for p in (c.get('content') or {}).get('parts') or []).strip()
    cites = list(dict.fromkeys(str((g.get('web') or {}).get('uri') or '') for g in (c.get('groundingMetadata') or {}).get('groundingChunks') or []))
    if not said: raise RuntimeError('the search came back empty')
    return said + ('\n\nSOURCES\n' + '\n'.join(x for x in cites if x) if any(cites) else '')


ANTHROPIC_WEB = ([{'type': 'web_search_20260209', 'name': 'web_search', 'max_uses': 5},
                  {'type': 'web_fetch_20260209', 'name': 'web_fetch', 'max_uses': 5}],
                 [{'type': 'web_search_20250305', 'name': 'web_search', 'max_uses': 5},      # models before 4.6
                  {'type': 'web_fetch_20250910', 'name': 'web_fetch', 'max_uses': 5}])


def _anthropic_web(create, model, system, content, max_tokens):
    "`create` is make_llm's ask (it carries the effort), or a client, whose messages.create is asked plainly."
    import anthropic
    if hasattr(create, 'messages'): create = create.messages.create
    for tools in ANTHROPIC_WEB:
        msgs = [{'role': 'user', 'content': content}]
        try:
            for _ in range(5):          # a long search pauses the turn; it is continued, not restarted
                r = create(model=model, max_tokens=max_tokens, system=system, messages=msgs, tools=tools)
                if r.stop_reason != 'pause_turn': break
                msgs = msgs + [{'role': 'assistant', 'content': r.content}]
        except anthropic.BadRequestError as e:
            _log_web('anthropic', e); continue
        if r.stop_reason == 'refusal': raise RuntimeError('model refused the request')
        for m in msgs[1:] + [{'content': r.content}]: _saw_anthropic(m['content'])      # a paused turn's searches, then the last
        return '\n\n'.join(b.text for b in r.content if b.type == 'text').strip()
    return None


def _saw_anthropic(blocks):
    """Each search or page the provider's server tools ran inside the call, as a step on the canvas (watching)."""
    for b in blocks or []:
        typ = getattr(b, 'type', '')
        if typ == 'server_tool_use':
            _saw('tool_call', getattr(b, 'name', '') or 'tool', {'tool_call_id': getattr(b, 'id', ''), 'args': dict(getattr(b, 'input', None) or {})})
        elif typ.endswith('_tool_result'):
            got = getattr(b, 'content', None)
            failed = 'error' in str(getattr(got, 'type', '') or (got.get('type') if isinstance(got, dict) else ''))
            _saw('tool_result', getattr(b, 'tool_use_id', ''), {'result': f'{len(got)} results' if isinstance(got, list) else '', 'is_error': failed})


def _responses_web(t, cfg, headers, model, system, user, images, max_tokens, effort=''):
    url = f"{(cfg.get('endpoint') or '').rstrip('/')}/openai/v1/responses" if t == 'azure_openai' else 'https://api.openai.com/v1/responses'
    content = [{'type': 'input_image', 'image_url': f'data:{ct};base64,{b64}'} for ct, b64 in (images or [])] + [{'type': 'input_text', 'text': user}]
    body = {'model': model, 'instructions': system, 'input': [{'role': 'user', 'content': content}],
            'tools': [{'type': 'web_search'}], 'max_output_tokens': max_tokens, **({'reasoning': {'effort': effort}} if effort else {})}
    try:
        r = post_retrying(url, headers, body, 180)
        if r.status_code == 400 and body.pop('reasoning', None) and _EFFORT_REFUSED.search(r.text or ''):
            _no_effort((t, url, model), r.text); r = post_retrying(url, headers, body, 180)
    except requests.RequestException as e: _log_web(t, e); return None
    if r.status_code != 200: _log_web(t, f'{r.status_code} {r.text[:200]}'); return None
    out = r.json(); aiusage.openai(out)
    for o in out.get('output') or []:
        if o.get('type') != 'web_search_call': continue
        act = o.get('action') or {}
        name, args = (('web_search', {'query': act.get('query') or ''}) if act.get('type', 'search') == 'search'
                      else ('web_fetch', {'url': act.get('url') or ''}))
        _saw('tool_call', name, {'tool_call_id': o.get('id') or name, 'args': args})
        _saw('tool_result', o.get('id') or name, {'result': o.get('status') or '', 'is_error': o.get('status') == 'failed'})
    return out.get('output_text') or '\n\n'.join(c.get('text', '') for o in out.get('output') or [] if o.get('type') == 'message'
                                                  for c in o.get('content') or [] if c.get('type') == 'output_text').strip()


def _log_web(t, why):
    from loguru import logger
    logger.info(f'{t}: web search not available on this brain, answering without it - {str(why)[:200]}')


def test_ai(store, cid: int) -> str:
    """Real round trip through the configured model; returns a detail string or raises."""
    c = store.get_connector(cid, with_secret=True)
    # the organisation's gateway says first whether its address and the code are right, in words a person can act on
    if c['Type'] == 'hipaa_ai' and (why := gateway_problem(json.loads(c.get('ConfigJson') or '{}'), c.get('Secret') or '')):
        raise RuntimeError(why)
    out = make_llm(c['Type'], json.loads(c.get('ConfigJson') or '{}'), c.get('Secret'))(
        'Reply with exactly: ok', 'ping')
    return f'model responded: {(out or "").strip()[:80]} - wired into intent triage'

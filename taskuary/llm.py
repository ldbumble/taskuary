"""The triage brain -> one provider-agnostic llm(system, user) -> str callable, the shape
triage.classify_intent expects. Which brain is the owner's choice (setting `triage_ai`):

    ''                  first ACTIVE AI connector with a key (anthropic/openai/azure_openai/
                        openrouter) - or keyless ollama, for a local model

    connector:<id>      that specific AI connector instance
    connector:<type>    legacy/default form - first active instance of that type
    cli:<agent>         your CODING CLI does the triage too - one headless run per message,
                        same brain that works the tasks, no second API key to buy

Cloud keys are cheap and instant per message; a CLI run is slower and heavier but keeps
everything on one model (and one bill). Configure it in Settings -> Triage & routing.
"""
import base64, json, mimetypes, re, requests
from pathlib import Path
from time import sleep
from typing import NamedTuple

from . import redact

# Everything that can answer a PROMPT. This list is what populates every brain picker, so a model
# that cannot emit text does not belong in it however good it is: `typesafe` (Jev) answers typed
# questions and would have nothing to say as the Assistant's brain. It is chosen on its own card.
# Providers that speak the OpenAI chat-completions schema exactly. A base url, a default model
# and a bearer key is the WHOLE integration, so they are data rather than nine near-identical
# branches - the tenth is a row here, not a code change. Every one was verified to exist by an
# unauthenticated POST returning 401/400 (a wrong path returns 404). base_url stays overridable
# for the same reason ollama's is: a gateway in front of any of them still speaks this surface.
# The model defaults are a starting point, not a promise - model names churn, the box overrides.
OPENAI_COMPATIBLE = {
    'groq':       ('https://api.groq.com/openai/v1', 'llama-3.3-70b-versatile'),
    'mistral':    ('https://api.mistral.ai/v1', 'mistral-small-latest'),
    'together':   ('https://api.together.xyz/v1', 'meta-llama/Llama-3.3-70B-Instruct-Turbo'),
    'cerebras':   ('https://api.cerebras.ai/v1', 'llama-3.3-70b'),
    'xai':        ('https://api.x.ai/v1', 'grok-2-latest'),
    'gemini':     ('https://generativelanguage.googleapis.com/v1beta/openai', 'gemini-2.0-flash'),
    'cohere':     ('https://api.cohere.ai/compatibility/v1', 'command-r-plus'),
    'deepseek':   ('https://api.deepseek.com/v1', 'deepseek-chat'),
    'perplexity': ('https://api.perplexity.ai', 'sonar'),
}
AI_TYPES = ('anthropic', 'openai', 'azure_openai', 'openrouter', 'ollama', 'meta') + tuple(OPENAI_COMPATIBLE)

# What a vision model will look at. "See below." is half the mail this app reads, and below was
# a screenshot - a text-only funnel filed the sentence and threw the actual ask away.
VISION_TYPES = ('image/png', 'image/jpeg', 'image/gif', 'image/webp')
VISION_MAX, VISION_BYTES = 4, 5 * 1024 * 1024      # per call: how many images, and how big each


def readable_images(store, message_ids, cap: int = VISION_MAX) -> list:
    """[(media_type, base64)] for the images on these messages, or [] when the owner has vision
    switched off. SVG and PDF are skipped: no provider takes them as image input."""
    if str(store.get_settings().get('vision_enabled') or '1') != '1': return []
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


# The model a CLI runs its light jobs on when nobody named one - triage, drafts, summaries - and the Assistant's, one
# tier up: on haiku it broke its own contract in the 2026-09-24 chat audit ("I don't have the lookup tools"), sonnet held.
LIGHT_DEFAULT = {'claude': 'haiku', 'codex': 'effort:low', 'gemini': 'gemini-2.5-flash'}
ASSISTANT_DEFAULT = {'claude': 'sonnet', 'codex': 'effort:medium', 'gemini': 'gemini-2.5-flash'}


def make_cli_llm(store, agent_name: str, model: str = None, cwd: str = None, trace=None, cancel=None,
                 resume=None, cli_tools: bool = False, extra_env: dict = None, read_only: bool = None,
                 research: bool = False, gear: str = 'light', keep: str = None):
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
    # a CONVERSATION that stays open between turns (clipool) - the Assistant's chat, a general agent's task
    if keep: prof['keep_alive'] = keep
    # `read_only` is explicit for scheduled reports: a folder tells the agent where it may READ,
    # not whether it may write. None preserves the older caller contract where a cwd meant hands.
    no_hands = read_only if read_only is not None else not (cwd or cli_tools)
    if not no_hands and cwd: prof['cwd'] = cwd
    elif not no_hands and cli_tools:
        # An owner-requested setup walkthrough needs the CLI's browser tool, but it still has no
        # business in a checkout. Keep its capable process in Taskuary's scratch directory.
        from . import config
        scratch = config.home() / 'scratch'; scratch.mkdir(exist_ok=True); prof['cwd'] = str(scratch)
    else:
        # The classifier reads untrusted text with every tool off. A report is different: it may
        # safely read files and the web, but never gets command, edit, write, or connector tools.
        from .clis import preset_args, readonly_args, report_read_args
        from . import config
        restrict = report_read_args if research else readonly_args
        prof['args'] = restrict(prof.get('cmd', 'claude'), list(prof.get('args') or preset_args(prof.get('cmd', 'claude')) or ['-p']))
        scratch = config.home() / 'scratch'; scratch.mkdir(exist_ok=True)
        prof['cwd'] = cwd or str(scratch)
    # The ACP road is for the general agent's tool-using runs only. `no_hands` is exactly the
    # classifier - triage and the drafter, one verdict with every tool off - and it keeps argv.
    if not no_hands: prof['acp_ok'] = True
    # WHICH GEAR this job rides. Session work - coding and general alike - takes the MAIN model;
    # the light gear is for the one-message jobs (triage, drafts, summaries, the digest). A
    # general worker session used to fall through to light whenever no main model was set, so
    # the analyst answered on the classifier's cheap model (the owner, 2026-09-16: general agents
    # use the same brain on high level like coding by default).
    light = str(prof.get('light_model') or '') if gear != 'main' else ''
    # a profile that names no light model still gets the CLI's small one: blank used to mean the MAIN model, so triage,
    # drafts and summaries ran on the coding tier (the owner, 2026-09-24: "lower model for triage/assistant")
    if gear != 'main' and not light and not model: light = LIGHT_DEFAULT.get(hub_agents.cli_of(prof, agent_name), '')
    if light.startswith('effort:'):
        # codex on a ChatGPT plan serves ONLY the plan's models - no mini/nano tier exists -
        # so its cheap gear is reasoning effort on the same model (verified: -c
        # model_reasoning_effort=low answers in a fraction of the tokens)
        prof['args'] = list(prof.get('args') or []) + ['-c', f"model_reasoning_effort={light.split(':', 1)[1].strip()}"]
    elif light:
        # 'gpt-5.4-mini@low' - a model from codex's own /model list and one of its reasoning levels
        from .climodels import split_pick
        m, eff = split_pick(light)
        prof['model'] = m
        if eff: prof['args'] = list(prof.get('args') or []) + ['-c', f'model_reasoning_effort={eff}']
    if model: prof['model'] = model     # an explicit per-job model outranks the light gear
    # 300s is the CLASSIFIER's leash - one message, one verdict, and a brain that hangs for twenty
    # minutes on a mail run is a bug. An agent the owner scheduled INTO a repo (cwd) is not
    # classifying: it researches, reads the systems it has tools for and writes a document. Same
    # rule as the flags above - the classifier gets the short leash, the owner's agent keeps its
    # profile (run_cli's own default is 1200s). The cap cut two of one report's four runs off at
    # exactly "timed out after 300s" (2026-09-03).
    if not (cwd or cli_tools or research): prof['timeout'] = min(int(prof.get('timeout') or 300), 300)
    def llm(system, user, max_tokens=MAX_TOKENS, images=None, want=None):
        """max_tokens is advisory here - a CLI has no such flag; the system prompt already says
        how long the answer should be. `images` is accepted and dropped: a CLI reads files off
        disk itself, and the prompt already names their paths. `want` is accepted and dropped
        too, and takes_want is never set: there is no wire to put a schema on, so the prompt and
        the caller's recheck (ask_json) are the whole contract here."""
        from .agents import run_cli
        kwargs = {'cancel': cancel} if cancel is not None else {}
        if extra_env: kwargs['extra_env'] = extra_env
        out, sid, _diff = run_cli(prof, f'{system}\n\n{user}', trace or (lambda *a: None),
                                  resume=resume, **kwargs)
        # what the caller needs to CONTINUE this conversation instead of starting another one
        llm.session_id = sid or resume
        return out
    llm.session_id = resume
    # said out loud, not merely absent: a brain that CANNOT carry a schema is the one whose answer
    # is worth rechecking in code (llm.ask_json). Silence means "do not second-guess me".
    llm.takes_want = False
    return llm


def build_llm(store, pick=None, model=None, trace=None, cancel=None, resume=None,
              cli_tools: bool = False, extra_env: dict = None, research: bool = False, fallback_user=None,
              gear: str = 'light', keep: str = None):
    """The brain, or the demo's script. Everything in the app asks for its brain here, which is
    the one place a demo can be told to answer without a key, a CLI, or a request that leaves
    the machine (demo.py)."""
    from . import demo
    # the demo answers from a script: no key, no CLI, no request leaving the machine
    if demo.enabled(): return demo.brain()
    brain = _build_llm(store, pick, model, trace, cancel, resume, cli_tools, extra_env, research, fallback_user, gear, keep)
    return _Scrubbed(brain) if brain else brain


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
        return self._brain(redact.scrub(system), redact.scrub(user), *a, **kw)
    def __getattr__(self, k): return getattr(object.__getattribute__(self, '_brain'), k)
    def __setattr__(self, k, v): setattr(object.__getattribute__(self, '_brain'), k, v)


def _build_llm(store, pick=None, model=None, trace=None, cancel=None, resume=None,
               cli_tools: bool = False, extra_env: dict = None, research: bool = False, fallback_user=None,
               gear: str = 'light', keep: str = None):
    """The brain named by `pick` ('' = first active AI connector, 'connector:<id>',
    'cli:<agent>'), defaulting to the triage_ai setting - callers like reports may name
    their OWN brain and model per job instead of riding the triage tier. The owner's ordered
    backup-brain setting applies to both cases, but a fallback uses its own model and starts a
    fresh conversation - provider-specific model/session identifiers never cross that line."""
    settings = store.get_settings()
    primary = str(pick if pick is not None else settings.get('triage_ai') or '').strip()
    if not primary:                                    # blank = the default brain, never "the first connector"
        from .agents import default_pick
        primary = default_pick(store)
    backups = [x.strip() for x in str(settings.get('triage_backup_ai') or '').split(',') if x.strip()]
    # This dedupe SURVIVES the role/brain split, unlike its twin in agent_chain. A session's chain
    # is of brains now, so that one went; but `triage_ai` and `triage_backup_ai` still spell a
    # brain as `cli:<agent>` - the classifier is built from an agent ROW (make_cli_llm) - so two
    # settings can still name two profiles backed by one executable, and trying claude twice is
    # not failover: it repeats the same paid failure. It can go when the brain settings name
    # brains, which is a change beyond the 2026-09-16 spec.
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

    def one(candidate, first=False):
        # the conversation - its resume id and its live process - belongs to the FIRST brain only; a failover
        # brain starts its own
        chosen_model, chosen_resume, chosen_keep = (model, resume, keep) if first else (None, None, None)
        if candidate.startswith('cli:'):
            return make_cli_llm(store, candidate[4:], chosen_model, trace=trace, cancel=cancel,
                                resume=chosen_resume, cli_tools=cli_tools, extra_env=extra_env,
                                research=research, gear=gear, keep=chosen_keep)
        want = candidate[10:] if candidate.startswith('connector:') else None
        want_id = int(want) if want and want.isdigit() else None
        for c in store.list_connectors():
            # a local model server (ollama) is the one brain that needs no key to be real
            ready = c['Active'] and (c['HasSecret'] or c['Type'] == 'ollama')
            selected = not want or (c['ConnectorId'] == want_id if want_id is not None else c['Type'] == want)
            if c['Type'] in AI_TYPES and ready and selected:
                full = store.get_connector(c['ConnectorId'], with_secret=True)
                config = json.loads(full.get('ConfigJson') or '{}')
                if chosen_model: config = {**config, 'model': chosen_model}
                return make_llm(full['Type'], config, full.get('Secret'))
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
                kw = kwargs if getattr(brain, 'takes_want', False) else {k: v for k, v in kwargs.items() if k != 'want'}
                out = brain(system, context, **kw)
                failover.last_pick = candidate
                failover.session_id = getattr(brain, 'session_id', None)
                return out
            except Exception as e:
                last = e
                if i == len(brains) - 1 or not availability_failure(e): raise
                if trace: trace('progress', 'fallback',
                                f'{candidate or "automatic AI"} is unavailable; trying {brains[i + 1][0]}')
        raise last
    failover.last_pick, failover.session_id = primary, resume
    failover.takes_want = True          # it forwards one to each brain that can carry it, and drops it for the rest
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
        try: return JsonAnswer(json.loads(re.sub(r'^```(json)?|```$', '', raw.strip(), flags=re.M)), raw, '')
        except ValueError as e: return JsonAnswer(None, raw, f'{type(e).__name__}: {e}')

    carries = getattr(brain, 'takes_want', None)
    if want is not None and carries: kw['want'] = want
    def short(a): return [k for k in need if not (a.data or {}).get(k)] if carries is False else []
    first = ask(user)
    if first.data is not None and not short(first): return first
    again = (f"\n\nYour last answer left out: {', '.join(short(first))}. Answer the whole JSON object "
             'again, including those.' if first.data is not None
             else '\n\nAnswer with the JSON object only - no prose, no code fence.')
    second = ask(user + again)
    return second if second.data is not None and not short(second) else (second if second.data is not None else first)


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
        except requests.RequestException as e: last = e; continue
        if r.status_code not in RETRY_STATUS: return r
        last = r
    if isinstance(last, Exception): raise last
    return last


def tried(r) -> str:
    """So the row the owner reads says we rode it out and it stayed down, not that we gave up."""
    return f' after {RETRY_TRIES} tries' if r.status_code in RETRY_STATUS else ''


def make_llm(t, cfg: dict, key: str):
    if not key and t != 'ollama': raise RuntimeError('no API key saved - paste one under Credentials')
    if t == 'anthropic':
        import anthropic
        cli = anthropic.Anthropic(api_key=key)
        model = cfg.get('model') or 'claude-opus-5'
        def llm(system, user, max_tokens=MAX_TOKENS, images=None, want=None):
            # images FIRST: every provider reads a picture better when the question follows it
            content = ([{'type': 'image', 'source': {'type': 'base64', 'media_type': ct, 'data': b64}}
                        for ct, b64 in (images or [])] + [{'type': 'text', 'text': user}]) if images else user
            # `want` is a schema the answer MUST fit. Anthropic has no response_format; a tool the
            # model is forced to call is the same thing - the tool's input schema is the answer's,
            # and what comes back is the tool call's arguments rather than prose.
            forced = ({'tools': [{'name': want.get('name') or 'answer', 'description': 'Answer with these fields.',
                                  'input_schema': want.get('schema') or want}],
                       'tool_choice': {'type': 'tool', 'name': want.get('name') or 'answer'}} if want else {})
            r = cli.messages.create(model=model, max_tokens=max_tokens, system=system,
                                    messages=[{'role': 'user', 'content': content}], **forced)
            if r.stop_reason == 'refusal': raise RuntimeError('model refused the request')
            if want:
                call = next((b for b in r.content if b.type == 'tool_use'), None)
                if call is not None: return json.dumps(call.input)
            return next((b.text for b in r.content if b.type == 'text'), '')
        llm.takes_want = True
        return llm
    if t == 'openai':
        urls = ['https://api.openai.com/v1/chat/completions']
        headers, model = {'Authorization': f'Bearer {key}'}, cfg.get('model') or 'gpt-4o-mini'
    elif t == 'openrouter':
        # one key, the whole catalog behind the OpenAI schema - open-weights models included.
        # Model strings are OpenRouter's names ('meta-llama/llama-3.3-70b-instruct', ...);
        # 'openrouter/auto' lets their router pick, so an empty model box still works.
        urls = ['https://openrouter.ai/api/v1/chat/completions']
        headers, model = {'Authorization': f'Bearer {key}', 'X-Title': 'Taskuary'}, cfg.get('model') or 'openrouter/auto'
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
        headers, model = {'Authorization': f'Bearer {key}'}, cfg.get('model') or 'muse-spark-1.2'
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
        base = (cfg.get('base_url') or default_base).rstrip('/')
        urls = [f'{base}/chat/completions']
        headers, model = {'Authorization': f'Bearer {key}'}, cfg.get('model') or default_model
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

    def llm(system, user, max_tokens=MAX_TOKENS, images=None, want=None):
        # three independent compat axes: newer models reject max_tokens ("use
        # max_completion_tokens"), older Azure api-versions reject max_completion_tokens,
        # older Azure resources 404 the v1 url - and not every model behind this one schema can
        # be handed a response_format. Walk the grid until one works.
        content = ([{'type': 'image_url', 'image_url': {'url': f'data:{ct};base64,{b64}'}}
                    for ct, b64 in (images or [])] + [{'type': 'text', 'text': user}]) if images else user
        msgs = [{'role': 'system', 'content': system}, {'role': 'user', 'content': content}]
        last = None

        def once(fmt):
            """The url x token-parameter grid with this response_format. The answer, or None when
            the endpoint refused the FORMAT and the same question is worth asking without it."""
            nonlocal last
            for url in urls:
                for tok_param in ('max_completion_tokens', 'max_tokens'):
                    body = {'messages': msgs, tok_param: max_tokens,
                            **({'model': model} if model else {}), **({'response_format': fmt} if fmt else {})}
                    # a local model may spend its first call loading weights off disk - give it room
                    r = post_retrying(url, headers, body, 180 if t == 'ollama' else 60)
                    if r.status_code == 200: return r.json()['choices'][0]['message']['content']
                    last = r
                    if r.status_code == 404: break                      # wrong surface -> next url
                    if r.status_code == 400 and fmt: return None        # cannot carry a schema -> ask without one
                    if not (r.status_code == 400 and 'max_completion_tokens' in r.text):
                        raise RuntimeError(f'{t} error {r.status_code} at {url.split("?")[0]}{tried(r)}: {r.text[:300]}')
            return None

        # `want` is a JSON schema the answer MUST fit, and the strongest form is worth asking for:
        # a strict schema is obeyed even when the prose contract in the prompt says something
        # narrower (verified against gpt-5.4, TQ-0665). An old model or a route that cannot carry
        # it answers 400, and then the prompt is all there is - which is where we were before.
        for fmt in ([{'type': 'json_schema', 'json_schema': {**want, 'strict': True}}] if want else []) + [None]:
            out = once(fmt)
            if out is not None: return out
        raise RuntimeError(f'{t} error {last.status_code} at {urls[-1].split("?")[0]}{tried(last)}: {last.text[:300]}')
    llm.takes_want = True
    return llm


def test_ai(store, cid: int) -> str:
    """Real round trip through the configured model; returns a detail string or raises."""
    c = store.get_connector(cid, with_secret=True)
    out = make_llm(c['Type'], json.loads(c.get('ConfigJson') or '{}'), c.get('Secret'))(
        'Reply with exactly: ok', 'ping')
    return f'model responded: {(out or "").strip()[:80]} - wired into intent triage'

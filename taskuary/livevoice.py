"""Live interaction: talk with a task's agent out loud (Pipecat, local WebRTC in the browser).

Two halves, as Pipecat's multi-worker example has them (examples/multi-worker/llm-with-backend): a FAST voice in front that talks, and
the task's own agent behind it - Claude Code, Codex, whatever works the task - unchanged, working on while he talks.

THE FRONT DOES NO WORK. For each line he says it may only (TOOLS): hand his words to the agent exactly as spoken (general.to_agent, the
one road a typed line takes - so they land in the chat as his line), read what is already there (the turn's step lines, the agent's
words, the card that waits) shortened for the ear, or press the card that waits - and only after it has read back what that press will do
and heard his yes to that same card, through the decide handler a click uses. Whatever its model answers, nothing else can happen:
`Front.heard` acts in plain code on a closed list. Nothing extra goes into the chat - his lines are his lines, the agent's words its turn.

The cards: "Live interaction" (live_voice) picks who hears and who speaks; each provider is its own card with its key and Test -
Deepgram (the same card that transcribes voice notes), Cartesia, Google Cloud speech (hearing and speaking on one credential).
Pipecat is an optional package, installed in the background once the card is switched on (deps.OPTIONAL['pipecat']).
"""
import asyncio, base64, json, threading, time
import requests
from loguru import logger

PIPECAT = '0.0.108'
HEARING = {'deepgram': 'deepgram', 'google': 'google_speech'}        # the card's choice -> the provider card that holds the key
SPEAKING = {'cartesia': 'cartesia', 'google': 'google_speech'}
TYPES = ('live_voice', 'cartesia', 'google_speech')
CARTESIA_VOICE = '71a7ad14-091c-4e8e-a314-022ece01c121'             # a stock Cartesia voice; his own id replaces it on the card
CARTESIA_VERSION = '2025-04-16'
TOOLS = ('hand_to_agent', 'read', 'press')
ACK, NO_CARD, LEFT = 'On it.', 'Nothing is waiting for a press.', 'Left as it is.'
def ask_yes(readback: str) -> str: return f"{readback.rstrip('. ')}. Say yes to do it."


def _cfg(c) -> dict:
    try: return json.loads((c or {}).get('ConfigJson') or '{}') or {}
    except ValueError: return {}


def hipaa_ok(cfg: dict) -> bool:
    "Only the Google pair keeps his voice on a provider a covered entity can sign a BAA with; any other pair is not for HIPAA data."
    return (cfg.get('hearing') or 'deepgram') == 'google' and (cfg.get('speaking') or 'cartesia') == 'google'


def _card(store, t: str):
    c = next((c for c in store.list_connectors() if c['Type'] == t and c['Active']), None) or store.get_connector_by_type(t)
    return store.get_connector(c['ConnectorId'], with_secret=True) if c else None


def setup(store) -> dict:
    """{live, hear, speak, cfg, hipaa} - the live card and the two provider cards its choices name, with their keys. RuntimeError, said
    so the owner knows which card to open, when one is missing, off or has no key."""
    live = _card(store, 'live_voice')
    if not live: raise RuntimeError('there is no Live interaction card - add it under Connections')
    cfg = _cfg(live)
    h, s = cfg.get('hearing') or 'deepgram', cfg.get('speaking') or 'cartesia'
    if h not in HEARING: raise RuntimeError(f"hearing is {h!r} - choose deepgram or google on the Live interaction card")
    if s not in SPEAKING: raise RuntimeError(f"speaking is {s!r} - choose cartesia or google on the Live interaction card")
    out = {'live': live, 'cfg': cfg, 'hipaa': hipaa_ok(cfg)}
    for role, t in (('hear', HEARING[h]), ('speak', SPEAKING[s])):
        c = _card(store, t)
        name = {'deepgram': 'Deepgram', 'cartesia': 'Cartesia', 'google_speech': 'Google Cloud speech'}[t]
        if not c or not c.get('Secret'): raise RuntimeError(f'the {name} card has no key yet - open it under Connections and paste one')
        if not c['Active']: raise RuntimeError(f'the {name} card is off - switch it on under Connections')
        out[role] = c
    return out


# ── THE PROVIDER CARDS' TESTS: one real call each ────────────────────────────────────────────────────────────────────────────────────
def _said(r, who: str):
    if r.status_code < 300: return
    try: why = r.json(); why = why.get('error', {}).get('message') if isinstance(why.get('error'), dict) else why.get('error') or why.get('message') or why
    except ValueError: why = r.text
    raise RuntimeError(f'{who} answered {r.status_code}: {str(why)[:200]}')


def test_cartesia(c) -> str:
    "The voice his card names, asked of Cartesia with his key: a wrong key or voice id says so here, not on the first call."
    key, vid = (c.get('Secret') or '').strip(), (_cfg(c).get('voice_id') or CARTESIA_VOICE).strip()
    if not key: raise RuntimeError('Cartesia: no API key saved')
    r = requests.get(f'https://api.cartesia.ai/voices/{vid}', headers={'X-API-Key': key, 'Cartesia-Version': CARTESIA_VERSION}, timeout=20)
    _said(r, 'Cartesia')
    return f"Cartesia answered - voice {r.json().get('name') or vid} is ready to speak"


def google_auth(c) -> tuple:
    """(headers, params) for Google Cloud's speech APIs: a service-account JSON is swapped for a token (google-auth, as the Google Cloud
    card does), anything else is an API key."""
    sec = (c.get('Secret') or '').strip()
    if not sec: raise RuntimeError('Google Cloud speech: no service-account JSON or API key saved')
    if not sec.startswith('{'): return {}, {'key': sec}
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
    except ImportError:
        from .deps import Missing
        raise Missing('google.auth', 'google-auth is not installed - the Google Cloud speech card needs it. Install it from the card') from None
    cr = service_account.Credentials.from_service_account_info(json.loads(sec), scopes=['https://www.googleapis.com/auth/cloud-platform'])
    cr.refresh(Request())
    return {'Authorization': f'Bearer {cr.token}', **({'x-goog-user-project': p} if (p := _cfg(c).get('project')) else {})}, {}


def test_google(c) -> str:
    "One word spoken by Text-to-Speech, then heard back by Speech-to-Text: both halves of the card, on its own credential."
    h, p = google_auth(c)
    lang = _cfg(c).get('language') or 'en-US'
    r = requests.post('https://texttospeech.googleapis.com/v1/text:synthesize', params=p, headers=h, timeout=30,
                      json={'input': {'text': 'Test.'}, 'voice': {'languageCode': lang}, 'audioConfig': {'audioEncoding': 'LINEAR16', 'sampleRateHertz': 16000}})
    _said(r, 'Google Text-to-Speech')
    audio = r.json().get('audioContent') or ''
    r = requests.post('https://speech.googleapis.com/v1/speech:recognize', params=p, headers=h, timeout=30,
                      json={'config': {'languageCode': lang}, 'audio': {'content': audio}})
    _said(r, 'Google Speech-to-Text')
    return 'Google answered - speaking and hearing both work'


def test_live(store, c) -> str:
    "The Live interaction card: Pipecat here, both chosen cards set up and each answering its own one real call."
    from . import deps, voice
    if not deps.installed('pipecat'): raise deps.Missing('pipecat', f'Pipecat is not installed yet - {installing()}')
    s = setup(store)
    run = {'deepgram': lambda x: voice.test(store, x), 'cartesia': test_cartesia, 'google_speech': test_google}
    said = [run[s['hear']['Type']](s['hear'])]
    if s['speak']['ConnectorId'] != s['hear']['ConnectorId']: said.append(run[s['speak']['Type']](s['speak']))
    return ' · '.join(said) + ('' if s['hipaa'] else ' · not for HIPAA data: only the Google pair is')


def test(store, c) -> str:
    return {'live_voice': lambda: test_live(store, c), 'cartesia': lambda: test_cartesia(c), 'google_speech': lambda: test_google(c)}[c['Type']]()


# ── PIPECAT, INSTALLED IN THE BACKGROUND once the card is on ─────────────────────────────────────────────────────────────────────────
_install = {'state': '', 'why': ''}
def installing() -> str:
    st = _install['state']
    return ('it is being installed now - press Test again in a minute' if st == 'running' else
            f"its install failed: {_install['why']} - press Install" if st == 'failed' else 'switch the card on and it installs by itself, or press Install')


def ensure(store=None) -> str:
    "Start Pipecat's install in the background when it is missing: '' when it is here, else the install's state. Never twice at once."
    from . import deps
    if deps.installed('pipecat'): return ''
    if _install['state'] == 'running': return 'running'
    can, why = deps.can_install()
    if not can: _install.update(state='failed', why=why); return 'failed'
    def go():
        try: deps.install('pipecat'); _install.update(state='done', why='')
        except Exception as e: _install.update(state='failed', why=str(e)[:300]); logger.warning(f'live voice: Pipecat did not install - {e}')
    _install.update(state='running', why='')
    threading.Thread(target=go, name='pipecat-install', daemon=True).start()
    return 'running'


# ── THE FRONT: what it reads, and the only things it can do ─────────────────────────────────────────────────────────────────────────
def readback(store, rid: int) -> str:
    "What pressing card `rid` will do, in words read from the review itself - never a model's."
    from .connectorcatalog import action_for
    from .outbound import review_envelope
    rv = store.get_review(int(rid)) or {}
    if rv.get('Kind') == 'action':
        try: d = json.loads(rv.get('DraftText') or '{}') or {}
        except ValueError: d = {}
        d = d if isinstance(d, dict) else {}
        verb = ((action_for(d.get('type')) or {}).get('press') if d.get('action') == 'run_tool' else '') or 'Approve'
        what = ' '.join(str(d.get('what') or d.get('command') or rv.get('Reason') or 'the step it proposes').split())[:240]
        return f'{verb}: {what}'
    to = review_envelope(store, rv).get('to') or []
    who = ', '.join(str(x.get('name') or x.get('address') or x) if isinstance(x, dict) else str(x) for x in to[:3]) or 'its recipient'
    words = ' '.join(str(rv.get('DraftText') or '').split())
    return f"Send the reply to {who}, saying: {words[:240]}{'...' if len(words) > 240 else ''}"


def facts(store, tid: int) -> dict:
    """What the front may say, read from the task's own chat (chatlog.read): the working turn's step lines, the agent's newest words, and
    the one card that waits. {working, steps, answer, answer_id, card}"""
    from . import chatlog
    items = chatlog.read(store, int(tid)).get('items') or []
    turns = [x for x in items if x.get('kind') == 'turn']
    live = next((t for t in reversed(turns) if t.get('state') in chatlog.LIVE), None)
    said = next((t for t in reversed(turns) if t.get('state') not in chatlog.LIVE and (t.get('text') or '').strip()), None)
    cards = [c for x in items for c in ([x] if x.get('kind') == 'card' else x.get('cards') or [] if x.get('kind') == 'turn' else [])]
    card = next((c for c in reversed(cards) if c.get('kind') == 'card' and (c.get('status') or c.get('state')) == 'pending' and c.get('review')), None)
    steps = [str(s.get('text') or '').strip() for s in (live or {}).get('steps') or [] if str(s.get('text') or '').strip()]
    return {'working': bool(live), 'steps': steps[-4:], 'answer': str((said or {}).get('text') or '').strip()[:2000],
            'answer_id': (said or {}).get('id'), 'card': {'review': int(card['review']), 'readback': readback(store, card['review'])} if card else None}


JUDGE = ('You are the voice in front of an AI agent that works a task for the person talking to you. You never do the work, decide or '
         'invent anything: the agent does. For the line he just said, answer one JSON object {"tool": ..., "say": ...} with tool one of:\n'
         '"hand_to_agent" - he asks for work, a change, a fact, an opinion or a decision, or tells the agent something: it goes to the agent '
         'exactly as he said it; say is "".\n'
         '"read" - he asks what the agent is doing, what it said, or what the card says: say it from STATUS, ANSWER and CARD below, short '
         'for speech, adding nothing that is not there.\n'
         '"press" - he wants the waiting CARD done, or says yes to what was READ BACK; say is "".\n'
         '"none" - he says no to what was read back, or the line is not meant for anyone; say is "".\n'
         'When unsure, hand_to_agent.')
WANT = {'type': 'object', 'properties': {'tool': {'type': 'string', 'enum': [*TOOLS, 'none']}, 'say': {'type': 'string'}},
        'required': ['tool', 'say'], 'additionalProperties': False}
SHORTEN = ('Say this for the ear: at most three short sentences, plain words, no lists, no markdown, no links read out. Keep its meaning, '
           'names and numbers; add nothing. Answer with the words to speak only.')


def brain_for(store, cfg: dict):
    "The owner's own AI on its light gear, as every quick one-shot job takes it - or the model the card names."
    from . import llm
    return llm.build_llm(store, job='judge', gear='light', model=(cfg.get('model') or '').strip() or None)


class Front:
    """One live session's front voice on task `tid`. `hand(words)`: his words to the agent (general.to_agent). `press(rid)` -> (ok, why):
    the decide handler a click uses. `brain(system, user)`: the fast model. Every method returns the lines to speak."""
    def __init__(self, store, tid, brain, hand, press, read=facts):
        self.store, self.tid, self.brain, self.hand, self.press, self.read = store, tid, brain, hand, press, read
        self.asked, self.lock = None, threading.Lock()
        f = self._facts() if tid else {}
        self.seen_answer, self.seen_card = f.get('answer_id'), (f.get('card') or {}).get('review')

    def _facts(self): return self.read(self.store, self.tid) if self.tid else {'working': False, 'steps': [], 'answer': '', 'answer_id': None, 'card': None}

    def judge(self, words: str, f: dict) -> dict:
        from .llm import ask_json
        user = (f"STATUS: {'working - ' + ' / '.join(f['steps']) if f['working'] else 'not working right now'}\n"
                f"ANSWER: {f['answer'][:1200] or '(none yet)'}\nCARD: {(f['card'] or {}).get('readback') or '(none waiting)'}\n"
                f"READ BACK: {(f['card'] or {}).get('readback') if self.asked and f['card'] and f['card']['review'] == self.asked else '(nothing)'}\n\n"
                f'HE SAID: {words}')
        try: return ask_json(self.brain, JUDGE, user, want=WANT, need=('tool',)).data or {}
        except Exception as e: logger.warning(f'live voice: the front could not judge a line - {e}'); return {}

    def heard(self, words: str) -> list:
        words = ' '.join(str(words or '').split())
        if not words: return []
        with self.lock:
            f = self._facts()
            a = self.judge(words, f) if self.brain else {}
            tool = a.get('tool') if a.get('tool') in (*TOOLS, 'none') else 'hand_to_agent'     # ...his words reach the agent: the safe default
            asked, self.asked = self.asked, None
            if tool == 'press':
                c = f.get('card')
                if not c: return [NO_CARD]
                if asked != c['review']: self.asked = c['review']; return [ask_yes(c['readback'])]
                ok, why = self.press(c['review'])
                self.seen_card = c['review']
                return ['Done.' if ok else f'That did not go: {why}']
            if tool == 'read': return [str(a.get('say') or '').strip() or self._status(f)]
            if tool == 'none': return [LEFT] if asked else []
            self.hand(words)
            return [ACK]

    def _status(self, f) -> str:
        return ('It is working: ' + '. '.join(f['steps'][-2:]) if f['working'] and f['steps'] else 'It is working.' if f['working']
                else 'It is not working on anything right now.')

    def shorten(self, text: str) -> str:
        try: out = str(self.brain(SHORTEN, text[:4000]) or '').strip() if self.brain else ''
        except Exception as e: logger.warning(f'live voice: could not shorten an answer - {e}'); out = ''
        return out or ' '.join(text.split())[:400]

    def news(self) -> list:
        "What arrived since the last look: the agent's new words, shortened, then a new card read back with its question."
        if not self.tid: return []
        with self.lock:
            f, out = self._facts(), []
            if f['answer_id'] and f['answer_id'] != self.seen_answer and not f['working']:
                self.seen_answer = f['answer_id']; out.append(self.shorten(f['answer']))
            c = f.get('card')
            if c and c['review'] != self.seen_card:
                self.seen_card = self.asked = c['review']; out.append(ask_yes(c['readback']))
            return out


# ── THE PIPELINE: browser mic -> hearing -> the front -> speaking -> browser speaker ─────────────────────────────────────────────────
def services(s: dict):
    "(stt, tts) Pipecat services for the chosen cards."
    hc, sc = s['hear'], s['speak']
    if hc['Type'] == 'deepgram':
        from pipecat.services.deepgram.stt import DeepgramSTTService
        stt = DeepgramSTTService(api_key=hc['Secret'])
    else: stt = _google('stt', hc)
    if sc['Type'] == 'cartesia':
        from pipecat.services.cartesia.tts import CartesiaTTSService
        tts = CartesiaTTSService(api_key=sc['Secret'], voice_id=(_cfg(sc).get('voice_id') or CARTESIA_VOICE).strip())
    else: tts = _google('tts', sc)
    return stt, tts


def _google(which: str, c):
    sec = (c.get('Secret') or '').strip()
    if not sec.startswith('{'): raise RuntimeError('a live session on Google needs the service-account JSON on its card - an API key only passes Test')
    if which == 'stt':
        from pipecat.services.google.stt import GoogleSTTService
        return GoogleSTTService(credentials=sec)
    from pipecat.services.google.tts import GoogleTTSService
    return GoogleTTSService(credentials=sec)


def front_processor(front: Front, tell=lambda m: None, poll: float = 1.5):
    """The front as a Pipecat processor: a final transcription becomes what the front answers, spoken; the agent's news is spoken as it
    comes. When he starts talking its own speech stops (an interruption) - the agent behind it never hears of that. `tell(msg)`: a state
    for the Talk button ('listening', 'thinking', 'speaking') over the data channel."""
    from pipecat.frames.frames import (BotStartedSpeakingFrame, BotStoppedSpeakingFrame, CancelFrame, EndFrame, StartFrame, TranscriptionFrame,
                                       TTSSpeakFrame, VADUserStartedSpeakingFrame)
    from pipecat.processors.frame_processor import FrameProcessor

    class FrontProcessor(FrameProcessor):
        def __init__(self):
            super().__init__(); self._watch, self._speaking = None, False

        async def _say(self, lines):
            for l in lines:
                if l: await self.push_frame(TTSSpeakFrame(l))

        async def _heard(self, words):
            # ...in a task of its own, never the frame's: an interruption resets the frame's task, and his words must still reach the agent
            tell({'tq': 'state', 'state': 'thinking'})
            try: await self._say(await asyncio.to_thread(front.heard, words))
            finally:
                if not self._speaking: tell({'tq': 'state', 'state': 'listening'})

        async def _watching(self):
            while True:
                await asyncio.sleep(poll)
                try: await self._say(await asyncio.to_thread(front.news))
                except asyncio.CancelledError: raise
                except Exception as e: logger.warning(f'live voice: news not read - {e}')

        async def process_frame(self, frame, direction):
            await super().process_frame(frame, direction)
            if isinstance(frame, StartFrame) and not self._watch: self._watch = self.create_task(self._watching()); tell({'tq': 'state', 'state': 'listening'})
            elif isinstance(frame, (EndFrame, CancelFrame)) and self._watch: await self.cancel_task(self._watch); self._watch = None
            elif isinstance(frame, BotStartedSpeakingFrame): self._speaking = True; tell({'tq': 'state', 'state': 'speaking'})
            elif isinstance(frame, BotStoppedSpeakingFrame): self._speaking = False; tell({'tq': 'state', 'state': 'listening'})
            elif isinstance(frame, VADUserStartedSpeakingFrame) and self._speaking: await self.broadcast_interruption()
            if isinstance(frame, TranscriptionFrame): self.create_task(self._heard(frame.text)); return
            await self.push_frame(frame, direction)
    return FrontProcessor()


def pipeline(transport_in, stt, front: Front, tts, transport_out, tell=lambda m: None, poll: float = 1.5, vad=True):
    "Mic -> voice activity -> hearing -> the front -> speaking -> speaker."
    from pipecat.pipeline.pipeline import Pipeline
    steps = [transport_in]
    if vad:
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.processors.audio.vad_processor import VADProcessor
        steps.append(VADProcessor(vad_analyzer=SileroVADAnalyzer()))
    return Pipeline([*steps, stt, front_processor(front, tell, poll), tts, transport_out])


SESSIONS = {}           # pc_id -> {task, tid, front, conn}


async def offer(store, sdp: str, kind: str, tid, hand, press, pc_id: str = None) -> dict:
    """The browser's WebRTC offer: a SmallWebRTC connection on this machine (no Daily, no LiveKit), its pipeline started, the answer back.
    `hand(tid, words)` / `press(rid)`: the server's one road into the agent and its decide handler. With no task yet (New), his words go
    back to the page ({'tq': 'new'}), which makes the task by New's own road and binds this session to it."""
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineTask
    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
    if pc_id and pc_id in SESSIONS:
        conn = SESSIONS[pc_id]['conn']; await conn.renegotiate(sdp=sdp, type=kind); return conn.get_answer()
    s = setup(store)
    stt, tts = services(s)
    loop = asyncio.get_running_loop()
    conn = SmallWebRTCConnection()
    await conn.initialize(sdp=sdp, type=kind)
    tell = lambda m: loop.call_soon_threadsafe(conn.send_app_message, m)
    def handed(words):
        if front.tid: return hand(front.tid, words)
        tell({'tq': 'new', 'text': words})
    front = Front(store, tid, brain_for(store, s['cfg']), handed, press)
    transport = SmallWebRTCTransport(webrtc_connection=conn, params=TransportParams(audio_in_enabled=True, audio_out_enabled=True))
    task = PipelineTask(pipeline(transport.input(), stt, front, tts, transport.output(), tell))
    ans = conn.get_answer()
    SESSIONS[ans['pc_id']] = {'task': task, 'tid': tid, 'front': front, 'conn': conn}

    @conn.event_handler('closed')
    async def _closed(_c): SESSIONS.pop(ans['pc_id'], None); await task.cancel()
    loop.create_task(PipelineRunner(handle_sigint=False).run(task))
    return ans


def bind(pc_id: str, tid: int) -> bool:
    "A session started on New, bound to the task his first words made: from now on it reads and hands to that task."
    s = SESSIONS.get(pc_id)
    if not s: return False
    f = s['front']
    with f.lock: s['tid'] = f.tid = int(tid); x = f._facts(); f.seen_answer, f.seen_card = x['answer_id'], (x['card'] or {}).get('review')
    return True


async def stop(pc_id: str) -> bool:
    s = SESSIONS.pop(pc_id, None)
    if not s: return False
    await s['task'].cancel()
    try: await s['conn'].disconnect()
    except Exception: pass
    return True

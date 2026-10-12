"""What the owner's own sent words MEAN: did they ask the other side for something, did they promise something - what,
and by when - and did a later message of theirs deliver an earlier promise. The model reads it; code only validates.

Two regexes used to decide this (assistant._ASKS / _PROMISE, 2026-08-29) and, worse, decided which threads the Advisor
was allowed to SEE: "On it, by EOD" was no promise, "I can have it to you Friday" was nothing at all, and a promise
vanished the moment the other side wrote "Great, thanks!" (the owner, 2026-10-11: "remove all the old garbage code ...
Everything should be ai"). Now each sent message is judged ONCE (sent_verdict, by MessageId), in one batched light-model
call per Advisor run, and a promise stays open until a LATER message of the owner's is judged to deliver it - the judge
sees the thread's open promises when it reads that later message, and the owner's later words when it reads the promise
(so the order messages are judged in never matters).

No brain is not a verdict: nothing is guessed, and the summaries say promises and asks cannot be tracked (blind()).
"""
import threading
from datetime import datetime, timedelta
from loguru import logger

DAYS = 30                  # the Advisor's window (assistant.DAYS): how far back sent words are read
BATCH = 40                 # messages per call - a first run on a full Sent folder catches up over a few runs
WORDS = 600                # characters of each message's own words the model reads
LATER = 3                  # later messages of the owner's on the thread shown beside a promise

SYSTEM = ("You read messages the OWNER sent and say what each one means for follow-up. For each message answer:\n"
          "- asks_them: true when the owner asked the other side to do, send, decide or answer something they now owe back "
          "(a question, a request, 'let me know', 'please approve'). A plain thanks or an FYI is false.\n"
          "- promise: true when the owner committed THEMSELF to do or send something later ('I'll send it Friday', 'On it, by EOD', "
          "'I can have it to you tomorrow', 'leave it with me'). Something already done in this very message is not a promise.\n"
          "- what: for a promise, the thing promised as a short verb phrase in the owner's voice, without the date "
          "('send the revised budget'); otherwise ''.\n"
          "- due: for a promise with a day, that day as YYYY-MM-DD, worked out from the date the message was SENT ('today'/'EOD' "
          "= the sent day, 'tomorrow' = the next day, 'Friday' = the next Friday on or after it); null when no day was given.\n"
          "- delivered: for a promise, true when one of YOUR LATER WORDS shown under it plainly delivers it; otherwise false.\n"
          "- delivers: the ids of OPEN PROMISES shown under the message that THIS message delivers (sends the thing, says it is done); [] if none.\n"
          "Judge only from the words given. Answer JSON only: "
          '{"verdicts": [{"id": "m123", "asks_them": false, "promise": false, "what": "", "due": null, "delivered": false, "delivers": []}]}')
WANT = {'type': 'object', 'required': ['verdicts'], 'properties': {'verdicts': {'type': 'array', 'items': {
    'type': 'object', 'required': ['id', 'asks_them', 'promise'],
    'properties': {'id': {'type': 'string'}, 'asks_them': {'type': 'boolean'}, 'promise': {'type': 'boolean'}, 'what': {'type': 'string'},
                   'due': {'type': ['string', 'null']}, 'delivered': {'type': 'boolean'}, 'delivers': {'type': 'array', 'items': {'type': 'string'}}}}}}}
_LOCK = threading.Lock()   # one judging pass at a time: the Advisor and the digest firing together would pay twice


def _since(days): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
def _ts(s): return str(s or '')[:19].replace('T', ' ')
def _words(m: dict, n: int = WORDS) -> str:
    from .triage import own_words
    return ' '.join(own_words(str(m.get('BodyText') or '')).split())[:n]
def _day(s) -> str:
    try: return datetime.fromisoformat(_ts(s)).strftime('%a %d %b %Y')
    except ValueError: return str(s or '')[:10]
def _date(v) -> str | None:
    try: return datetime.fromisoformat(str(v).strip()[:10]).strftime('%Y-%m-%d') if v else None
    except ValueError: return None


def _brain(store, llm):
    if llm is not None: return llm
    from .llm import build_llm
    try: return build_llm(store)
    except Exception as e:
        logger.debug(f'sentjudge: no model - {e}'); return None


def _item(store, m: dict, open_: list, later: list) -> str:
    to = store.last_inbound_in(m['ConversationId']) or {}
    out = [f"[m{m['MessageId']}] sent {_day(m.get('SentAt'))} to {to.get('FromName') or to.get('FromEmail') or 'them'} "
           f"re \"{' '.join(str(m.get('Subject') or '').split())[:90]}\":\n  \"{_words(m)}\""]
    if open_: out.append('  OPEN PROMISES on this thread: ' + '; '.join(
        f"[m{p['MessageId']}] \"{p.get('PromiseWhat') or _words(p, 120)}\"" + (f" (due {p['PromiseDue']})" if p.get('PromiseDue') else '') for p in open_))
    if later: out.append('  YOUR LATER WORDS on this thread: ' + '; '.join(f"{_day(x.get('SentAt'))}: \"{_words(x, 200)}\"" for x in later))
    return '\n'.join(out)


def _ask(llm, items: list) -> list:
    from .llm import ask_json
    a = ask_json(llm, SYSTEM, f"TODAY: {datetime.now().strftime('%a %d %b %Y')}\n\n" + '\n\n'.join(items), want=WANT, need=('verdicts',))
    got = (a.data or {}).get('verdicts') if isinstance(a.data, dict) else None
    if not isinstance(got, list): raise ValueError(f"the judge's answer held no verdicts: {(a.error or a.raw)[:160]}")
    return [v for v in got if isinstance(v, dict)]


def judge(store, llm=None, days: int = DAYS) -> int:
    """Read the owner's sent messages in the window that have no verdict yet - ONE call, at most BATCH of them, newest
    first - and keep each answer. Nothing unjudged costs nothing (no model is even built). Returns how many were judged."""
    with _LOCK:
        rows = store.sent_unjudged(_since(days), BATCH)
        if not rows: return 0
        llm = _brain(store, llm)
        if llm is None: return 0
        ctx, items = {}, []
        for m in rows:
            cid, at = m['ConversationId'], _ts(m.get('SentAt'))
            open_ = [p for p in store.open_promises(_since(days), at, cid) if p['MessageId'] != m['MessageId'] and _ts(p.get('SentAt')) < at]
            later = store.own_sent_on_thread(cid, after=at, limit=LATER)
            ctx[f"m{m['MessageId']}"] = (m, {f"m{p['MessageId']}": p['MessageId'] for p in open_}, later)
            items.append(_item(store, m, open_, later))
        try: got = _ask(llm, items)
        except Exception as e:
            logger.warning(f'sentjudge: the sent-words judge failed - {e}'); return 0
        by, n = getattr(llm, 'last_pick', None) or 'model', 0
        for v in got:
            hit = ctx.get(str(v.get('id') or '').strip())
            if not hit: continue                                       # an id it invented is not a verdict
            m, opened, later = hit
            promise = v.get('promise') is True
            done = later[-1]['MessageId'] if promise and v.get('delivered') is True and later else None
            store.put_sent_verdict(m['MessageId'], m['ConversationId'], v.get('asks_them') is True, promise,
                                   ' '.join(str(v.get('what') or '').split())[:160] if promise else '',
                                   _date(v.get('due')) if promise else None, str(by)[:60], done)
            if promise and not done:                                  # the owner's own word is their task, with its day (spec 2026-10-12)
                store.task_for_promise(m['MessageId'], ' '.join(str(v.get('what') or '').split())[:160], _date(v.get('due')))
            for pid in v.get('delivers') or []:
                if str(pid) in opened: store.deliver_promise(opened[str(pid)], m['MessageId'])   # only a promise it was shown
            n += 1
        return n


def judge_text(store, body: str, subject: str = '', to: str = '', llm=None) -> dict | None:
    """One message about to leave or just sent (asks.watch_reply), judged on its words alone: {'asks_them', 'promise',
    'what', 'due'} or None when there is no brain or it did not answer. Never on a button's thread - callers background it."""
    llm = _brain(store, llm)
    if llm is None or not str(body or '').strip(): return None
    from .triage import own_words
    item = (f"[m0] sent {datetime.now().strftime('%a %d %b %Y')} to {to or 'them'} re \"{' '.join(str(subject or '').split())[:90]}\":\n"
            f"  \"{' '.join(own_words(str(body)).split())[:WORDS]}\"")
    try: v = next((x for x in _ask(llm, [item]) if str(x.get('id') or '').strip() == 'm0'), None)
    except Exception as e:
        logger.warning(f'sentjudge: could not judge the sent reply - {e}'); return None
    if not v: return None
    return {'asks_them': v.get('asks_them') is True, 'promise': v.get('promise') is True,
            'what': ' '.join(str(v.get('what') or '').split())[:160], 'due': _date(v.get('due'))}


def ready(store) -> bool:
    """Is there a brain to judge with at all? (build_llm reads the same pick.)"""
    from . import demo
    if demo.enabled(): return True
    from .llm import brain_status
    try: return bool(brain_status(store).get('ready'))
    except Exception: return False


def blind(store, days: float = DAYS) -> str:
    """What the promise and ask tracking cannot vouch for, in one plain sentence - '' when it can. Never a guess in its
    place: with no AI there is nothing to read the owner's words with, so the summary says so rather than "nothing open"."""
    # said in the calm voice (welcome.py's word rule): a chat line, not a settings page
    if not ready(store): return "Nothing reads your sent mail for me yet, so I can't keep track of what you promised or asked people for."
    n = len(store.sent_unjudged(_since(days), 500))
    return (f"I haven't read {n} of your sent message{'s' if n != 1 else ''} yet, so I can't vouch for any promise or ask in "
            f"{'them' if n != 1 else 'it'}.") if n else ''

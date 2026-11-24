"""WHAT THE OWNER READS, SAID BY ONE FUNCTION (the one-log spec, part C, 2026-11-19). His lines were built from words written for the agent:
"...and it was REFUSED - nothing went out: <git's raw output>", "run `agent-browser signup` again; a box only the owner can fill is theirs"
on a failed card, "You signed in to" over a sign-up, "triage: ..." on a row, "the AI could not tell whether..." under a held step.

`owner(event)` is the line he sees; `agent(event)` the words the agent is told. One event - {'kind': ..., facts} - feeds both, so a surface
that shows him a fact calls `owner` and never borrows the agent's sentence. What a tool printed is the agent's to read; he gets the one
line where the tool says why (`reason`).
"""
import re

# ...a tool's frame around its reason is where, never why: git's file lists and hints, PowerShell's "At line:1 char:66" and its `+ ~~~` marks
_LISTED = re.compile(r'^([ MADRCU?!]{1,2}\s+\S+|[0-9a-f]{7,40}\s.*|[^\s:]+[/\\][^\s]+)$')
_SAYS_WHY = re.compile(r'^(error|fatal|ERROR|FATAL)\b')
_FRAME = re.compile(r'^(At (line|char):\d|At [^:]+:\d+ char:\d+|\+ |hint:|remote:\s*$|To \S+$)', re.I)


# TASKUARY'S OWN FOLDERS ARE NO PLACE HE GOES (the judge's walk, 2026-11-19: "Files are in C:\Users\...\scratch\outputs\TQ-0001:" in an
# answer whose files stood under it as cards): a task's outputs folder, read off the layout Taskuary itself writes, is said as its files
_OUTPUTS = re.compile(r'''(?:[A-Za-z]:)?[\\/](?:[^\s"'`<>|\\/]+[\\/])*scratch[\\/]outputs[\\/]TQ-\d+(?:[\\/]([^\s"'`<>|\\/]*))?''')
def paths(text) -> str:
    "`text` with every path into a task's own outputs folder said as \"this task's files\" - a file in it by its own name."
    return _OUTPUTS.sub(lambda m: m.group(1) or "this task's files", str(text or ''))


def reason(said) -> str:
    "The one line where WSL, git, gh or PowerShell says why - '' when it printed nothing."
    lines = [l.strip() for l in str(said or '').splitlines() if l.strip()]
    told = [l for l in lines if not _LISTED.match(l) and not _FRAME.match(l)] or lines
    return next((l for l in told if _SAYS_WHY.match(l)), told[0] if told else '')[:240]


# WHY A STEP WAITS FOR HIS PRESS, in his words - by the gate's own reason code, never the judge's account of itself
HELD = {'out': 'it leaves this computer', 'undone': "it can't be undone", 'unsure': 'it may spend money or send your details',
        'unsure_undo': 'it may not be undoable', 'outside': "it is outside this task's own folders"}
_UNSURE = re.compile(r'^the AI could not tell whether (it can be undone|it spends money)', re.I)


def held_why(why) -> str:
    "A held step's why as he reads it: the judge's doubt said as what the step may do."
    w = ' '.join(str(why or '').split())
    if (m := _UNSURE.match(w)): return HELD['unsure_undo' if m.group(1).startswith('it can') else 'unsure']
    return w


def _cap(s: str) -> str: return s[:1].upper() + s[1:]


# A TURN THE AI PROVIDER ENDED, read off the failure's structure - its HTTP status, its error `type` - never its prose (the owner, 2026-11-19: a
# failed turn showed the provider's raw error JSON twice). He reads one plain line and what happens next; the raw text is the agent's
_STATUS = re.compile(r'\b(4\d\d|5\d\d)\b')
_TYPE = re.compile(r'''["']type["']\s*:\s*["'](\w+)["']''')
NEXT = 'write to carry on, or press Try again'
def turn_failed(said) -> str:
    from .failures import cli_quota
    r = str(said or '')
    # ...TASKUARY'S OWN SENTENCE STANDS AS IT IS (say.plain's rule): "The AI is over its limit - trying again at 12:12" and "HIPAA AI refused the
    # request - it said: ..." were read again as an unknown error, and he saw "The AI stopped on an error" over the reason (the gateway walk, 2026-11-19)
    if (own := ' '.join(r.split())) and not raw(r) and not provider_said(r): return own
    from .failures import refused
    if (why := refused(r)): return f'{why} - {NEXT}.'
    codes, types = {int(c) for c in _STATUS.findall(r)}, set(_TYPE.findall(r))
    # ...the CLI's own quota notice says when it resets; a provider's typed error that merely mentions "rate limit" is read by its type
    if (q := cli_quota(r)) and ('reset' in q.lower() or not types): return f'{q} - {NEXT} once it resets.'
    # ...AND ONE TASKUARY SAID IN WORDS IS SAID AS IT WAS (the Hydrogen walk, 2026-11-19: "the model ran out of room ... pick a non-thinking
    # model on its card" sat in the log while three turns read "The AI stopped on an error"), its card a press away
    if r.strip() and not _RAW.search(r): return own_failure(r)
    if 429 in codes or types & {'rate_limit_error', 'insufficient_quota', 'quota_exceeded'}: return f'The AI provider is over its quota or rate limit - {NEXT} in a minute.'
    if codes & {401, 403} or types & {'authentication_error', 'permission_error'}:
        return "The AI provider refused the request: its sign-in or access was turned down - check the AI's card under Connections, then " + NEXT + '.'
    if codes & {400, 404, 413, 422} or types & {'invalid_request_error', 'not_found_error'}: return f'The AI provider refused the request - {NEXT}.'
    if any(c >= 500 for c in codes) or types & {'overloaded_error', 'api_error', 'timeout'}: return f"The AI provider didn't answer - {NEXT}."
    return f'The AI stopped on an error before it finished - {NEXT}.'


_CARD_OF = re.compile(r'^([a-z][a-z0-9_]*):\s+')
def own_failure(text) -> str:
    """A failure Taskuary itself wrote in words, as he reads it: its first line, the AI card it names (a leading `<card type>: `) by its title
    and a link to it - "its card" in it becomes that link."""
    from .connectorcatalog import by_type
    t = ' '.join(str(text or '').split('\n')[0].split())
    m = _CARD_OF.match(t); card = by_type(m.group(1)) if m else None
    if not card: return names(t).rstrip('.') + '.'
    href, rest = f"#connector={m.group(1)}", t[m.end():]
    said = rest.replace('its card', f'[its card]({href})', 1) if 'its card' in rest else f"{rest} - [open its card]({href})"
    return f"{str(card.get('title') or m.group(1)).split(' - ')[0]}: {names(said).rstrip('.')}."


def owner(e: dict) -> str:
    "The line the owner sees for event `e`."
    k = e.get('kind')
    if k == 'land_refused':
        why = reason(e.get('why'))
        return f"pressed {e.get('how') or 'the button'} on the agent's work - it did not go" + (f": {why}" if why else '')
    if k == 'signin':
        site = e.get('site') or 'the site'
        if not e.get('ok'): return f"tried to {'sign up on' if e.get('signup') else 'sign in to'} {site} - it did not go in"
        return f"{'signed up on' if e.get('signup') else 'signed in to'} {site}" + (f" - saved for next time (remove it under {e['where']})" if e.get('saved') and e.get('where') else '')
    if k == 'signup_failed':
        why = ' '.join(str(e.get('why') or '').split())
        # ...who moves next is said once, by the card's own line (general.AGENT_TOLD): it read "The agent was told. The agent was told and goes on"
        # ...a status code is no words of the site's (walk 10, 2026-11-23: 'it said "the site answered with an error (HTTP 400)"'): said by its kind
        if raw(why): return f"No account was made on {e.get('site') or 'the site'}: the site answered the sign-up with an error."
        return f"No account was made on {e.get('site') or 'the site'}" + (f': it said "{why[:200]}"' if why else ': it kept its sign-up form up') + '.'
    if k == 'signup_held': return f"Make an account on {e.get('site') or 'the site'}" + (f" {e['as']}" if e.get('as') else '')
    if k == 'held':
        return held_why(e.get('why'))
    if k == 'turn_failed': return turn_failed(e.get('raw'))
    if k == 'failure': return plain(e.get('raw'), e.get('who') or 'ai')
    if k == 'reason':                                   # a reader's note on a row: its words, never its name for itself
        from .categories import route_why
        return re.sub(r'^\s*(triage|router|reader)\s*:\s*', '', route_why(e.get('text')), flags=re.I).strip()
    raise ValueError(f'say.owner: no words for {k!r}')


def step_why(output) -> str:
    "A failed step's line under its row: the one line where the tool says why, in his words when it is raw."
    r = reason(output)
    return f"Why: {plain(r, 'any') if raw(r) else r}" if r else 'It stopped without saying why.'


def agent(e: dict) -> str:
    "The words the agent is told for event `e` - what it needs to act on, the tool's output whole."
    k = e.get('kind')
    if k == 'land_refused': return f"pressed {e.get('how') or 'the button'} on the agent's work and it was REFUSED - nothing went out: {str(e.get('why') or '')[:600]}"
    if k == 'signup_failed': return str(e.get('said') or owner(e))
    return owner(e)


# A FAILURE'S TEXT, AS HE READS IT ON ANY SURFACE (a toast, the phone, a queued start's line, the bell): a line Taskuary wrote in words is kept;
# one that carries a tool's raw output - a JSON body, a traceback, an exception's class, a status code - is said by what kind
# of failure it is, read off that structure, never shown as it came
_RAW = re.compile(r'''[{\[]\s*["']|Traceback|File "|\b[A-Z]\w*(Error|Exception)\b:?|\bErrno\b|\b(HTTP|[Ss]tatus(?: code)?|[Ee]rror(?: code)?)\W{0,3}[45]\d\d\b|\b[45]\d\d (Client|Server) Error''')
def raw(text) -> bool: return bool(_RAW.search(str(text or '')))
def provider_said(text) -> bool: return bool(_STATUS.search(str(text or '')) or _TYPE.search(str(text or '')))


def plain(text, who: str = 'ai') -> str:
    """`text` in his words: Taskuary's own sentence as it is (its first line), else the kind of failure - `who` 'ai' for an AI provider's,
    'service' for a connected service's (channels.plain_failure, the one road a card's error takes), anything else as itself."""
    t = ' '.join(str(text or '').split('\n')[0].split())
    if not t: return ''
    if not raw(text):
        return names(t)
    if who == 'service':
        s = plain_failure(RuntimeError(str(text)))
        return s if not raw(s) else 'The service answered with an error.'
    from .failures import classify, refused
    # ...a start or a press that failed: the one road a failure's sentence takes (failures.classify) - but a provider's own status or error
    # type is the provider's, said by that structure below (walk 4: "API Error: 529" read "Something went wrong on this computer")
    if who in ('start', 'any') and (not provider_said(text) or refused(str(text))):
        s = classify(str(text)).get('sentence') or ''
        if s and not raw(s): return s
        # ...and where it names no provider's status, no AI is to blame: said as a failure of its own, its text in the log
        return "The agent couldn't start - Taskuary kept the details in its log." if who == 'start' else "That didn't work - Taskuary kept the details in its log."
    s = turn_failed(text).split(' - ')[0].split(':')[0].rstrip('.') + '.'
    # ...a press or a page answered by some other service is never blamed on the AI
    return s.replace('The AI provider', 'The service it called').replace('The AI stopped', 'It stopped') if who == 'any' else s


# ── the readings each surface had of its own, folded here (one road): a path's folder name, a service's failure, an AI's ──────────────
# A failure is said to the owner as it is stored: "422: I could not tell..." wore FastAPI's status prefix, and a refused
# hand-off printed the full path of a checkout on this machine into the chat (2026-09-29 audit). The folder's own name
# says which checkout; the rest of the path says nothing to the owner and does not belong in a chat.
_PATH = re.compile(r'(?<![\w/:])(?:[A-Za-z]:[\\/]|/(?:Users|home|tmp|var|opt)/)[^\s\'",;)]+')


def names(e) -> str:
    detail = getattr(e, 'detail', None)
    s = str(detail if isinstance(detail, str) else e)
    s = re.sub(r'^\d{3}:\s*', '', s)
    def name(m):
        path = m.group(0).rstrip('.')                        # a sentence's full stop is not part of the folder
        return path.replace('\\', '/').rstrip('/').rsplit('/', 1)[-1] + m.group(0)[len(path):]
    return _PATH.sub(name, s)


# WHAT A FAILED TEST SAYS. The card used to print the exception as it came - a socket's
# "[Errno 11001] getaddrinfo failed", a server's "401 Client Error: Unauthorized for url: ..." -
# which tells the owner something broke and not what to do next. The common failures get a
# sentence with the next step in it; anything else keeps its own words, which are usually ours.
# LastError keeps the raw text: problems.lapsed() reads it to spot an expired sign-in.
_DNS = re.compile(r'getaddrinfo failed|Name or service not known|nodename nor servname|Temporary failure in name resolution|NameResolutionError|No address associated', re.I)
_TIMEOUT = re.compile(r'timed? ?out|ReadTimeout|ConnectTimeout', re.I)
_REFUSED = re.compile(r'Connection refused|actively refused|ECONNREFUSED|WinError 10061', re.I)
# ...a connection that dropped part-way through a read, as the socket, imaplib and requests each word it
_DROPPED = re.compile(r'Connection aborted|Connection reset|RemoteDisconnected|socket error|EOF occurred|Broken pipe|IncompleteRead', re.I)
_AUTH_WORDS = re.compile(r'\b(invalid_auth|not_authed|token_revoked|token_expired|account_inactive|bad credentials|invalid[_ ]api[_ ]key|incorrect api key)\b', re.I)
def _status(e):
    r = getattr(e, 'response', None)
    code = getattr(r, 'status_code', None) or getattr(e, 'code', None) or getattr(e, 'status_code', None)
    if isinstance(code, int): return code
    # requests/httpx spell it "401 Client Error: Unauthorized for url" when only the text survives a re-raise
    m = re.search(r'\b(401|403|429|5\d\d)\b[^\n]{0,20}(?:Client Error|Server Error|Unauthori[sz]ed|Forbidden|Too Many Requests)', str(e), re.I)
    if m: return int(m.group(1))
    # ...and an API that answers 200 with its own word for it: Slack's "invalid_auth" was printed to the owner as it came
    return 401 if _AUTH_WORDS.search(str(e)) else None


def plain_failure(e: Exception, signin: bool = False) -> str:
    raw = str(e)
    from . import googlecal, msauth
    if msauth.LAPSED in raw or googlecal.lapsed(raw): return raw[:500]      # already says what to do: sign in again
    code = _status(e)
    # ...the service's own trouble (a Microsoft outage, 2026-11-12): the raw line put its URL, the mailbox in it, on the card and the
    # bell - and there is nothing on the card to change
    if isinstance(code, int) and 500 <= code < 600:
        return (f"The service is having trouble on its side (it answered {code}). Nothing here needs changing - "
                "it is tried again on every poll, and what came in meanwhile is read once it is back.")
    if code == 429: return ("The service asked Taskuary to slow down (too many requests at once). Nothing is lost - it is tried again on "
                            "every poll, and the rest is read then.")
    # ...a sign-in card has no key to paste: its sign-in still renews (a lapsed one says LAPSED above), so the service refused the read
    if code == 401 and signin: return ("Microsoft refused the read though the sign-in still works - usually trouble on its side, and it "
                                       "is tried again on every poll. If it lasts, sign in again on the card.")
    if code == 401: return ("The service turned the key or password down. Check it is the current one - "
                            "paste it again if it was changed or has expired - then Save and Test again.")
    if code == 403: return ("The service knows this account but would not let it in. The key may not have permission "
                            "for this, or an administrator has to allow it.")
    if _DNS.search(raw): return ("The server's address could not be found. Check the server name for typos, "
                                 "and that this computer is online.")
    if isinstance(e, TimeoutError) or _TIMEOUT.search(raw):
        return ("The server did not answer in time. It may be down, or this network may block it - try again in a minute.")
    # setup has one box for the server and none for a port: the name is what can be checked, and IT knows the rest (2026-10-17)
    if _REFUSED.search(raw): return ("The server turned the connection away. Check the server name, or ask your IT team "
                                     "for the right server and port.")
    # ...a read cut off part-way, or a server never reached (failures._UNREACHED, the road the run cards read): the socket's words
    # and requests' repr - the folder, the host, the mailbox in its URL - reached the card and the bell with no word of what happens next
    from .failures import _UNREACHED
    if _DROPPED.search(raw): return ("The connection to the server dropped part-way through the read. Nothing already in is lost, "
                                     "and it is tried again on every poll.")
    if _UNREACHED.search(raw): return ("The server could not be reached - check this computer is online. It is tried again on every poll.")
    # ...and any other answer as requests words it, without the address it was asked at - the mailbox is in that URL
    return re.sub(r' for url: \S+', '', raw)[:500] or type(e).__name__


# A FAILING AI IN PLAIN WORDS: the raw exception ("'claude' not found on PATH", "not JSON") stood on the Advisor's line, and stayed
# there days after (the non-coder audit, 2026-10-17). Matched on what the SYSTEM said, never on anything the owner typed.
_AI_ERRS = ((r'not found on path|no such file|is not recognized|cannot find the file', "it isn't installed on this computer any more"),
            (r'json|verdict|parse|could not be read', "its answers came back in a form Taskuary can't read"),
            (r'timed? ?out|took too long|deadline', 'it took too long to answer'),
            (r'\b(401|403)\b|unauthori[sz]ed|forbidden|api key|sign[ -]?in|log ?in|expired|credential', 'it needs you to sign in again, or its key stopped working'),
            (r'\b429\b|rate.?limit|quota|usage limit|credit|billing|insufficient|cap reached', 'it reached its usage limit or ran out of credit'),
            (r'connect|network|getaddrinfo|resolve|unreachable|offline', "Taskuary couldn't reach it - check this computer is online"))


def plain_ai_error(raw: str) -> str:
    low = str(raw or '').lower()
    said = next((said for pat, said in _AI_ERRS if re.search(pat, low)), 'it stopped answering') if low.strip() else ''
    # ...and an answer it could not read says what came back (llm.unreadable): "a form Taskuary can't read" alone left nothing to go on
    came = re.search(r'the AI (sent back|answered) [^()]*', str(raw or ''))
    return f"{said}: {came.group(0).strip()}" if came and said == _AI_ERRS[1][1] else said


def said(e) -> str:
    "An exception as a line of the chat says it (say.plain): a tool's raw text never reaches him there."
    d = getattr(e, 'detail', None)
    return plain(d if isinstance(d, str) else str(e), 'any')

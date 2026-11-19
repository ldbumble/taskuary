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
        return f"No account was made on {e.get('site') or 'the site'}" + (f': it said "{why[:200]}"' if why else ': it kept its sign-up form up') + '. The agent was told.'
    if k == 'held':
        return held_why(e.get('why'))
    if k == 'reason':                                   # a reader's note on a row: its words, never its name for itself
        from .categories import route_why
        return re.sub(r'^\s*(triage|router|reader)\s*:\s*', '', route_why(e.get('text')), flags=re.I).strip()
    raise ValueError(f'say.owner: no words for {k!r}')


def agent(e: dict) -> str:
    "The words the agent is told for event `e` - what it needs to act on, the tool's output whole."
    k = e.get('kind')
    if k == 'land_refused': return f"pressed {e.get('how') or 'the button'} on the agent's work and it was REFUSED - nothing went out: {str(e.get('why') or '')[:600]}"
    if k == 'signup_failed': return str(e.get('said') or owner(e))
    return owner(e)

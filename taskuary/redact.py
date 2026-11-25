"""Take credentials - and SSNs and dates of birth - out of anything on its way to a model.

The leak this closes is on the FIRST prompt, not in stored history: a colleague mails an API
key, triage reads that mail, and `agents.task_context` writes the body verbatim into an agent
prompt that goes to Anthropic, OpenAI or Azure. Scrubbing happens at the doors text leaves by -
llm.build_llm (a call, an API agent's every step, its search, a CLI's warmed instructions),
agents.run_cli, terminal (a pane's seed, every line typed into a session), acp and clipool's own
wire, the tool server's answers (agenttools.rpc), every API answer to an agent's session
(server.token_gate) and the context files Taskuary writes for an agent to read - and NOT at the database: a
`message` row is a mirror of the owner's inbox, and a vendor's one-time portal code is the whole
point of the mail it arrived in.

Deterministic on purpose. An AI cannot decide what to hide from an AI - by the time it judges,
the credential is already in a prompt - and a classifier that is 97% right leaks the rest
forever. Rules are exhaustive where they match and honest where they do not: this catches
credentials that have a SHAPE; a password merely SAID ("the wifi password is bluefish17") is taken only from what is shown (shown).

The placeholder is LABELLED (`[redacted:aws-key]`, not a blank) because the drafter often has to
write "I've rotated the key you sent" without ever seeing it; a bare hole makes a model guess at
what is missing. `MARK` is what outbound checks for: a placeholder in a draft is a bug, not a send.

Over-redaction is a bug too. A git SHA is 40 hex characters, so there is deliberately no
catch-all "long hex string" rule here. The chat scrub used to have one and it stored
"revert da8dae00..." as "revert [redacted]"; `concierge.redact` now comes here instead. A
random-looking value is taken only when its own line says it is a secret.

SSNs AND DATES OF BIRTH (the owner, 2026-11-25: "never sent to endpoints, even HIPAA AI") go the
same way, at the same doors: an SSN by its shape (123-45-6789, 123 45 6789) or as nine digits its
label names (SSN, social security number); a date of birth only where a label says it is one (DOB,
date of birth, born, birthday) - a bare date is a meeting, an invoice, a deadline, and stays.
`secrets` is the credential half alone, for what is SHOWN or KEPT here (a chat line, a title, an
error on his screen): his store and his screen keep the number, only what leaves for a model loses
it. The cost is real: an agent cannot type an SSN into a form it never saw. What no door here can
reach - a CLI reading a file off disk with its own Read tool, a picture of a card - needs the
gateway's own guardrail.
"""
import re

MARK = '[redacted:'


def _ph(label): return f'[redacted:{label}]'


# Ordered: the block and the URI rules run before the prefix rules so a key inside one is not
# half-replaced, and the labelled-value rule runs last on whatever is still legible.
_RULES = [
    (re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----', re.S),
     lambda m: _ph('private-key')),
    # keep the scheme, user and host: a checkout URL stays readable, the password does not
    (re.compile(r'(?P<head>[a-z][a-z0-9+.\-]*://[^\s:/@]+:)(?P<pw>[^\s/@]+)(?=@)'),
     lambda m: m.group('head') + _ph('url-credentials')),
    (re.compile(r'(?i)\b(?P<k>password|pwd)\s*=\s*(?P<v>[^;\s]+)'),
     lambda m: f"{m.group('k')}={_ph('password')}"),
    # JSON object keys the connectors API used to return verbatim. The labelled-value rule below
    # wants `client_secret: foo`, not `"client_secret": "foo"`.
    (re.compile(r'(?P<k>"(?:client_secret|google_client_secret|google_refresh_token|refresh_token|'
                r'api_key|app_key|secret_key|secret_access_key|private_key|access_key|password)"'
                r'\s*:\s*")(?P<v>[^"]{6,})"'),
     lambda m: m.group('k') + _ph('secret') + '"'),
    (re.compile(r'\bAKIA[0-9A-Z]{12,}\b'), lambda m: _ph('aws-key')),
    (re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}\b'), lambda m: _ph('github-token')),
    (re.compile(r'\bxox[abpr]-[A-Za-z0-9-]{10,}'), lambda m: _ph('slack-token')),
    (re.compile(r'\b(?:sk|rk)-[A-Za-z0-9_\-]{16,}'), lambda m: _ph('api-key')),
    (re.compile(r'\bglpat-[A-Za-z0-9_\-]{16,}'), lambda m: _ph('api-key')),
    (re.compile(r'\bya29\.[A-Za-z0-9_\-]{20,}'), lambda m: _ph('api-key')),
    (re.compile(r'\bey[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}'),
     lambda m: _ph('jwt')),
    # the only rule that judges an ORDINARY-looking value, and only because its line named it
    (re.compile(r'''(?i)(?P<k>\b(?:secret|token|passwd|password|api[_ -]?key|apikey|access[_ -]?key'''
                r'''|private[_ -]?key|client[_ -]?secret|refresh[_ -]?token)\b\s*[:=]\s*)'''
                r'''(?P<q>["']?)(?P<v>[^\s"',;]{6,})'''),
     lambda m: m.group('k') + m.group('q') + _ph('secret')),
]


def secrets(text) -> str:
    "Every credential-shaped thing in `text`, replaced by a labelled placeholder - what is shown or kept HERE (scrub is what leaves)."
    out = str(text or '')
    for rx, sub in _RULES: out = rx.sub(sub, out)
    return out


_SSN_LABEL = r'(?:ssn|ss\#|s\.s\.n\.?|social[\s_-]*security(?:[\s_-]*(?:number|num|no\.?|\#))?|social)'
_MON = r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?'
_DATE = (rf'(?:\d{{4}}[-/.]\d{{1,2}}[-/.]\d{{1,2}}|\d{{1,2}}[-/.]\d{{1,2}}[-/.]\d{{2,4}}'
         rf'|{_MON}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MON}(?:,?\s+\d{{4}})?)(?![\w/])')
_DOB_LABEL = r'(?:d\.?o\.?b\.?|date[\s_-]*of[\s_-]*birth|birth[\s_-]*date|birthday|born(?:\s+on)?)'
# between a label and its value: a colon, quotes (a JSON key), "is", "on", "of" - a few characters, never a sentence away
_SEP = r'(?P<sep>[\s"\':=#()\-–]*(?:(?:is|was|on|of|date)\b[\s"\':=\-]*){0,2})'
_PII = [
    # the label first, so "SSN: 123456789" keeps its label and the shape below finds nothing left
    (re.compile(rf'(?i)(?P<k>\b{_SSN_LABEL}){_SEP}\d{{3}}[\s.-]?\d{{2}}[\s.-]?\d{{4}}(?![\w-])'), lambda m: m.group('k') + m.group('sep') + _ph('ssn')),
    (re.compile(r'(?<![\w-])\d{3}([- ])\d{2}\1\d{4}(?![\w-])'), lambda m: _ph('ssn')),       # one separator, the same both times
    (re.compile(rf'(?i)(?P<k>\b{_DOB_LABEL})(?![a-z]){_SEP}{_DATE}'), lambda m: m.group('k') + m.group('sep') + _ph('date-of-birth')),
]


def scrub(text) -> str:
    "`text` as it may leave for a model: every credential (secrets), SSN and labelled date of birth, a labelled placeholder."
    out = secrets(text)
    for rx, sub in _PII: out = rx.sub(sub, out)
    return out


def scrub_all(o):
    "Every string value in a JSON-shaped value scrubbed: an answer read as data stays the same shape."
    if isinstance(o, str): return scrub(o)
    if isinstance(o, dict): return {k: scrub_all(v) for k, v in o.items()}
    if isinstance(o, list): return [scrub_all(v) for v in o]
    return o


# SAID, NOT SHAPED: "my password is Hunter2!x9", "username northwind, password chirp-pass". A prompt keeps these - the agent he gave a
# password to signs in with it - but a line drawn for him or sent to his phone (a task's title, the rail, the phone) is not a prompt, and a
# title copied his sentence, password and all, onto the rail and the phone (walk 19). The value must hold a digit or a sign, so "password
# reset" stays a title.
_SAID = re.compile(r"""(?i)(?P<k>\b(?:password|passwd|passcode|pwd|pin)\b(?:\s+(?:is|was)\b)?\s*[:=]?\s*)"""
                   r"""(?![=:\[])(?P<v>(?=[^\s,;)\]"']*[^A-Za-z\s,;)\]"'])[^\s,;)\]"']{4,})""")


def shown(text) -> str:
    "`text` as it may be SHOWN - on a title, the rail, the phone: every credential scrub takes, and a password said in words."
    return _SAID.sub(lambda m: m.group('k') + _ph('password'), secrets(text))


def holds_placeholder(text) -> bool: return MARK in str(text or '')

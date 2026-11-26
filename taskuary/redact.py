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
it. The cost is real: an agent cannot type an SSN into a form it never saw. A file an AI card's
agent opens with its harness CLI's own shell leaves through relay.py, scrubbed there (scrub_body). What no door
here can reach - his own CLI plan reading a file off disk with its own Read tool, a picture of a card - needs
the provider's own guardrail.
"""
import functools, re

MARK = '[redacted:'


def _ph(label): return f'[redacted:{label}]'


# WHERE A WORD STARTS, ALSO IN TEXT THAT IS JSON (round 5): a newline serialized is the two characters \n, so the letter n stood where a
# line began and no rule that opens on a word's edge saw a key, an SSN or a label at a line's start in a tool's answer or a file's rows.
# So a rule with a left edge has a twin that opens on the escape itself - run only over text that holds a backslash, and found by it
_ESC = r'(?P<esc>\\[nrt])'
def _rule(body, sub, edge=None, flags=0):
    "(the rule, its twin for a line's start inside serialized text or None, what takes the match's place)"
    return re.compile((edge or '') + body, flags), re.compile(_ESC + body, flags) if edge else None, sub


def _run(rules, out: str) -> str:
    esc = '\\' in out
    for rx, twin, sub in rules:
        out = rx.sub(sub, out)
        if esc and twin: out = twin.sub(lambda m, sub=sub: m.group('esc') + sub(m), out)
    return out


_W = r'\b'
# Ordered: the block and the URI rules run before the prefix rules so a key inside one is not
# half-replaced, and the labelled-value rule runs last on whatever is still legible.
_RULES = [
    _rule(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----', lambda m: _ph('private-key'), flags=re.S),
    # keep the scheme, user and host: a checkout URL stays readable, the password does not
    _rule(r'(?P<head>[a-z][a-z0-9+.\-]*://[^\s:/@]+:)(?P<pw>[^\s/@]+)(?=@)', lambda m: m.group('head') + _ph('url-credentials')),
    _rule(r'(?P<k>password|pwd)\s*=\s*(?P<v>[^;\s]+)', lambda m: f"{m.group('k')}={_ph('password')}", _W, re.I),
    # JSON object keys the connectors API used to return verbatim. The labelled-value rule below
    # wants `client_secret: foo`, not `"client_secret": "foo"`.
    _rule(r'(?P<k>"(?:client_secret|google_client_secret|google_refresh_token|refresh_token|'
          r'api_key|app_key|secret_key|secret_access_key|private_key|access_key|password)"'
          r'\s*:\s*")(?P<v>[^"]{6,})"', lambda m: m.group('k') + _ph('secret') + '"'),
    _rule(r'AKIA[0-9A-Z]{12,}\b', lambda m: _ph('aws-key'), _W),
    _rule(r'gh[pousr]_[A-Za-z0-9]{20,}\b', lambda m: _ph('github-token'), _W),
    _rule(r'xox[abpr]-[A-Za-z0-9-]{10,}', lambda m: _ph('slack-token'), _W),
    _rule(r'(?:sk|rk)-[A-Za-z0-9_\-]{16,}', lambda m: _ph('api-key'), _W),
    _rule(r'glpat-[A-Za-z0-9_\-]{16,}', lambda m: _ph('api-key'), _W),
    _rule(r'ya29\.[A-Za-z0-9_\-]{20,}', lambda m: _ph('api-key'), _W),
    _rule(r'ey[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}', lambda m: _ph('jwt'), _W),
    # the only rule that judges an ORDINARY-looking value, and only because its line named it
    _rule(r"""(?P<k>(?:secret|token|passwd|password|api[_ -]?key|apikey|access[_ -]?key"""
          r"""|private[_ -]?key|client[_ -]?secret|refresh[_ -]?token)\b\s*[:=]\s*)"""
          r"""(?P<q>["']?)(?P<v>[^\s"',;]{6,})""", lambda m: m.group('k') + m.group('q') + _ph('secret'), _W, re.I),
]


def secrets(text) -> str:
    "Every credential-shaped thing in `text`, replaced by a labelled placeholder - what is shown or kept HERE (scrub is what leaves)."
    return _run(_RULES, str(text or ''))


_SSN_LABEL = r'(?:ssn|ss\#|s\.s\.n\.?|social[\s_-]*security(?:[\s_-]*(?:number|num|no\.?|\#))?|social)'
_MON = r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?'
# ...a date as a form holds it too, the digits run together (010590, 01051990, 19900105): only ever read beside its label
_DATE = (rf'(?:\d{{4}}[-/.]\d{{1,2}}[-/.]\d{{1,2}}|\d{{1,2}}[-/.]\d{{1,2}}[-/.]\d{{2,4}}'
         rf'|{_MON}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MON}(?:,?\s+\d{{4}})?'
         rf'|\d{{8}}|\d{{6}})(?![\w/])')
_DOB_LABEL = r'(?:d\.?o\.?b\.?|date[\s_-]*of[\s_-]*birth|birth[\s_-]*date|birthday|born(?:\s+on)?)'
# between a label and its value: a colon, quotes (a JSON key - escaped, where the JSON is itself inside a string), a line's end, "is", "on",
# "of" - a few characters, never a sentence away
_GAP = r'(?:\\[nrt]|[\s"\':=#()\-–\\])*'
_SEP = rf'(?P<sep>{_GAP}(?:(?:is|was|on|of|date)\b{_GAP}){{0,2}})'
_L = r'(?<![A-Za-z0-9])'           # a label's left edge: a field's name may lead up to it (patient_ssn, member_dob)
_PII = [
    # the label first, so "SSN: 123456789" keeps its label and the shape below finds nothing left
    _rule(rf'(?P<k>{_SSN_LABEL}){_SEP}\d{{3}}[\s.-]?\d{{2}}[\s.-]?\d{{4}}(?![\w-])', lambda m: m.group('k') + m.group('sep') + _ph('ssn'), _L, re.I),
    _rule(r'\d{3}(?P<s>[- ])\d{2}(?P=s)\d{4}(?![\w-])', lambda m: _ph('ssn'), r'(?<![\w-])'),       # one separator, the same both times
    _rule(rf'(?P<k>{_DOB_LABEL})(?![a-z]){_SEP}{_DATE}', lambda m: m.group('k') + m.group('sep') + _ph('date-of-birth'), _L, re.I),
]


def scrub(text) -> str:
    "`text` as it may leave for a model: every credential (secrets), SSN and labelled date of birth, a labelled placeholder."
    return _run(_PII, secrets(text))


def scrub_parts(c):
    """A message's content as it may leave: a string scrubbed, or every string of each part of a list - its words, a tool's answer held
    inside it, a file's text. A part that carries bytes (a picture, a document as base64) goes as it is: no rule here reads a picture."""
    if isinstance(c, list): return [p if isinstance(p, dict) and _BYTES & p.keys() else scrub_all(p) for p in c]
    return scrub(c)


# the keys a part's bytes ride under, on the wires Taskuary and a card's harness speak (chat completions, Responses): a picture, a document
# as base64, and a provider's own sealed reasoning - a rule that matched inside one would hand back bytes it cannot read
_BYTES = {'image_url', 'source', 'file', 'input_audio', 'file_data', 'encrypted_content'}


KEYED = 256        # a value this short is also read beside its own key (_leaf): an SSN, a date - never a page of text twice


@functools.lru_cache(maxsize=4096)
def _names_secret(name: str) -> bool:
    "Does a field of this name hold a credential, by the rule for one in JSON (\"client_secret\": ...)? Asked once a name."
    import json
    return MARK in secrets(json.dumps({name: 'x' * 8}))


def _leaf(k, v):
    """One value of a JSON-shaped thing, under its key. A string is scrubbed - as the JSON it holds, where it holds some (scrub_json). And
    THE LABEL MAY BE THE KEY (round 5): {"ssn": "078051120"}, {"dob": "010590"} and {"client_secret": ...} left for a model whole, because a
    value read alone has no label - so it is read once more as the field it is, by the same rules, as serialized text always was."""
    import json
    if isinstance(v, bool) or not isinstance(v, (str, int, float)): return v
    out = scrub_json(v) if isinstance(v, str) else v
    if out != v or not k: return out
    name, s = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '_', str(k)), str(v)    # memberDob reads as member_dob does
    if len(s) > KEYED: return _ph('secret') if _names_secret(name) else out
    try: got = json.loads(scrub(json.dumps({name: s}, ensure_ascii=False)))[name]
    except (ValueError, KeyError, TypeError): return out
    return got if got != s else out


def scrub_all(o, k: str = ''):
    "Every value in a JSON-shaped value scrubbed, each under its key (_leaf): an answer read as data stays the same shape."
    if isinstance(o, dict): return {a: scrub_all(v, a) for a, v in o.items()}
    if isinstance(o, list): return [scrub_all(v, k) for v in o]
    return _leaf(k, o)


def scrub_json(s):
    """A string that holds JSON (a tool call's arguments, a tool's answer), scrubbed as the data it is - decoded, so a line's start is a
    line's start - and still JSON; any other string as scrub does it."""
    import json
    if str(s)[:1] not in ('{', '['): return scrub(s)
    try: o = json.loads(s)
    except (TypeError, ValueError): return scrub(s)
    return s if (out := scrub_all(o)) == o else json.dumps(out, ensure_ascii=False)


def scrub_body(o, hits: list = None, k: str = ''):
    """A whole request on its way to a model (relay.py), whatever its wire: every value scrubbed under its key (_leaf - a call's arguments,
    a tool's answer as the JSON they are), what rides under a bytes key as it is. `hits` is handed the key of each value that changed - a
    count, never the text."""
    if isinstance(o, dict): return {a: v if a in _BYTES else scrub_body(v, hits, a) for a, v in o.items()}
    if isinstance(o, list): return [scrub_body(v, hits, k) for v in o]
    out = _leaf(k, o)
    if hits is not None and out != o: hits.append(k)
    return out


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

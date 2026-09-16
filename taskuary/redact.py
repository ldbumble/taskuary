"""Take credentials out of anything on its way to a model.

The leak this closes is on the FIRST prompt, not in stored history: a colleague mails an API
key, triage reads that mail, and `agents.task_context` writes the body verbatim into a coder
prompt that goes to Anthropic, OpenAI or Azure. Scrubbing happens at the three doors a prompt
leaves by (llm.build_llm, agents.run_cli, terminal.Term.seed) and NOT at the database: a
`message` row is a mirror of the owner's inbox, and a vendor's one-time portal code is the whole
point of the mail it arrived in.

Deterministic on purpose. An AI cannot decide what to hide from an AI - by the time it judges,
the credential is already in a prompt - and a classifier that is 97% right leaks the rest
forever. Rules are exhaustive where they match and honest where they do not: this catches
credentials that have a SHAPE, and will never catch "the wifi password is bluefish17".

The placeholder is LABELLED (`[redacted:aws-key]`, not a blank) because the drafter often has to
write "I've rotated the key you sent" without ever seeing it; a bare hole makes a model guess at
what is missing. `MARK` is what outbound checks for: a placeholder in a draft is a bug, not a send.

Over-redaction is a bug too. A git SHA is 40 hex characters, so there is deliberately no
catch-all "long hex string" rule here. The chat scrub used to have one and it stored
"revert da8dae00..." as "revert [redacted]"; `concierge.redact` now comes here instead. A
random-looking value is taken only when its own line says it is a secret.
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


def scrub(text) -> str:
    """Every credential-shaped thing in `text`, replaced by a labelled placeholder."""
    out = str(text or '')
    for rx, sub in _RULES: out = rx.sub(sub, out)
    return out


def holds_placeholder(text) -> bool: return MARK in str(text or '')

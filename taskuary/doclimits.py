"""How much of each operator document reaches the model that reads it - the Docs editor's meter.

The numbers are not kept here: each is the constant the prompt builder itself cuts with (terminal.DOC_CHARS for every
profile document, terminal.AGENT_CHARS, triage.SOUL_CHARS ...), so the meter and the prompt cannot disagree. GET
/api/doc/{name} returns limit(store, name) as `limit`; the editor counts what is typed against it (website/src/docMeter.js).
`flat` says the count is of the document as a session receives it (terminal.flatten_rules: headings unmarked, one space
between everything), not of the file. `past` is what really happens to text past the limit, in the words the meter shows.
A document no reader cuts (TRIAGE.md is triage's whole system prompt, DIGEST.md is written for the owner) has no limit.
"""

CUT, WHOLE, SECTIONS = 'the end is cut off', 'still read whole, but long', 'whole sections are left out'


def fixed():
    "name -> (chars, flat, reader, past) for the documents that are not profiles"
    from . import counsel, learned_cut, responder, terminal, triage
    return {'soul': (triage.SOUL_CHARS, False, 'triage and drafts', CUT), 'job': (triage.JOB_CHARS, False, 'triage', CUT),
            'style': (responder.STYLE_CHARS, False, 'drafts', CUT), 'counsel': (counsel.BUDGET, False, 'the assistant', WHOLE),
            'agent': (terminal.AGENT_CHARS, True, 'every agent', CUT), 'learned': (learned_cut.WHOLE_CAP, False, 'its readers', SECTIONS)}


def is_profile_doc(store, name: str) -> bool:
    from .agents import profile_document
    if name == 'coding': return True
    try: return any(profile_document(store, a['Name']) == name for a in store.list_agents(active_only=False))
    except Exception: return False


def limit(store, name: str):
    "{chars, flat, reader, past} for one document, or None when nothing cuts it"
    from . import terminal
    got = fixed().get(name) or ((terminal.DOC_CHARS, True, 'the agent', CUT) if is_profile_doc(store, name) else None)
    return dict(zip(('chars', 'flat', 'reader', 'past'), got)) if got else None

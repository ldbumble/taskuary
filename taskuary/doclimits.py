"""How much of each operator document reaches the model that reads it - the Docs editor's meter.

The numbers are not kept here: each is the constant the prompt builder itself cuts with (triage.SOUL_CHARS,
responder.STYLE_CHARS ...), so the meter and the prompt cannot disagree. GET
/api/doc/{name} returns limit(store, name) as `limit`; the editor counts what is typed against it (website/src/docMeter.js).
`flat` says the count is of the document as a session receives it, flattened, not of the file. `past` is what really happens to text past the limit, in the words the meter shows.
A document no reader cuts (TRIAGE.md is triage's whole system prompt, DIGEST.md is written for the owner) has no limit.
"""

CUT, WHOLE, SECTIONS = 'the end is cut off', 'still read whole, but long', 'whole sections are left out'


def fixed():
    "name -> (chars, flat, reader, past) for the documents a reader cuts"
    from . import counsel, lookout, memory, responder, selfclose, triage
    return {'soul': (triage.SOUL_CHARS, False, 'triage and drafts', CUT), 'job': (triage.JOB_CHARS, False, 'triage', CUT),
            'style': (responder.STYLE_CHARS, False, 'drafts', CUT), 'counsel': (counsel.BUDGET, False, 'the assistant', WHOLE),
            'learned': (memory.WHOLE_CAP, False, 'its readers', SECTIONS), selfclose.AGENTS_DOC: (selfclose.AGENTS_CHARS, True, 'every agent', CUT),
            lookout.ADVISOR_DOC: (lookout.ADVISOR_CHARS, False, 'the Advisor', CUT)}


def limit(store, name: str):
    "{chars, flat, reader, past} for one document, or None when nothing cuts it"
    got = fixed().get(name)
    return dict(zip(('chars', 'flat', 'reader', 'past'), got)) if got else None

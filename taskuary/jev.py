"""TypeSafe's Jev - a decision model, not a brain.

Unstructured state in, typed answers with calibrated probabilities out, in one parallel forward
pass. It cannot emit text AT ALL, which is exactly why it suits a routing judge (four yes/nos about
a run) and exactly why it must never reach a brain picker: chosen as the Assistant's brain it would
have nothing to say. `llm.AI_TYPES` is what populates those pickers, and `typesafe` is kept out of
it on purpose.

Its training optimises CALIBRATION rather than agreement - a 0.7 is meant to be right seven times in
ten - so the probability is worth recording even though the judge only needs the boolean.
"""
import json

from . import llm as llm_mod, redact

API = 'https://api.typesafe.ai/v1/systemone'
MODEL = 'jev-latest'
YES = 0.5          # a probability is not a verdict until something picks a line; this is that line
# What "no" looks like, described rather than negated. The caller supplies the `true` criterion; this
# is the other side of it, and it has to describe a state the model can recognise on its own.
FALSE = 'Nothing in the state described above matches that.'


def ask(key: str, state: str, questions: dict, timeout: int = 20) -> dict:
    """Answer every question about one state, in one call: {name: (chose_yes, probability)}.

    `questions` is {name: (instructions, criterion)}. RAISES on anything that is not a clean answer -
    a caller that wants a failure to mean something must say so itself, because the only honest
    alternative here is inventing an answer nobody gave.
    """
    if not questions: return {}
    if not key: raise RuntimeError('no TypeSafe API key saved - paste one under Credentials')
    # Every OTHER hosted call in the app is scrubbed at one seam - llm.build_llm wraps the brain it
    # returns (_Scrubbed). This road does not go through it, so it scrubs at its own door: a report
    # that came back carrying a password must not post one to a third party just because the thing
    # reading it answers in probabilities rather than words.
    state = redact.scrub(state)
    body = {'model': MODEL, 'state': state,
            'questions': {n: {'type': 'noul', 'instructions': i,
                              # the owner's own sentence is the whole `true` criterion, word for word,
                              # so what the card shows is what is sent. `false` was once that sentence
                              # with "not this:" glued in front, which describes nothing - and a model
                              # asked to weigh a description against its own negation answers near 0.5
                              # whatever the state says (measured on real runs, 2026-09-17).
                              'criteria': {'true': redact.scrub(c), 'false': FALSE}}
                          for n, (i, c) in questions.items()}}
    r = llm_mod.post_retrying(API, {'Authorization': f'Bearer {key}',
                                    'Content-Type': 'application/json'}, body, timeout)
    if r.status_code != 200:
        raise RuntimeError(f'TypeSafe answered {r.status_code}{llm_mod.tried(r)}: {str(r.text)[:200]}')
    try: answers = (r.json() or {}).get('answers') or {}
    except (ValueError, json.JSONDecodeError) as e:
        raise RuntimeError(f'TypeSafe sent something that is not JSON: {e}')
    out = {}
    for name in questions:
        got = answers.get(name) or {}
        p = got.get('noul')
        if not isinstance(p, (int, float)) or isinstance(p, bool):
            raise RuntimeError(f'TypeSafe did not answer {name!r} - got {sorted(answers) or "nothing"}')
        out[name] = (float(p) >= YES, float(p))
    return out


# One boolean per verdict, argmax'd: `noul` answers yes/no, triage has three intents and three kinds. Every question is asked
# OF THE OWNER'S OWN JUDGEMENT - the state carries their profile (SOUL), what was learned from their past verdicts (LEARNED) and
# the verdicts on related mail (PAST VERDICTS) - so "would you make this a task" is answered the way they would, not in general.
_OF = ' Judge as this owner would, using OWNER PROFILE, LEARNED and PAST VERDICTS in the state above: where a past verdict plainly fits, follow it.'
TRIAGE = {
    'task':       ('Would the owner make this message a task?' + _OF,
                   'Something must be done beyond writing back - a system to change, something to produce, chase or look up that takes more than a sentence - and the owner is the one it falls to.'),
    'reply_only': ('Would the owner answer this with a short reply and nothing more?' + _OF,
                   'The message asks the owner a question or a favour that one sentence from them settles - a yes, a no, a time, a name, a go-ahead - and nothing has to be looked up, changed or produced behind it.'),
    'fyi':        ('Would the owner file this as informational, with no action?' + _OF,
                   'The owner would file it without acting: a notice, report, thanks or thread between others, or something their past verdicts say is not theirs.'),
    'urgent':     ('Would the owner call this urgent?',
                   'It carries a deadline today or tomorrow, an event happening today, or somebody blocked right now until it is done.'),
}
# Asked only to say WHO does a task, so they are read only when intent is task.
KIND = {
    'coding':  ("If this is a task, would it need code changed in one of the owner's repositories?" + _OF,
                'The work is a bug fix, feature, script or pull request in a repository the owner holds; looking up, confirming or granting is not that.'),
    'general': ('If this is a task, would an assistant that can read, research and draft do it for the owner?' + _OF,
                'Thinking, reading, checking a value, chasing a person or drafting a reply would do it; nobody has to type at a system or act in the world.'),
    'manual':  ('If this is a task, would only the owner themselves be able to do it?' + _OF,
                'A person has to do it in the world - attend, sign, call, decide - and no amount of typing or thinking does it.'),
}


def triage(key: str, state: str, timeout: int = 20) -> dict:
    """{intent, kind, urgent, p} - a verdict with NO reason; the words are not this model's to write. `kind` is None unless intent is task."""
    got = ask(key, state, {**TRIAGE, **KIND}, timeout)
    p = {k: v[1] for k, v in got.items()}
    intent = max(('task', 'reply_only', 'fyi'), key=p.get)
    kind = max(('coding', 'general', 'manual'), key=p.get) if intent == 'task' else None
    return {'intent': intent, 'kind': {'manual': 'task'}.get(kind, kind), 'urgent': got['urgent'][0], 'p': p}

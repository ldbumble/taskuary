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

"""A stub for the sent-words judge (taskuary/sentjudge.py): the model's answer per message, picked by a phrase of the
owner's own words. What a message MEANS is the model's call in the app, so a test says what the model said - it never
leans on a word list."""
import json, re

from taskuary import sentjudge


def brain(said: dict, calls: list = None):
    """A brain answering the judge's prompt: `said` maps a phrase of the owner's words to the verdict fields for it
    (asks_them / promise / what / due / delivered / delivers), or to a function of the item's text returning them.
    Anything not named is neither an ask nor a promise."""
    def llm(system, user, **kw):
        if calls is not None: calls.append(user)
        out = []
        for item in user.split('\n\n')[1:]:
            m = re.match(r'\[(m\d+)\]', item)
            if not m: continue
            words = item.split('\n')[1]
            v = next((v for k, v in said.items() if k in words), {})
            out.append({'id': m.group(1), 'asks_them': False, 'promise': False, **(v(item) if callable(v) else v)})
        return json.dumps({'verdicts': out})
    return llm


def judged(store, said: dict, calls: list = None) -> int:
    """Run one judging pass over the owner's unjudged sent messages with the stub's answers."""
    return sentjudge.judge(store, brain(said, calls))

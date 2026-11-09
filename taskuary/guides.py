"""How-tos an agent reads when its work comes to one - progressive disclosure (the owner, 2026-11-09: "that's crazy ... The tools should be
progressive disclosure"). The system prompt names each in a line where it applies (browserview.offer, general.NUMBER_LINE); the text itself
is one call away - the `guide` tool (agenttools) or `taskuary --guide TOPIC` - instead of riding in every turn of every task."""


def _browser():
    from . import browserview
    return browserview.guide()

def _number():
    from .general import TEACH_ME
    return TEACH_ME

def _show():
    from .agenttools import SHOW_EXAMPLE
    return f'A WORKED `show` SPEC - a grid of stats, a chart beside a table, and a checklist:\n{SHOW_EXAMPLE}'

# topic -> (what it is for, in one line; its text)
GUIDES = {'browser': ("driving Taskuary's browser: looking at a page, signing in, a CAPTCHA, a step only the owner can do", _browser),
          'show': ('a worked example of a `show` view: stats, a chart beside a table, a checklist', _show),
          'number': ('teaching a figure out of a customised system before you state it - schema, definition, known numbers, proof', _number)}

def index() -> str: return '; '.join(f'{k} ({w})' for k, (w, _) in GUIDES.items())

def read(topic: str) -> str:
    "One guide's text. ValueError names the ones there are, so the next call is the right one."
    t = str(topic or '').strip().lower()
    if t not in GUIDES: raise ValueError(f'no guide {topic!r} - one of: {index()}')
    return GUIDES[t][1]()

"""How-tos an agent reads when its work comes to one - progressive disclosure (the owner, 2026-11-09: "that's crazy ... The tools should be
progressive disclosure"). The system prompt names each in a line where it applies (browserview.offer, general.NUMBER_LINE); the text itself
is one call away - the `guide` tool (agenttools) or `taskuary --guide TOPIC` - instead of riding in every turn of every task."""


def _browser():
    from . import browserview
    return browserview.guide()

def _number():
    from .general import TEACH_ME
    return TEACH_ME

# ...the types themselves, read when a view is made instead of riding in every turn's tool list (the night run, 2026-11-09)
SHOW_TYPES = ("THE `show` TYPES: every type takes title? and description?; each block draws as its own card, its children under it. "
              "grid {cols: 1-4} (its children side by side, stacking on a phone), stats {items: [{label, value, format?, note?, trend?: "
              "{dir: up|down|neutral, text}}]}, chart {kind: bar|line, format?, points: [{label, value, highlight?}]}, table {columns: [name | "
              "{label, format}], rows}, checklist {items: [{text, done}]}, list {items}, steps {items}, text {text: markdown}, note {tone: "
              "info|success|warning, text}, badge {text, variant?: default|secondary|outline|success|warning}, button {label, verb: a task-page "
              "button to light for the owner (close, defer, reply, continue...) | open: an app link as BRINGING THINGS UP writes them - #task=12, "
              "#connector=quickbooks, #settings=updates, #report=new}. format is currency|number|percent (12.5 -> 12.5%); give numbers as numbers.")

def _show():
    from .agenttools import SHOW_EXAMPLE
    return f'{SHOW_TYPES}\n\nA WORKED SPEC - a grid of stats, a chart beside a table, and a checklist:\n{SHOW_EXAMPLE}'

# ...and the shapes of the rarer proposals, out of every turn's tool list (2026-11-09)
PROPOSE = ("THE SHAPES OF A `propose` run_tool: a post - {action: run_tool, type: linkedin_post, text, image: a picture in your task "
           "folder}, drawn for the owner as the post with its Post button. A new GitHub issue - {type: github_issue, repo: owner/name, title, "
           "body, labels?}, drawn with its Create issue button. On a Jira, Monday or Linear item - type jira_comment {body}, jira_move "
           "{status}, jira_assign {assignee}, jira_close {body?} (monday_ and linear_ the same); `item` is the one this task came from "
           "unless you name another. Every one waits for the owner's press; always give `why`.")

# topic -> (what it is for, in one line; its text)
GUIDES = {'browser': ("driving Taskuary's browser: looking at a page, signing in, a CAPTCHA, a step only the owner can do", _browser),
          'show': ('the `show` types and their props, with a worked example', _show),
          'propose': ('the shapes of a post, a new GitHub issue and a Jira, Monday or Linear write', lambda: PROPOSE),
          'number': ('teaching a figure out of a customised system before you state it - schema, definition, known numbers, proof', _number)}

def index() -> str: return '; '.join(f'{k} ({w})' for k, (w, _) in GUIDES.items())

def read(topic: str) -> str:
    "One guide's text. ValueError names the ones there are, so the next call is the right one."
    t = str(topic or '').strip().lower()
    if t not in GUIDES: raise ValueError(f'no guide {topic!r} - one of: {index()}')
    return GUIDES[t][1]()

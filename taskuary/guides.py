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
              "{dir: up|down|neutral, text}}]}, chart {kind: bar|line|area|pie, format?, points: [{label, value, highlight?}] | rows: records, "
              "y?: the number column, x?: the label column}, table {columns?: [name | {label, format}], rows: lists, or records [{column: "
              "value}] whose keys are the columns}, checklist {items: [{text, done}]}, list {items}, steps {items}, text {text: markdown}, note "
              "{tone: info|success|warning, text}, badge {text, variant?: default|secondary|outline|success|warning}, button {label, verb: a "
              "task-page button to light for the owner (close, defer, reply, continue...) | open: an app link as BRINGING THINGS UP writes them - "
              "#task=12, #connector=quickbooks, #settings=updates, #report=new | on: {press: {action: answer, params: {text}} or {action: "
              "setState, params: {statePath, value}}}}. format is currency|number|percent (12.5 -> 12.5%); give numbers as numbers.\n"
              "WHAT-IF AND ANSWERS (after json-render's state and actions): the view's `state` {name: first value}; slider {label, value: "
              "{$bindState: /name}, min, max, step?, format?}, toggle {label, value}, select {label, value, options}, date {label, value} each move "
              "one value on his screen alone. A tile's value, a point's value or a table cell may be {$expr: \"...\"} (or {$state: /name}): "
              "numbers, 'words', true/false, the state's names - in a cell also its row's columns, lower case with _ for a space - + - * / %, "
              "== != < <= > >=, && || !, c ? a : b, min max round abs floor ceil; it is worked out again as a control moves. choice {label, "
              "options} and a button's answer (its text may hold {expr}: \"Order {seats} seats\") come back to you once, as his press.\n"
              "WHO CAN MAKE WHICH TIMES: availability {people: [{name, ranges?: [{day, from, to}]}], minutes?: the meeting's length, 30 unless "
              "given} draws each person's ranges as bars on one time axis, the days side by side, how many people are free in each stretch, and "
              "the best slot - the most people for `minutes` together - banded and said with its count (\"4 of 6\"), who cannot make it and who "
              "has not replied. day is a date (2026-12-01) or a short label, from and to are 24-hour times (14:00); a person with no `ranges` has "
              "not replied, with an empty list can make none. The counts and the best slot are worked out on the page from the ranges; the view "
              "takes no count.\n"
              "A VIEW'S `id` (beside title and root) names it: shown again under the same id - a chart, a table, any view - it is drawn "
              "once, where you just showed it, as it now is, and no older copy stays above it: a view that changes as answers arrive is one view.")
AVAILABILITY = ('{"id":"times","title":"Product ideas session","root":"a","elements":{"a":{"type":"availability","props":{"minutes":60,"people":['
                '{"name":"Erin Blake","ranges":[{"day":"2026-12-01","from":"14:00","to":"16:00"}]},'
                '{"name":"Ray Colton","ranges":[{"day":"2026-12-02","from":"10:00","to":"12:00"},{"day":"2026-12-01","from":"15:00","to":"16:00"}]},'
                '{"name":"Paula Vance","ranges":[]},{"name":"Omar Keller"}]}}}}')
WHAT_IF = ('{"title":"Payworth seats","state":{"seats":40,"annual":false},"root":"g","elements":{"g":{"type":"grid","props":{"cols":1},'
           '"children":["s","a","k","go"]},"s":{"type":"slider","props":{"label":"Seats","value":{"$bindState":"/seats"},"min":5,"max":200,"step":5}},'
           '"a":{"type":"toggle","props":{"label":"Pay yearly (2 months free)","value":{"$bindState":"/annual"}}},"k":{"type":"stats","props":{"items":['
           '{"label":"Per month","format":"currency","value":{"$expr":"seats * (annual ? 10 : 12)"}},{"label":"Per year","format":"currency",'
           '"value":{"$expr":"seats * (annual ? 10 : 12) * 12"}}]}},"go":{"type":"button","props":{"label":"Go with this"},"on":{"press":'
           '{"action":"answer","params":{"text":"{seats} seats, {annual ? \'yearly\' : \'monthly\'}"}}}}}}')
CHOICE = ('{"root":"c","elements":{"c":{"type":"choice","props":{"label":"Which plan should I renew?","options":["Basic - $200/mo",'
          '"Pro - $540/mo","Let it lapse"]}}}}')

def _show():
    from .agenttools import SHOW_EXAMPLE
    return (f'{SHOW_TYPES}\n\nA WORKED SPEC - a grid of stats, a chart beside a table, and a checklist:\n{SHOW_EXAMPLE}\n\n'
            f'A WHAT-IF - a seats slider and a toggle working out the cost, and his go:\n{WHAT_IF}\n\nA CHOICE:\n{CHOICE}\n\n'
            f'AN AVAILABILITY - two have named times, one can make none, one has not replied:\n{AVAILABILITY}')

# ...and the shapes of the rarer proposals, out of every turn's tool list (2026-11-09)
PROPOSE = ("THE SHAPES OF A `propose` run_tool: a new GitHub issue - {type: github_issue, repo: owner/name, title, "
           "body, labels?}, drawn with its Create issue button. On a Jira, Monday or Linear item - type jira_comment {body}, jira_move "
           "{status}, jira_assign {assignee}, jira_close {body?} (monday_ and linear_ the same); `item` is the one this task came from "
           "unless you name another. Every one waits for the owner's press.")

# topic -> (what it is for, in one line; its text)
GUIDES = {'browser': ("driving Taskuary's browser: looking at a page, signing in, a CAPTCHA, a step only the owner can do", _browser),
          'show': ('the `show` types and their props, with a worked example', _show),
          'propose': ('the shapes of a new GitHub issue and a Jira, Monday or Linear write', lambda: PROPOSE),
          'number': ('teaching a figure out of a customised system before you state it - schema, definition, known numbers, proof', _number)}

def index() -> str: return '; '.join(f'{k} ({w})' for k, (w, _) in GUIDES.items())

def read(topic: str) -> str:
    "One guide's text. ValueError names the ones there are, so the next call is the right one."
    t = str(topic or '').strip().lower()
    if t not in GUIDES: raise ValueError(f'no guide {topic!r} - one of: {index()}')
    return GUIDES[t][1]()

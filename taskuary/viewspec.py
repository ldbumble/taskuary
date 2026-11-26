"""A VIEW THE AGENT SHOWS IN ITS CHAT (agenttools `show`): a small JSON tree - {title?, root, elements: {id: {type, props, children?}}} -
drawn as real UI (website/src/ViewSpec.jsx) where a table, a chart or a checklist says more than words. After Vercel's json-render, built
small here because its packages need React 19. The catalog (viewspec.json) is the only list of types and props; the page reads the same file.

`check` is the server's word on a spec: a type, prop or size outside the catalog is a ValueError the model reads and fixes, and the spec that
passes comes back normalised. A button only names a row button (buttons.json) to light, or an app page to open - nothing here sends."""
import json, re
from pathlib import Path

from . import buttons

CAT = json.loads(Path(__file__).with_name('viewspec.json').read_text(encoding='utf-8'))
CAPS, EVERY = CAT['caps'], CAT['every']
TYPES = {t: {**spec, **EVERY} for t, spec in CAT['types'].items()}     # every type also takes a title and a description
MARK = 'TASKUARY-VIEW '                  # the tool's answer carries the spec after this, so the chat draws it from the trace (chatStream.viewOf)
ROW_VERBS = sorted(v for v, b in buttons.VERBS.items() if b.get('row'))      # lit where it stands on the task page: a verb with no row has no button
ROW_OF = {r: v for v in ROW_VERBS for r in buttons.VERBS[v]['row'] if r not in ROW_VERBS}    # its row id (done) names it too
LINK, ID = re.compile(r'#[\w=&%.:/-]+'), re.compile(r'[\w-]{1,64}')


def _text(v, n, at):
    if isinstance(v, bool) or not isinstance(v, (str, int, float)): raise ValueError(f'{at} must be text')
    s = str(v).strip()
    if len(s) > n: raise ValueError(f'{at} is {len(s)} characters - keep it to {n}')
    return s


def _list(v, at, n=None):
    n = n or CAPS['items']
    if not isinstance(v, list) or not v: raise ValueError(f'{at} must be a non-empty list')
    if len(v) > n: raise ValueError(f'{at} has {len(v)} entries - show at most {n}; a longer one belongs in a file')
    return v


def _cell(v, at, names=None):
    if v is None or isinstance(v, (bool, int, float)): return v
    if isinstance(v, dict): return _expr(v, at, names)
    return _text(v, CAPS['short'], at)


# ── A VALUE WORKED OUT ON THE PAGE (the owner, 2026-11-24: a "seats" slider recomputes a cost tile live, after json-render's data binding):
# {"$state": "/seats"} reads a value of the view's `state`, {"$expr": "seats * price"} works one out - numbers, 'words', true/false, the
# state's names (and in a table's cell its row's columns, lower case with _ for a space), + - * / %, comparisons, && || !, c ? a : b, and
# min max round abs floor ceil. Parsed here only to say what is wrong; the page evaluates the same grammar (viewSpec.js evalExpr), never eval
FNS = ('min', 'max', 'round', 'abs', 'floor', 'ceil')
_TOK = re.compile(r"\s*(?:(\d+(?:\.\d+)?|\.\d+)|('[^']*'|\"[^\"]*\")|([A-Za-z_]\w*)|(==|!=|<=|>=|&&|\|\||[-+*/%<>!?:(),]))")
def names_in(src: str) -> set:
    "The names an expression reads, or a ValueError saying where it stops making sense."
    toks, i, s = [], 0, str(src)
    while i < len(s.rstrip()):
        m = _TOK.match(s, i)
        if not m or m.end() == i: raise ValueError(f'cannot read {s[i:].strip()[:20]!r}')
        toks.append(next(g for g in m.groups() if g is not None) if any(m.groups()) else ''); i = m.end()
    toks, used, at = [t for t in toks if t], set(), [0]
    peek = lambda: toks[at[0]] if at[0] < len(toks) else ''
    def eat(t=None):
        x = peek()
        if t and x != t: raise ValueError(f"expected {t!r} {'at the end' if not x else f'before {x!r}'}")
        if not x: raise ValueError('it ends too soon')
        at[0] += 1; return x
    def atom():
        x = eat()
        if x == '(': tern(); eat(')'); return
        if x in ('-', '!'): return atom()
        if x[0].isdigit() or x[0] == '.' or x[0] in '\'"' or x in ('true', 'false'): return
        if not (x[0].isalpha() or x[0] == '_'): raise ValueError(f'{x!r} cannot start a value')
        if peek() == '(':
            if x not in FNS: raise ValueError(f'{x}() is not one of {", ".join(FNS)}')
            eat('(')
            if peek() != ')':
                tern()
                while peek() == ',': eat(','); tern()
            eat(')'); return
        used.add(x)
    def binary():
        atom()
        while peek() in ('+', '-', '*', '/', '%', '==', '!=', '<', '<=', '>', '>=', '&&', '||'): eat(); atom()
    def tern():
        binary()
        if peek() == '?': eat('?'); tern(); eat(':'); tern()
    if not toks: raise ValueError('it is empty')
    tern()
    if peek(): raise ValueError(f'{peek()!r} was not expected')
    return used


def _expr(v, at, names=None):
    "{$expr} or {$state} -> {'$expr': src}, its names among `names` (the state's, and a row's columns) - else a ValueError the model fixes."
    if set(v) == {'$state'} and isinstance(v['$state'], str): v = {'$expr': v['$state'].strip().lstrip('/')}
    if set(v) != {'$expr'} or not isinstance(v['$expr'], str): raise ValueError(f'{at} must be a value, or {{"$expr": "..."}} / {{"$state": "/name"}}')
    src = _text(v['$expr'], CAPS['short'], at)
    try: used = names_in(src)
    except ValueError as e: raise ValueError(f'{at}: {src!r} - {e}') from None
    if names is not None and (bad := sorted(used - set(names))): raise ValueError(f'{at}: {src!r} reads {", ".join(bad)}, which the view has no value for - its state has {", ".join(sorted(names)) or "nothing"}')
    return {'$expr': src}
def col_name(label) -> str: return re.sub(r'\W+', '_', str(label).strip().lower()).strip('_')
TMPL = re.compile(r'\{([^{}]+)\}')
def _tmpl(v, at, names):
    "Words with {expr} in them (an answer: \"Order {seats} seats\"): each worked out when he presses."
    s = _text(v, CAPS['short'], at)
    for m in TMPL.finditer(s): _expr({'$expr': m.group(1)}, at, names)
    return s


def _num(v, at):
    if isinstance(v, bool) or not isinstance(v, (int, float)): raise ValueError(f'{at} must be a number')
    return v


def _obj(v, at, need, may=()):
    if isinstance(v, str) and need == ('text',): return {'text': v}
    if not isinstance(v, dict): raise ValueError(f'{at} must be an object with {", ".join(need)}')
    if (bad := set(v) - set(need) - set(may)): raise ValueError(f'{at} has {", ".join(sorted(bad))} - it takes {", ".join((*need, *may))}')
    if (miss := [k for k in need if v.get(k) in (None, '')]): raise ValueError(f'{at} needs {", ".join(miss)}')
    return v


def _rows(v, at, cols, names=()):
    out, row = [], [*names, *map(col_name, cols)]        # ...a cell's expression reads the state and its own row's columns
    for i, r in enumerate(_list(v, at)):
        if isinstance(r, dict):
            if (bad := set(r) - set(cols)): raise ValueError(f'{at}[{i}] has {", ".join(sorted(bad))}, which are not among the columns')
            r = [r.get(c) for c in cols]
        if not isinstance(r, list) or len(r) > len(cols): raise ValueError(f'{at}[{i}] must be a list of at most {len(cols)} cells (one per column)')
        out.append([_cell(c, f'{at}[{i}][{j}]', row) for j, c in enumerate(r)] + [None] * (len(cols) - len(r)))
    return out


# ── THE ONE ROW SHAPE (the owner, 2026-11-24: "showing is one step"): a list of flat records, [{column: value}] - what a report's run, a
# database read and past_figures answer with, and what a table's `rows` and a chart's `rows` take as they are
def records(text) -> list | None:
    "A tool's answer as records - JSON lines of flat objects (reports.rows_out), or a JSON list of them - else None."
    s = str(text or '').strip()
    try: rs = json.loads(s) if s.startswith('[') else [json.loads(l) for l in s.splitlines() if l.strip()]
    except ValueError: return None
    ok = rs and all(isinstance(r, dict) and r and all(not isinstance(x, (dict, list)) for x in r.values()) for r in rs)
    return rs if ok else None
def columns_of(rs) -> list: return list(dict.fromkeys(k for r in rs for k in r))[:CAPS['columns']]


def _points(rows, x, y, at):
    "A chart's rows as its points: `y` the number column (else the first that is a number in every row), `x` its label (else the first that is not)."
    rs = _list(rows, f'{at}.rows')
    if not all(isinstance(r, dict) for r in rs): raise ValueError(f'{at}.rows must be records - [{{column: value}}]')
    cols, num = columns_of(rs), lambda c: all(isinstance(r.get(c), (int, float)) and not isinstance(r.get(c), bool) for r in rs)
    y = y or next((c for c in cols if num(c)), None)
    if y not in cols or not num(y): raise ValueError(f'{at}.y must name a column that is a number in every row - one of {", ".join(c for c in cols if num(c)) or "none"}')
    x = x or next((c for c in cols if c != y and not num(c)), None)
    if x is not None and x not in cols: raise ValueError(f'{at}.x must name one of the columns: {", ".join(cols)}')
    return [{'label': _text(r.get(x) if x else f'#{i + 1}', CAPS['short'], f'{at}.rows[{i}].{x}'), 'value': r[y]} for i, r in enumerate(rs)]


def _tile(o, at, names=None):
    o = _obj(o, at, ('label', 'value'), ('note', 'trend', 'format'))
    out = {'label': _text(o['label'], CAPS['short'], f'{at}.label'), 'value': _cell(o['value'], f'{at}.value', names)}
    if o.get('note'): out['note'] = _text(o['note'], CAPS['short'], f'{at}.note')
    if o.get('format') is not None: out['format'] = _prop(FORMAT, o['format'], f'{at}.format', {})
    if o.get('trend') is not None:      # its direction colours it; the words say by how much and against what ("+$340 vs Collect")
        t = _obj(o['trend'], f'{at}.trend', ('dir',), ('text',))
        out['trend'] = {'dir': _prop(DIR, t['dir'], f'{at}.trend.dir', {}), **({'text': _text(t['text'], CAPS['short'], f'{at}.trend.text')} if t.get('text') else {})}
    return out


# a table's column is its name, or {label, format} when its numbers are money, plain counts or percents
FORMAT, DIR = CAT['types']['chart']['format'], 'up|down|neutral'
def _col(c, at):
    if not isinstance(c, dict): return _text(c, CAPS['short'], at)
    o = _obj(c, at, ('label',), ('format',))
    return {'label': _text(o['label'], CAPS['short'], f'{at}.label'), **({'format': _prop(FORMAT, o['format'], f'{at}.format', {})} if o.get('format') else {})}
def labels(cols): return [c['label'] if isinstance(c, dict) else c for c in cols or []]


def _prop(kind, v, at, props, names=()):
    if '|' in kind:
        ws = kind.split('|')
        if all(w.isdigit() for w in ws):        # a count, as a grid's columns: a number, or its digits
            if isinstance(v, bool) or str(v) not in ws: raise ValueError(f'{at} must be one of {kind.replace("|", ", ")}')
            return int(v)
        if v not in ws: raise ValueError(f'{at} must be one of {kind.replace("|", ", ")}')
        return v
    if kind == 'str': return _text(v, CAPS['short'], at)
    if kind == 'md': return _text(v, CAPS['long'], at)
    # ...a table's columns and a row of tiles are as wide as a screen holds, never a list's length
    wide = CAPS['columns'] if at.endswith('.columns') or kind == 'tiles' else None
    if kind == 'strs': return [_text(x, CAPS['short'], f'{at}[{i}]') for i, x in enumerate(_list(v, at, wide))]
    if kind == 'cols': return [_col(x, f'{at}[{i}]') for i, x in enumerate(_list(v, at, CAPS['columns']))]
    if kind == 'rows': return _rows(v, at, labels(props.get('columns')), names)
    if kind == 'records': return v          # ...a chart's: made its points in _element
    if kind == 'num': return _num(v, at)
    if kind == 'bind':      # a control's value: the state name it moves - "seats", "/seats" or json-render's {"$bindState": "/seats"}
        n = v.get('$bindState') if isinstance(v, dict) and set(v) == {'$bindState'} else v
        if not isinstance(n, str) or not re.fullmatch(r'[A-Za-z_]\w{0,31}', n := n.strip().lstrip('/')): raise ValueError(f'{at} must name a value of the state: "seats" or {{"$bindState": "/seats"}}')
        return n
    if kind == 'tiles': return [_tile(x, f'{at}[{i}]', names) for i, x in enumerate(_list(v, at, wide))]
    if kind == 'checks':
        os = [_obj(x, f'{at}[{i}]', ('text',), ('done',)) for i, x in enumerate(_list(v, at))]
        return [{'text': _text(o['text'], CAPS['short'], f'{at}[{i}].text'), 'done': o.get('done') is True} for i, o in enumerate(os)]
    if kind == 'points':
        os = [_obj(x, f'{at}[{i}]', ('label', 'value'), ('highlight',)) for i, x in enumerate(_list(v, at))]
        val = lambda x, a: _expr(x, a, names) if isinstance(x, dict) else _num(x, a)
        return [{'label': _text(o['label'], CAPS['short'], f'{at}[{i}].label'), 'value': val(o['value'], f'{at}[{i}].value'),
                 **({'highlight': True} if o.get('highlight') is True else {})} for i, o in enumerate(os)]
    if kind == 'avail': return _avail(v, at)
    if kind == 'verb':
        v = ROW_OF.get(v, v) if isinstance(v, str) else v
        if v not in ROW_VERBS: raise ValueError(f'{at}: {v!r} is no button on the task page - one of {", ".join(ROW_VERBS)}')
        return v
    if kind == 'link':
        if not isinstance(v, str) or not LINK.fullmatch(v) or v == '#setup': raise ValueError(f'{at} must be an app page link like #settings or #report=new')
        return v
    raise ValueError(f'{at}: the catalog names an unknown kind {kind!r}')       # viewspec.json itself is wrong


# ── WHO CAN MAKE WHICH TIMES (the owner, 2026-11-26: a thread finding a meeting time): the agent gives only who and their ranges - {name,
# ranges: [{day, from, to}]}, a day an ISO date or a short label, times HH:MM on a 24-hour clock; no `ranges` is no reply yet, an empty list
# none of the times. How many fit each slot and the best one are the page's arithmetic (availability.js `overlap`), never the model's
_TIME, DAY_N = re.compile(r'([01]?\d|2[0-3]):([0-5]\d)'), 20
def _mins(v, at):
    if not isinstance(v, str) or not (m := _TIME.fullmatch(v.strip())): raise ValueError(f'{at} must be a time on a 24-hour clock, like 09:30 or 14:00')
    return int(m[1]) * 60 + int(m[2])
def _avail(v, at):
    out, days = [], set()
    for i, o in enumerate(_list(v, at, CAPS['people'])):
        o = _obj(o, f'{at}[{i}]', ('name',), ('ranges',)); p = {'name': _text(o['name'], CAPS['short'], f'{at}[{i}].name')}
        if p['name'] in [x['name'] for x in out]: raise ValueError(f'{at}[{i}].name {p["name"]!r} is listed twice - one entry a person, all their ranges in it')
        if (rs := o.get('ranges')) is not None:
            if not isinstance(rs, list): raise ValueError(f'{at}[{i}].ranges must be a list of {{day, from, to}} - leave it out for someone who has not replied')
            if len(rs) > CAPS['ranges']: raise ValueError(f'{at}[{i}].ranges has {len(rs)} entries - at most {CAPS["ranges"]}')
            p['ranges'] = []
            for j, r in enumerate(rs):
                a = f'{at}[{i}].ranges[{j}]'; r = _obj(r, a, ('day', 'from', 'to'))
                if _mins(r['from'], f'{a}.from') >= _mins(r['to'], f'{a}.to'): raise ValueError(f'{a}.from must be before its to')
                p['ranges'].append({'day': _text(r['day'], DAY_N, f'{a}.day'), 'from': r['from'].strip(), 'to': r['to'].strip()}); days.add(p['ranges'][-1]['day'])
        out.append(p)
    if len(days) > CAPS['days']: raise ValueError(f'{at} spans {len(days)} days - at most {CAPS["days"]}')
    return out


CONTROLS = ('slider', 'toggle', 'select', 'date')        # ...each moves one value of the view's state, on the page alone
def _on(v, at, names):
    """A button's `on.press`, after json-render's actions: answer {text} - his pick, to the agent once as his press (words with {expr} in
    them are worked out when he presses) - or setState {statePath, value} on the page. Nothing else: no action sends or pays."""
    p = _obj(_obj(v, at, ('press',))['press'], f'{at}.press', ('action',), ('params',))
    a, ps = p['action'], p.get('params') or {}
    if not isinstance(ps, dict): raise ValueError(f'{at}.press.params must be an object')
    if a == 'answer': return {'press': {'action': a, 'params': {'text': _tmpl(_obj(ps, f'{at}.press.params', ('text',))['text'], f'{at}.press.params.text', names)}}}
    if a == 'setState':
        ps = _obj(ps, f'{at}.press.params', ('statePath', 'value'))
        if (n := _prop('bind', ps['statePath'], f'{at}.press.params.statePath', {})) not in names: raise ValueError(f'{at}.press.params.statePath: the state has no {n!r}')
        return {'press': {'action': a, 'params': {'statePath': n, 'value': _cell(ps['value'], f'{at}.press.params.value', names)}}}
    raise ValueError(f'{at}.press.action must be answer (his pick, to you) or setState (a value on the page) - not {a!r}')


def _element(eid, e, names=()):
    at = f'elements.{eid}'
    if not isinstance(e, dict): raise ValueError(f'{at} must be an object {{type, props, children?}}')
    if (t := e.get('type')) not in TYPES: raise ValueError(f'{at}.type {t!r} is not one of {", ".join(TYPES)}')
    if (bad := set(e) - {'type', 'props', 'children', 'on'}): raise ValueError(f'{at} has {", ".join(sorted(bad))} - an element is type, props, children, on')
    props, spec = e.get('props') or {}, TYPES[t]
    if not isinstance(props, dict): raise ValueError(f'{at}.props must be an object')
    if (bad := set(props) - set(spec)): raise ValueError(f'{at}.props has {", ".join(sorted(bad))} - a {t} takes {", ".join(spec)}')
    if (miss := [k for k, kind in spec.items() if kind.endswith('!') and props.get(k) in (None, '', [])]): raise ValueError(f'{at}.props needs {", ".join(miss)}')
    # ...records stand as they come: a table's columns are their keys, a chart's points their label and number columns
    if t == 'table' and not props.get('columns'):
        if not isinstance(props['rows'], list) or not all(isinstance(r, dict) for r in props['rows']): raise ValueError(f'{at}.props needs columns, or rows as records [{{column: value}}]')
        props = {**props, 'columns': columns_of(props['rows'])}
    if t == 'chart':
        if (props.get('points') is None) == (props.get('rows') is None): raise ValueError(f'{at}.props needs points, or rows (records) with y (and x)')
        if props.get('rows') is not None:
            x, y = (_text(props[k], CAPS['short'], f'{at}.props.{k}') if props.get(k) else None for k in ('x', 'y'))
            props = {**{k: v for k, v in props.items() if k not in ('rows', 'x', 'y')}, 'points': _points(props['rows'], x, y, f'{at}.props')}
    out = {}
    for k, kind in spec.items():          # in the catalog's order, so a table's rows are read against its columns
        if props.get(k) is not None: out[k] = _prop(kind.rstrip('!'), props[k], f'{at}.props.{k}', out, names)
    on = _on(e['on'], f'{at}.on', names) if e.get('on') is not None else None
    if on and t != 'button': raise ValueError(f'{at}.on: only a button takes an action - a choice answers by itself')
    if t == 'button' and sum(x is not None for x in (out.get('verb'), out.get('open'), on)) != 1:
        raise ValueError(f'{at} needs one of props.verb (a button to light), props.open (a page link) or on.press (answer / setState)')
    if t == 'slider' and not out['min'] < out['max']: raise ValueError(f'{at}.props.min must be under max')
    if t == 'availability' and not 15 <= out.get('minutes', 30) <= 480: raise ValueError(f'{at}.props.minutes (how long the meeting is) must be 15 to 480')
    kids = e.get('children') or []
    if not isinstance(kids, list) or not all(isinstance(k, str) for k in kids): raise ValueError(f'{at}.children must be a list of element ids')
    if len(kids) > CAPS['children']: raise ValueError(f'{at} has {len(kids)} children - at most {CAPS["children"]}')
    return {'type': t, 'props': out, **({'on': on} if on else {}), **({'children': kids} if kids else {})}


def _state(spec, els) -> dict:
    "The view's values: its `state` as given, and each bound name it lacks at its control's start - a slider's min, off, the first option."
    st = spec.get('state') or {}
    if not isinstance(st, dict): raise ValueError('state must be an object of name -> its first value')
    if len(st) > CAPS['state']: raise ValueError(f'state has {len(st)} values - at most {CAPS["state"]}')
    out = {}
    for k, v in st.items():
        if not re.fullmatch(r'[A-Za-z_]\w{0,31}', str(k)) or k in FNS or k in ('true', 'false'): raise ValueError(f'state.{k}: a name is a word (letters, digits, _)')
        if isinstance(v, (dict, list)): raise ValueError(f'state.{k} must be a number, words, true or false')
        out[k] = _cell(v, f'state.{k}')
    for e in els.values():
        p = e.get('props') if isinstance(e, dict) else None
        if not isinstance(p, dict) or e.get('type') not in CONTROLS or p.get('value') is None: continue
        try: n = _prop('bind', p['value'], '', {})
        except ValueError: continue          # ...said by its own element
        if n not in out: out[n] = {'slider': p.get('min', 0), 'toggle': False, 'select': (p.get('options') or [''])[0], 'date': ''}[e['type']]
    return out


# THE TOOL'S SCHEMA IS THE CATALOG (the HIPAA walk, 2026-11-21: five calls to draw one chart - root missing, `bar` as a type, `data` for props,
# `x`/`y` for points - each refusal naming one rule): the element shape, the type names and every prop by name, from viewspec.json, so a
# model fills it right the first time. One flat element (no anyOf: some providers refuse it); `check` still says what a type takes
_KIND = {'str': {'type': 'string'}, 'md': {'type': 'string'}, 'verb': {'type': 'string'}, 'link': {'type': 'string'}, 'num': {'type': 'number'}, 'records': {'type': 'array', 'items': {'type': 'object'}},
         'cols': {'type': 'array', 'items': {}}, 'rows': {'type': 'array', 'items': {'type': 'array'}}, 'strs': {'type': 'array', 'items': {'type': 'string'}},
         'tiles': {'type': 'array', 'items': {'type': 'object'}},
         'avail': {'type': 'array', 'items': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'ranges': {'type': 'array', 'items': {
             'type': 'object', 'properties': {'day': {'type': 'string'}, 'from': {'type': 'string'}, 'to': {'type': 'string'}}, 'required': ['day', 'from', 'to']}}}, 'required': ['name']}},
         'checks': {'type': 'array', 'items': {'type': 'object'}},
         'points': {'type': 'array', 'items': {'type': 'object', 'properties': {'label': {'type': 'string'}, 'value': {},
                                                                                  'highlight': {'type': 'boolean'}}, 'required': ['label', 'value']}}}
def _kind(k):
    k = k.rstrip('!')
    if '|' in k: ws = k.split('|'); return {'type': 'integer', 'enum': [int(w) for w in ws]} if all(w.isdigit() for w in ws) else {'type': 'string', 'enum': ws}
    return _KIND.get(k, {})
def element_schema() -> dict:
    "One element as the show tool's schema has it: {type, props, children}, every prop the catalog names (a name two types share takes either)."
    props = {}
    for spec in TYPES.values():
        for p, k in spec.items(): props[p] = _kind(k) if p not in props or props[p] == _kind(k) else {}
    return {'type': 'object', 'properties': {'type': {'type': 'string', 'enum': list(TYPES)}, 'props': {'type': 'object', 'properties': props},
                                             'children': {'type': 'array', 'items': {'type': 'string'}}, 'on': {'type': 'object'}}, 'required': ['type']}
# ...and one small view that passes, said with every refusal: the example is the rule a model copies
EXAMPLE = {'root': 'c', 'elements': {'c': {'type': 'chart', 'props': {'kind': 'bar', 'title': 'Tickets by quarter',
                                                                     'points': [{'label': 'Q1', 'value': 412}, {'label': 'Q2', 'value': 380}]}}}}


def check(spec) -> dict:
    "The spec normalised, or a ValueError saying what to fix. Only what the root reaches is kept."
    if not isinstance(spec, dict): raise ValueError('the view must be an object {title?, root, elements}')
    els, root = spec.get('elements'), spec.get('root')
    if not isinstance(els, dict) or not els: raise ValueError('elements must be an object of id -> {type, props, children?}')
    if len(els) > CAPS['elements']: raise ValueError(f'{len(els)} elements - at most {CAPS["elements"]}')
    # ...A VIEW WITH NO ROOT STANDS ON ITS ONE TOP (walk 2, 2026-11-21: Claude left `root` out and was refused twice for one chart): the one
    # element no other names as a child is the root - several tops, or none, still ask for it
    if root in (None, '') and (tops := [k for k in els if not any(k in (e or {}).get('children', []) for e in els.values() if isinstance(e, dict))]):
        # ...and SEVERAL TOPS stand in one column, in the order given (round 3, 2026-11-22: a title and a chart, siblings with no root, were
        # refused again) - the view the model meant, never a second try for it
        if len(tops) == 1: root = tops[0]
        else: root = next(f'_col{n}' for n in range(len(els) + 1) if f'_col{n}' not in els); els = {**els, root: {'type': 'grid', 'props': {'cols': '1'}, 'children': tops}}
    if root not in els: raise ValueError(f'root {root!r} is not one of the elements')
    out, path, state = {}, [], _state(spec, els)
    def walk(eid):
        if eid in path: raise ValueError(f'elements.{eid} contains itself - children must form a tree')
        if eid not in els: raise ValueError(f'elements.{path[-1]}.children names {eid!r}, which is not an element')
        if eid in out: return
        out[eid] = _element(eid, els[eid], tuple(state)); path.append(eid)
        for k in out[eid].get('children', []): walk(k)
        path.pop()
    walk(root)
    view = {**({'title': _text(spec['title'], CAPS['short'], 'title')} if spec.get('title') else {}), 'root': root, 'elements': out, **({'state': state} if state else {})}
    # ...A VIEW NAMED IS ONE VIEW (the owner, 2026-11-26: availability that fills in as replies come): shown again under the same `id` it replaces
    # the one drawn before, where it stands in the chat (chatStream.viewHomes) - never a second copy under it
    if spec.get('id') not in (None, ''):
        if not isinstance(spec['id'], str) or not ID.fullmatch(spec['id']): raise ValueError('id must be a short name of letters, digits, - or _ - it names the view, and showing it again updates it')
        view['id'] = spec['id']
    if (n := len(json.dumps(view, ensure_ascii=False))) > CAPS['chars']: raise ValueError(f'the view is {n:,} characters - keep it to {CAPS["chars"]:,}: fewer rows, shorter text, or the whole of it in a file')
    return view


# A VIEW OF ONLY WORDS SHOWS NOTHING (his live app, 2026-11-25: "really dumb visual that provides nothing" - a card titled for a picture
# held only the picture's alt text, beside the picture itself): words in a box are the answer's words, and they are not drawn as a view
WORDS = ('text', 'note', 'grid')
def shown(spec) -> str:
    "The tool's answer: a line for the model, and the checked spec on one line after MARK for the chat. A refusal carries one that passes."
    try: view = check(spec)
    except ValueError as e: raise ValueError(f"{e}. A view that passes: {json.dumps(EXAMPLE, separators=(',', ':'))}") from e
    if all(e['type'] in WORDS for e in view['elements'].values()): raise ValueError('a view of only words shows nothing your answer does not - say them there')
    # ...a view he can answer is one of its own: its id names it to the answer road, so the same choice shown twice is two questions
    if asks(view): view['id'] = __import__('uuid').uuid4().hex[:12]
    # ...AND THE SPEC IS THE ANSWER'S LAST THING: every reader takes it from the mark to the end (viewSpec.specIn, session_artifacts.view). The
    # line on his pick stood after it, so a view he could answer - a choice, a button - read as no view and was never drawn (the card gallery)
    return f"Shown in the owner's chat.{' His pick comes to you as his press.' if asks(view) else ''} {MARK}{json.dumps(view, ensure_ascii=False, separators=(',', ':'))}"
def asks(view) -> bool: return any(e['type'] == 'choice' or (e.get('on') or {}).get('press', {}).get('action') == 'answer' for e in view['elements'].values())


# ── HIS ANSWER ON A VIEW (a choice's option, a button's answer): one press of his, on the road a press takes - an audit row of the task, a
# press event its agent hears (events), the agent woken on it (general.to_agent). Once a control:
# a second press says what he picked first. It sends and pays nothing; the agent does what the pick asks, with a card where that needs one
ANSWER, _ONCE = 'view_answer', __import__('threading').Lock()
def answers(store, tid: int) -> dict:
    "{view id: {element id: his pick}} on task `tid`."
    out = {}
    for r in store._rows("SELECT Detail FROM audit WHERE EntityType='task' AND EntityId=? AND Action=? ORDER BY Id", (int(tid), ANSWER)):
        try: d = json.loads(r['Detail'] or '{}')
        except ValueError: continue
        out.setdefault(str(d.get('view')), {}).setdefault(str(d.get('el')), d.get('pick'))
    return out


def answer(store, tid: int, view: str, el: str, pick: str, asked: str = '', actor: str = 'owner') -> dict:
    "-> {ok, pick, told} - or {ok: False, pick: the first one} where this control was answered already."
    view, el, pick = _text(view, 64, 'view'), _text(el, 64, 'el'), _text(pick, CAPS['short'], 'pick')
    if not (view and el and pick): raise ValueError('an answer names its view, its control and his pick')
    asked = str(asked or '').strip()[:CAPS['short']]
    with _ONCE:                 # ...two presses at once are still one answer
        if (had := answers(store, tid).get(view, {}).get(el)) is not None: return {'ok': False, 'pick': had}
        store.audit('task', int(tid), ANSWER, actor, detail={'view': view, 'el': el, 'pick': pick, 'asked': asked})
    # ...heard as his press; drawn on the view he pressed, never as a chat line besides (it is not in general.PRESSES)
    from . import events, general
    events.add(store, int(tid), 'press', what=f'picked "{pick}"' + (f' for "{asked}"' if asked else '') + ' on your view')
    return {'ok': True, 'pick': pick, 'told': general.to_agent(store, int(tid), '', actor, frm='taskuary', pressed=True) or ''}

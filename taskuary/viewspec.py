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
LINK = re.compile(r'#[\w=&%.:/-]+')


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


def _cell(v, at):
    if v is None or isinstance(v, (bool, int, float)): return v
    return _text(v, CAPS['short'], at)


def _num(v, at):
    if isinstance(v, bool) or not isinstance(v, (int, float)): raise ValueError(f'{at} must be a number')
    return v


def _obj(v, at, need, may=()):
    if isinstance(v, str) and need == ('text',): return {'text': v}
    if not isinstance(v, dict): raise ValueError(f'{at} must be an object with {", ".join(need)}')
    if (bad := set(v) - set(need) - set(may)): raise ValueError(f'{at} has {", ".join(sorted(bad))} - it takes {", ".join((*need, *may))}')
    if (miss := [k for k in need if v.get(k) in (None, '')]): raise ValueError(f'{at} needs {", ".join(miss)}')
    return v


def _rows(v, at, cols):
    out = []
    for i, r in enumerate(_list(v, at)):
        if isinstance(r, dict):
            if (bad := set(r) - set(cols)): raise ValueError(f'{at}[{i}] has {", ".join(sorted(bad))}, which are not among the columns')
            r = [r.get(c) for c in cols]
        if not isinstance(r, list) or len(r) > len(cols): raise ValueError(f'{at}[{i}] must be a list of at most {len(cols)} cells (one per column)')
        out.append([_cell(c, f'{at}[{i}][{j}]') for j, c in enumerate(r)] + [None] * (len(cols) - len(r)))
    return out


def _tile(o, at):
    o = _obj(o, at, ('label', 'value'), ('note', 'trend', 'format'))
    out = {'label': _text(o['label'], CAPS['short'], f'{at}.label'), 'value': _cell(o['value'], f'{at}.value')}
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


def _prop(kind, v, at, props):
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
    if kind == 'rows': return _rows(v, at, labels(props.get('columns')))
    if kind == 'tiles': return [_tile(x, f'{at}[{i}]') for i, x in enumerate(_list(v, at, wide))]
    if kind == 'checks':
        os = [_obj(x, f'{at}[{i}]', ('text',), ('done',)) for i, x in enumerate(_list(v, at))]
        return [{'text': _text(o['text'], CAPS['short'], f'{at}[{i}].text'), 'done': o.get('done') is True} for i, o in enumerate(os)]
    if kind == 'points':
        os = [_obj(x, f'{at}[{i}]', ('label', 'value'), ('highlight',)) for i, x in enumerate(_list(v, at))]
        return [{'label': _text(o['label'], CAPS['short'], f'{at}[{i}].label'), 'value': _num(o['value'], f'{at}[{i}].value'),
                 **({'highlight': True} if o.get('highlight') is True else {})} for i, o in enumerate(os)]
    if kind == 'verb':
        v = ROW_OF.get(v, v) if isinstance(v, str) else v
        if v not in ROW_VERBS: raise ValueError(f'{at}: {v!r} is no button on the task page - one of {", ".join(ROW_VERBS)}')
        return v
    if kind == 'link':
        if not isinstance(v, str) or not LINK.fullmatch(v) or v == '#setup': raise ValueError(f'{at} must be an app page link like #settings or #report=new')
        return v
    raise ValueError(f'{at}: the catalog names an unknown kind {kind!r}')       # viewspec.json itself is wrong


def _element(eid, e):
    at = f'elements.{eid}'
    if not isinstance(e, dict): raise ValueError(f'{at} must be an object {{type, props, children?}}')
    if (t := e.get('type')) not in TYPES: raise ValueError(f'{at}.type {t!r} is not one of {", ".join(TYPES)}')
    if (bad := set(e) - {'type', 'props', 'children'}): raise ValueError(f'{at} has {", ".join(sorted(bad))} - an element is type, props, children')
    props, spec = e.get('props') or {}, TYPES[t]
    if not isinstance(props, dict): raise ValueError(f'{at}.props must be an object')
    if (bad := set(props) - set(spec)): raise ValueError(f'{at}.props has {", ".join(sorted(bad))} - a {t} takes {", ".join(spec)}')
    if (miss := [k for k, kind in spec.items() if kind.endswith('!') and props.get(k) in (None, '', [])]): raise ValueError(f'{at}.props needs {", ".join(miss)}')
    out = {}
    for k, kind in spec.items():          # in the catalog's order, so a table's rows are read against its columns
        if props.get(k) is not None: out[k] = _prop(kind.rstrip('!'), props[k], f'{at}.props.{k}', out)
    if t == 'button' and ('verb' in out) == ('open' in out): raise ValueError(f'{at}.props needs one of verb (a button to light) or open (a page link)')
    kids = e.get('children') or []
    if not isinstance(kids, list) or not all(isinstance(k, str) for k in kids): raise ValueError(f'{at}.children must be a list of element ids')
    if len(kids) > CAPS['children']: raise ValueError(f'{at} has {len(kids)} children - at most {CAPS["children"]}')
    return {'type': t, 'props': out, **({'children': kids} if kids else {})}


def check(spec) -> dict:
    "The spec normalised, or a ValueError saying what to fix. Only what the root reaches is kept."
    if not isinstance(spec, dict): raise ValueError('the view must be an object {title?, root, elements}')
    els, root = spec.get('elements'), spec.get('root')
    if not isinstance(els, dict) or not els: raise ValueError('elements must be an object of id -> {type, props, children?}')
    if len(els) > CAPS['elements']: raise ValueError(f'{len(els)} elements - at most {CAPS["elements"]}')
    if root not in els: raise ValueError(f'root {root!r} is not one of the elements')
    out, path = {}, []
    def walk(eid):
        if eid in path: raise ValueError(f'elements.{eid} contains itself - children must form a tree')
        if eid not in els: raise ValueError(f'elements.{path[-1]}.children names {eid!r}, which is not an element')
        if eid in out: return
        out[eid] = _element(eid, els[eid]); path.append(eid)
        for k in out[eid].get('children', []): walk(k)
        path.pop()
    walk(root)
    view = {**({'title': _text(spec['title'], CAPS['short'], 'title')} if spec.get('title') else {}), 'root': root, 'elements': out}
    if (n := len(json.dumps(view, ensure_ascii=False))) > CAPS['chars']: raise ValueError(f'the view is {n:,} characters - keep it to {CAPS["chars"]:,}: fewer rows, shorter text, or the whole of it in a file')
    return view


def shown(spec) -> str:
    "The tool's answer: a line for the model, and the checked spec on one line after MARK for the chat."
    view = check(spec)
    return f"Shown in the owner's chat. {MARK}{json.dumps(view, ensure_ascii=False, separators=(',', ':'))}"

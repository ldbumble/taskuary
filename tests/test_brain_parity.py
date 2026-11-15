"""THE SAME JOBS ON EVERY BRAIN ROAD, judged by what they leave behind (the owner, 2026-11-15: "how many times do we have to fix the same thing
... Goal was to make hipaa ai the same as all other ones").

An outside client on the HIPAA AI card took 25 minutes to fill an invoice template and draft the email: the API road could not write an
Office file, and nothing was cached. The parity work before it matched tools BY NAME and never ran a job through. Here each everyday job runs
through the real road - the card's own transport (llm.make_llm: the Messages API, an OpenAI-compatible gateway, the HIPAA AI card with a
Gemini or a Claude model behind it), the agent's loop (apiagent.turn under general.send_prompt), Taskuary's own tools through the same /api/mcp
a Claude Code or Codex session calls - with a scripted model and no network. What is judged is the OUTCOME: a file that opens, the card it is
attached to, what reached the chat, and what each request cost. A job one road can do and another cannot fails here.

The CLI roads (Claude Code, Codex) make files with their own hands - not ours to script; what is ours is the same /api/mcp they are pointed at,
checked as the reference below (TheCliRoadsReachTheSameTools).
"""
import json, re, time
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import agenttools, apiagent, browserview as bv, config, general, llm, outputs, server, session_artifacts
from taskuary.store import MemoryStore

ROADS = {'anthropic': ('anthropic', 'claude-sonnet-5-5'), 'openai': ('openai', 'gpt-5'), 'openrouter_claude': ('openrouter', 'anthropic/claude-sonnet-5-5'),
         'hipaa_gemini': ('hipaa_ai', 'gemini-3.8-flash'), 'hipaa_claude': ('hipaa_ai', 'claude-sonnet-5-5')}
CLAUDE = ('anthropic', 'openrouter_claude', 'hipaa_claude')
GW = 'https://ai.northwind.example/v1'
CLIENT = TestClient(server.app)
ITEMS = [(f'2026-10-{d:02d}', 1 + d % 5, 15 * (1 + d % 5)) for d in range(1, 31)]        # thirty sessions: date, units, amount


# ── the model: a job's plan, said through each card's own wire ───────────────────────────────────────────────────────────────────
class Scripted:
    """A model that follows `plan` - a generator that yields a list of (tool, args) calls or its final words, and is sent the answers its last
    calls got (as the model read them, stubs and all). Every request the road sent is kept, as the provider received it."""
    def __init__(self, plan, answered=''):
        self.gen, self.bodies, self.n, self.answered, self.started = plan(), [], 0, answered, False
    def next(self, results):
        if not self.started: self.started = True; return next(self.gen)
        try: return self.gen.send(results)
        except StopIteration: return 'Done.'
    def calls(self, got):
        if isinstance(got, str): return None, got
        out = []
        for name, a in got: self.n += 1; out.append((f'c{self.n}', name, a))
        return out, ''


def _openai_results(body):
    msgs = body['messages']
    at = max((i for i, m in enumerate(msgs) if m.get('tool_calls')), default=None)
    return [] if at is None else [m['content'] if isinstance(m['content'], str) else ''.join(p.get('text') or '' for p in m['content'])
                                   for m in msgs[at + 1:] if m.get('role') == 'tool']


def _anthropic_results(kw):
    last = (kw.get('messages') or [{}])[-1]
    return [b['content'] if isinstance(b.get('content'), str) else ''.join(x.get('text') or '' for x in b.get('content') or [])
            for b in last.get('content') or [] if isinstance(b, dict) and b.get('type') == 'tool_result']


class _R:
    def __init__(self, body, status=200): self.status_code, self._b, self.text, self.headers = status, body, json.dumps(body), {'x-litellm-attempted-fallbacks': '0'}
    def json(self): return self._b


def wire(road, model: Scripted):
    "The patches that put `model` behind the card of `road`, and the brain build_llm hands the session."
    t, name = ROADS[road]
    if t == 'anthropic':
        def create(**kw):
            model.bodies.append(json.loads(json.dumps(kw, default=str)))
            calls, said = model.calls(model.next(_anthropic_results(kw)) if kw.get('tools') or kw.get('messages') else 'ok')
            content = [NS(type='tool_use', id=i, name=n, input=a) for i, n, a in calls] if calls else [NS(type='text', text=said)]
            return NS(stop_reason='tool_use' if calls else 'end_turn', content=content, model=name, usage=None)
        cli = mock.Mock(); cli.messages.create.side_effect = create
        patch = mock.patch('anthropic.Anthropic', return_value=cli)
    else:
        def post(url, headers, body, timeout):
            model.bodies.append(json.loads(json.dumps(body)))
            calls, said = model.calls(model.next(_openai_results(body)))
            msg = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': i, 'type': 'function', 'function': {'name': n, 'arguments': json.dumps(a)}}
                                                                        for i, n, a in calls]} if calls else {'role': 'assistant', 'content': said}
            return _R({'model': model.answered or name, 'choices': [{'message': msg, 'finish_reason': 'stop'}],
                       'usage': {'prompt_tokens': len(json.dumps(body)) // 4, 'completion_tokens': 20}})
        patch = mock.patch.object(llm, 'post_retrying', side_effect=post)
    cfg = {'model': name, **({'base_url': GW} if t != 'anthropic' else {})}
    return patch, lambda: llm.make_llm(t, cfg, 'k')


def _mcp_post(url, json=None, headers=None, timeout=None, **kw):
    "Taskuary's own tools, answered by the real server - the door a CLI session's MCP client knocks on."
    path = url.split('://', 1)[-1].split('/', 1)[1]
    return CLIENT.post('/' + path, json=json, headers=headers)


# ── the world: a person's mail with the files a job needs ─────────────────────────────────────────────────────────────────────────
def world(files: dict, ask='Fill in the invoice template for October and send it to Erin.'):
    s = MemoryStore()
    tid = s.create_task({'Title': 'October invoice for Erin', 'Summary': ask, 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
    mid = s.add_message({'TaskId': tid, 'ExternalId': f'x{time.time_ns()}', 'ConversationId': 'conv-inv', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                         'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'Subject': 'October invoice', 'BodyText': ask,
                         'SentAt': '2026-11-02 09:00:00', 'Status': 'routed'})
    s._exec('UPDATE task SET TrustedThrough=? WHERE TaskId=?', (10 ** 9, tid))          # a sender he trusts: the agent works it (origin.hold)
    d = config.home() / 'attachments' / f'm{mid}'; d.mkdir(parents=True, exist_ok=True)
    paths = {}
    for n, data in files.items():
        (p := d / n).write_bytes(data)
        s.add_attachment({'MessageId': mid, 'ExternalId': f'a{time.time_ns()}', 'Name': n, 'ContentType': outputs.content_type(n), 'Size': len(data), 'Path': str(p)})
        paths[n] = str(p)
    return s, tid, paths


def run(road, s, tid, plan, line='Please do it.', answered='', installed=False):
    "One owner line on task `tid`, worked by `road`'s card with the model scripted by `plan`. (model, session, seconds)."
    model = Scripted(plan, answered)
    patch, make = wire(road, model)
    session = general.GeneralSession(s, tid)
    session.pick, session.provider, session.model = 'connector:1', road, ''
    llm._NO_CACHE.clear(); llm._ANSWERED.clear()
    t0 = time.monotonic()
    with patch, mock.patch.object(server, 'store', s), mock.patch('requests.post', side_effect=_mcp_post), \
            mock.patch.object(llm, 'build_llm', side_effect=lambda *a, **k: make()), \
            mock.patch.object(bv, 'installed', return_value=installed), mock.patch.object(bv, 'can_set_up', return_value=False), \
            mock.patch.object(bv, 'state', return_value={'open': False}):
        session.send_prompt(line, echo=False)
    return model, session, time.monotonic() - t0


def said(s, tid) -> str: return '\n'.join(c['Body'] for c in s.list_comments(tid) if c['ActorType'] == general.ASSISTANT_TYPE)
def out(tid, name) -> Path: return outputs.folder(tid) / name
def emails(s, tid) -> list:
    "The email cards waiting for the owner's Send, each as its review row (its envelope names what it carries)."
    from taskuary import verdicts
    return [s.get_review(c['rid']) for c in verdicts.unsent(s, tid)]
def carries(card, name) -> bool: return name in json.dumps(card, default=str)


ALL = list(ROADS)


# ── 1. fill a Word invoice template with thirty line items and attach it to an email card ───────────────────────────────────────
def _docx_template():
    from taskuary import officefiles
    return officefiles.docx('Invoice number: {{NO}}\n| Date | Units | Amount |\n| {{DATE}} | {{UNITS}} | {{AMOUNT}} |\nTotal due: {{TOTAL}}')


def _opens(p: Path) -> str:
    "The file as an Office app would open it - a valid package, read back by Taskuary's own reader - its text."
    import zipfile
    from xml.dom import minidom
    from taskuary import attachtext
    with zipfile.ZipFile(p) as z:
        for n in z.namelist():
            if n.endswith('.xml'): minidom.parseString(z.read(n))
    return attachtext.read(p.name, p.read_bytes())['text']


@pytest.mark.parametrize('road', ALL)
def test_a_word_invoice_with_thirty_lines_is_filled_and_attached_to_the_email(road):
    s, tid, f = world({'Invoice template.docx': _docx_template()})
    name, total = 'Invoice INV-2026-10.docx', sum(a for *_, a in ITEMS)
    def plan():
        got = yield [('file_read', {'path': f['Invoice template.docx']})]
        assert '{{DATE}} | {{UNITS}} | {{AMOUNT}}' in got[0], got
        yield [('file_edit', {'path': f['Invoice template.docx'], 'old': '{{DATE}} | {{UNITS}} | {{AMOUNT}}', 'save_as': str(out(tid, name)),
                              'new': '\n'.join(f'{d} | {u} | {a:.2f}' for d, u, a in ITEMS)})]
        yield [('file_edit', {'path': str(out(tid, name)), 'old': '{{TOTAL}}', 'new': f'${total:.2f}'}),
               ('file_edit', {'path': str(out(tid, name)), 'old': '{{NO}}', 'new': 'INV-2026-10'})]
        got = yield [('propose_email', {'to': 'erin@northwind.example', 'subject': 'Re: October invoice', 'text': 'Hi Erin, the October invoice is attached.',
                                        'attach': [name]})]
        assert 'error' not in got[0].lower()[:40], got
        yield 'The October invoice is filled and attached to the email for Erin - press Send when it reads right.'
    model, _, secs = run(road, s, tid, plan)
    text = _opens(out(tid, name))
    assert all(f'{d} | {u} | {a:.2f}' in text for d, u, a in ITEMS) and f'Total due: ${total:.2f}' in text and 'INV-2026-10' in text
    cards = emails(s, tid)
    assert len(cards) == 1 and carries(cards[0], name), cards
    assert 'filled and attached' in said(s, tid)
    assert len(model.bodies) == 5, f'{road}: one call a step, {len(model.bodies)} calls'


# ── 2. the same with an Excel template: the formulas follow the rows, the total covers them all ────────────────────────────────────
def _xlsx_template() -> bytes:
    import io
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(['Date', 'Units', 'Rate', 'Amount']); ws.append(['{{DATE}}', 0, 15, '=B2*C2']); ws.append([None, None, 'Total', '=SUM(D2:D2)'])
    b = io.BytesIO(); wb.save(b); return b.getvalue()


@pytest.mark.parametrize('road', ALL)
def test_an_excel_invoice_grows_to_thirty_rows_with_its_formulas_and_total(road):
    from openpyxl import load_workbook
    s, tid, f = world({'Invoice template.xlsx': _xlsx_template()})
    name = 'Invoice INV-2026-10.xlsx'
    def plan():
        got = yield [('file_read', {'path': f['Invoice template.xlsx']})]
        row = next(l.strip().strip('|').strip() for l in got[0].splitlines() if '{{DATE}}' in l)
        yield [('file_edit', {'path': f['Invoice template.xlsx'], 'old': row, 'save_as': str(out(tid, name)),
                              'new': '\n'.join(f'{d} | {u} | 15' for d, u, _ in ITEMS)})]
        got = yield [('file_read', {'path': str(out(tid, name))})]
        assert '=SUM(D2:D31)' in got[0], got
        yield [('propose_email', {'to': 'erin@northwind.example', 'subject': 'Re: October invoice', 'text': 'Attached.', 'attach': [name]})]
        yield 'Filled the workbook - thirty rows, the total covers them - and attached it to the email for Erin.'
    run(road, s, tid, plan)
    ws = load_workbook(out(tid, name)).active
    assert [ws.cell(31, c).value for c in (1, 2, 3, 4)] == ['2026-10-30', ITEMS[-1][1], 15, '=B31*C31']
    assert [ws['C32'].value, ws['D32'].value] == ['Total', '=SUM(D2:D31)']
    assert [carries(c, name) for c in emails(s, tid)] == [True]


# ── 3. read what came on the mail - a PDF, a Word file, a workbook - and answer from it ─────────────────────────────────────────────
def _files():
    import io
    from openpyxl import Workbook
    from taskuary import officefiles
    from test_attachment_text import pdf
    wb = Workbook(); wb.active.append(['Vendor', 'Due']); wb.active.append(['Payworth', 4812.5]); b = io.BytesIO(); wb.save(b)
    return {'statement.pdf': pdf('Statement for October', 'Total due: USD 4,812.50 by 2026-11-01'),
            'statement.docx': officefiles.docx('Statement for October\nTotal due: USD 4,812.50 by 2026-11-01'), 'statement.xlsx': b.getvalue()}


@pytest.mark.parametrize('road', ALL)
@pytest.mark.parametrize('kind', ['pdf', 'docx', 'xlsx'])
@pytest.mark.parametrize('reader', ['file_read', 'read_attachment'])
def test_a_file_on_the_mail_is_read_and_answered_from(road, kind, reader):
    n = f'statement.{kind}'
    s, tid, f = world({n: _files()[n]}, ask='How much do we owe on the attached statement?')
    aid = s.list_attachments(s.list_messages(tid)[0]['MessageId'])[0]['AttachmentId']
    def plan():
        got = yield [(reader, {'path': f[n]} if reader == 'file_read' else {'id': aid})]
        if 'not loaded' in got[0] or 'load_tools' in got[0] or 'Loaded' in got[0]: got = yield [(reader, {'id': aid})]
        amount = re.search(r'4,?812\.5', got[0])
        yield f'We owe USD {amount[0] if amount else "?"} on the statement.'
    run(road, s, tid, plan)
    assert re.search(r'We owe USD 4,?812\.5', said(s, tid)), said(s, tid)


# ── 4. a query written for review is shown - it appears under the answer, as text ───────────────────────────────────────────────────
@pytest.mark.parametrize('road', ALL)
def test_a_query_for_review_is_written_and_shown_under_the_answer(road):
    s, tid, _ = world({}, ask='Write me the SQL for overdue invoices so I can review it.')
    sql = 'SELECT InvoiceNo, DueDate FROM invoice WHERE DueDate < CURRENT_DATE AND Paid = 0;'
    def plan():
        yield [('file_write', {'path': str(out(tid, 'overdue.sql')), 'text': sql})]
        got = yield [('show', {'files': [str(out(tid, 'overdue.sql'))]})]
        assert 'Shown' in got[0], got
        yield 'The query is under this answer for you to review.'
    run(road, s, tid, plan)
    shown = [a for a in s.list_task_artifacts(tid) if a.get('Kind') == 'shown']
    assert [a['Name'] for a in shown] == ['overdue.sql'] and Path(shown[0]['Path']).read_text(encoding='utf-8') == sql
    assert shown[0]['ContentType'] == 'text/plain'


# ── 5. a chart drawn in the chat ──────────────────────────────────────────────────────────────────────────────────────────────────
CHART = {'root': 'c', 'elements': {'c': {'type': 'chart', 'props': {'kind': 'bar', 'format': 'currency', 'description': 'Billed per week',
         'points': [{'label': f'Week {i}', 'value': v} for i, v in enumerate((900, 1150, 780, 1320), 1)]}}}}


@pytest.mark.parametrize('road', ALL)
def test_a_chart_is_drawn_in_the_chat(road):
    from taskuary import viewspec
    s, tid, _ = world({}, ask='Chart what we billed each week in October.')
    def plan():
        got = yield [('show', CHART)]
        assert viewspec.MARK in got[0], got
        yield 'Billing peaked in week 4.'
    run(road, s, tid, plan)
    views = [a for a in s.list_task_artifacts(tid) if a.get('Kind') == session_artifacts.VIEW]
    assert len(views) == 1 and json.loads(Path(views[0]['Path']).read_text(encoding='utf-8'))['elements']['c']['type'] == 'chart'


# ── 6. the browser: offered where this computer has one, and said in one line with the way on where it has not ────────────────────
def _tools(road, body) -> list:
    return sorted(t.get('name') or t['function']['name'] for t in body.get('tools') or [])
def _system(road, body) -> str:
    return json.dumps(body['system'] if ROADS[road][0] == 'anthropic' else body['messages'][0]['content'])


@pytest.mark.parametrize('road', ALL)
@pytest.mark.parametrize('installed', [True, False])
def test_the_browser_is_offered_where_there_is_one_and_said_where_there_is_not(road, installed):
    s, tid, _ = world({}, ask='Look up the claim status on the payer portal.')
    def plan(): yield 'Opening it.'
    model, *_ = run(road, s, tid, plan, installed=installed)
    names, system = _tools(road, model.bodies[0]), _system(road, model.bodies[0])
    assert ('browser_open' in names) is installed and ('browser_look' in names) is installed
    if installed: assert 'browser_open' in system
    else: assert 'NO BROWSER FOR AGENTS YET' in system and '[[TASKUARY-ASK]]' in system, 'one line and the way on, never "cannot be done from here"'


# ── 7. a long job: each request stays bounded, the prefix stays the same bytes, and the cache is marked where the model needs it ───
@pytest.mark.parametrize('road', ALL)
def test_a_long_job_keeps_each_request_bounded_its_prefix_stable_and_its_cache_marked(road):
    # ...each a real sheet's size (~9,400 characters, under one tool answer's cap) and each its own: the same page twice is going in circles
    files = {f'week{i:02d}.csv': ('client,date,units,rate,amount\n' + '\n'.join(
        f'client-{i:02d}-{k:03d},2026-10-{k % 30 + 1:02d},{k % 5 + 1},15.00,{(k % 5 + 1) * 15:.2f}' for k in range(240))).encode() for i in range(1, 21)}
    s, tid, f = world(files, ask='Add up all twenty weekly sheets.')
    def plan():
        for n in sorted(f): yield [('file_read', {'path': f[n]})]
        yield 'All twenty read: the total is in the sheet.'
    model, session, _ = run(road, s, tid, plan)
    sizes = [len(json.dumps(b)) for b in model.bodies]
    assert len(sizes) == 21, f'{road}: twenty reads and the answer are 21 calls, not {len(sizes)}'
    one = max(len(x) for x in files.values()) + 400
    assert max(sizes) < sizes[0] + (2 * apiagent.KEEP_STEPS - 1) * one + 20 * 700, f'{road}: grew to {max(sizes):,} from {sizes[0]:,} - stubs, not every page again'
    assert max(sizes) < apiagent.REQUEST_CHARS * 1.05, 'the bound is the whole request, the tools and the system with it'
    assert len({_system(road, b) for b in model.bodies}) == 1, 'the system is the same bytes on every step: the cache prefix holds'
    assert len({json.dumps(_tools(road, b)) for b in model.bodies}) == 1
    marks = [json.dumps(b).count('cache_control') for b in model.bodies]
    if road in CLAUDE: assert all(1 <= m <= 4 for m in marks), f'{road}: Claude caches only what is marked - {marks}'
    else: assert not any(marks), f'{road}: a marker turns its own prefix cache off - {marks}'
    # ...and the next turn of the same conversation opens on the same system: what was cached is read again
    first = _system(road, model.bodies[0])
    model2 = Scripted(lambda: iter(['The total is 13,500.']))
    patch, make = wire(road, model2)
    with patch, mock.patch.object(server, 'store', s), mock.patch('requests.post', side_effect=_mcp_post), \
            mock.patch.object(llm, 'build_llm', side_effect=lambda *a, **k: make()), mock.patch.object(bv, 'installed', return_value=False), \
            mock.patch.object(bv, 'can_set_up', return_value=False), mock.patch.object(bv, 'state', return_value={'open': False}):
        session.send_prompt('And the grand total?', echo=False)
    assert _system(road, model2.bodies[0]) == first


@pytest.mark.parametrize('road', ['hipaa_gemini', 'anthropic'])
def test_the_request_bound_holds_the_whole_request_tools_and_system_included(road):
    """The gateway's own log (2026-11-15): calls of 35-60K tokens on a task under a 120,000-character bound. The tools' schemas rode beside the
    conversation and were never counted. Set low, every call - tools, system and all - stays under it."""
    files = {f'week{i:02d}.csv': ('client,date,units,rate,amount\n' + '\n'.join(
        f'client-{i:02d}-{k:03d},2026-10-{k % 30 + 1:02d},{k % 5 + 1},15.00,{(k % 5 + 1) * 15:.2f}' for k in range(240))).encode() for i in range(1, 9)}
    s, tid, f = world(files, ask='Add up the eight weekly sheets.')
    bound = 80_000
    s.set_setting('agent_request_chars', str(bound), 'owner')
    def plan():
        for n in sorted(f): yield [('file_read', {'path': f[n]})]
        yield 'Read all eight.'
    model, *_ = run(road, s, tid, plan)
    sizes = [len(json.dumps(b)) for b in model.bodies]
    assert len(sizes) == 9 and max(sizes) < bound * 1.05, f'{road}: {sizes}'


# ── the CLI roads: the reference - the same Taskuary tools at the same door, and the same outcome from them ───────────────────────────
class TestTheCliRoadsReachTheSameTools:
    def test_claude_and_codex_sessions_and_an_ai_card_reach_one_server(self):
        s, tid, _ = world({})
        claude = agenttools.session_args(s, 'claude', tid)
        codex = agenttools.session_args(s, 'codex', tid)
        cfg = json.loads(Path(claude[claude.index('--mcp-config') + 1]).read_text(encoding='utf-8'))
        assert next(iter(cfg['mcpServers'].values()))['url'] == agenttools.url(tid)
        assert any(agenttools.url(tid) in x for x in codex)
        posted = []
        def post(url, json=None, headers=None, timeout=None): posted.append(url); return _mcp_post(url, json=json, headers=headers)
        with mock.patch.object(server, 'store', s):
            names = {t['function']['name'] for t in apiagent.taskuary_tools(tid, 'sid-p', post=post)}
        assert posted == [agenttools.url(tid)], 'the AI card asks the same server, for the same task'
        assert {'propose_email', 'propose_reply', 'show', 'read_attachment', 'search_messages'} <= names

    def test_every_hand_a_cli_has_the_ai_card_has_by_its_own_name(self):
        "Claude Code's Read/Write/Edit/Bash/WebSearch/WebFetch and agent-browser - each one family the API road offers whole (never behind load_tools)."
        s, tid, _ = world({})
        with mock.patch.object(apiagent, 'taskuary_tools', return_value=[]):
            names = {t['function']['name'] for t in apiagent.tools_for(tid, 'sid-h', browser=True)}
        apiagent.forget(tid, 'sid-h')
        for cli, ours in {'Read': 'file_read', 'Write': 'file_write', 'Edit': 'file_edit', 'Glob': 'files_list', 'Bash': 'run_command',
                          'WebSearch': 'web_search', 'WebFetch': 'web_fetch', 'agent-browser open': 'browser_open', 'agent-browser snapshot': 'browser_look',
                          'agent-browser click': 'browser_click', 'agent-browser fill': 'browser_fill', 'agent-browser screenshot': 'browser_screenshot'}.items():
            assert ours in names, f"a CLI's {cli} has no counterpart on an AI card"

    def test_a_cli_session_attaching_its_file_and_showing_a_chart_gets_the_card_and_the_view_an_ai_card_does(self):
        from taskuary import guard, terminal, viewspec
        s, tid, _ = world({})
        d = outputs.folder(tid); d.mkdir(parents=True, exist_ok=True)
        from taskuary import officefiles
        (d / 'Invoice INV-2026-10.docx').write_bytes(officefiles.docx('Invoice INV-2026-10\n| Date | Amount |\n| 2026-10-01 | 60.00 |'))
        env = terminal.session_env('assistant', tid, sid='sid-cli')
        h = {'X-Taskuary-Token': env[guard.AGENT_ENV], guard.TASK_HDR: env[guard.TASK_ENV]}
        def call(name, a):
            r = CLIENT.post(f'/api/mcp?task={tid}', headers=h, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': a}})
            return r.json()['result']['content'][0]['text']
        with mock.patch.object(server, 'store', s):
            call('propose_email', {'to': 'erin@northwind.example', 'subject': 'Re: October invoice', 'text': 'Attached.', 'attach': ['Invoice INV-2026-10.docx']})
            assert viewspec.MARK in call('show', CHART)
        assert [carries(c, 'Invoice INV-2026-10.docx') for c in emails(s, tid)] == [True]
        assert [a['Kind'] for a in s.list_task_artifacts(tid)] == [session_artifacts.VIEW]

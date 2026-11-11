"""What each kind of model call sends, measured on a scratch store with invented people: `python tools/prompt_sizes.py`.

No model is called and nothing leaves the machine: a recording stand-in answers. TASKUARY_HOME is a fresh temp dir, so the real home is never
opened. Tokens are ESTIMATED as characters / 4. Prints one row per call kind - system, user, tools, calls per unit of work and tokens per unit -
and the agent loop's calls step by step as they were sent before 2026-11-10 (every earlier tool answer whole) and as they are sent now
(apiagent.sent). The owner, 2026-11-10: "they spent 25 dollars in one day? 32 million tokens?"."""
import json, os, sys, tempfile
from pathlib import Path

os.environ['TASKUARY_HOME'] = tempfile.mkdtemp(prefix='prompt_sizes_')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest import mock

NL = chr(10)
tok = lambda n: int(n) // 4


def world():
    "A task on a 15-message thread with two attachments, from a colleague, in a store holding the shipped guides."
    from taskuary import docsync
    from taskuary.store import MemoryStore
    s = MemoryStore(); docsync.sync_connections(s)
    s.set_setting('owner_email', 'alex@northwind.example', 't'); s.set_setting('owner_name', 'Alex Doyle', 't')
    tid = s.create_task({'Title': 'Payworth renewal', 'Summary': 'Erin asks whether we renew the Payworth contract by Friday', 'Kind': 'general',
                         'Status': 'open'}, 'owner')
    body = ('Hi Alex,' + NL * 2 + 'Following up on the renewal: pricing went up 8% and section 4 changed. Can you confirm by Friday whether '
            'we renew? The draft and last year\'s invoice are attached.' + NL * 2 + 'Thanks,' + NL + 'Erin' + NL * 2) + ('> earlier quoted line' + NL) * 20
    for i in range(15):
        mid = s.add_message({'TaskId': tid, 'ExternalId': f'x-{i}', 'ConversationId': 'c1', 'Channel': 'email', 'Subject': 'Re: Payworth renewal',
                             'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': f'2026-11-0{1 + i % 9} 09:{i:02d}:00',
                             'BodyText': body, 'Status': 'routed'})
    for n in ('renewal-draft.pdf', 'invoice-2025.pdf'): s.add_attachment({'MessageId': mid, 'Name': n, 'Path': f'/tmp/{n}'})
    return s, tid, mid


def tools_list(tid):
    from taskuary import agenttools, apiagent
    def post(url, json=None, headers=None, timeout=None):
        r = mock.Mock(status_code=200); r.json.return_value = agenttools.rpc(json, lambda n, a: '', ()); return r
    return apiagent.tools_for(tid, 'sizes', True, post=post)


ANSWERS = [NL.join(f'[m{i}] Erin Blake 2026-11-0{i % 9 + 1} - Re: Payworth renewal: ' + 'the terms and the price ' * 12 for i in range(10)),   # a mail search, 10 hits
           'FROM Erin Blake' + NL + 'What was agreed on the renewal and who signs it. ' * 80,                                                     # a read_message
           'clause,text' + NL + '4.1,The supplier may revise prices annually' + NL * 1 + ('row,' * 6 + NL) * 3000]                              # a 20 KB file


def loop(system, user, tools, steps=12, stub=True):
    "The size of each call one agent turn of `steps` tool calls sends: [chars per call]."
    from taskuary import apiagent
    sent, k = [], iter(range(10**6))
    class Brain:
        def chat(self, msgs, tools_, max_tokens, **kw):
            sent.append(len(json.dumps(msgs)) + len(json.dumps(tools_)))
            n = sum(m.get('role') == 'tool' for m in msgs)
            return {'content': 'Done.'} if n >= steps else {'tool_calls': [{'id': f'c{n}', 'function': {'name': 'file_read', 'arguments': json.dumps({'path': f'f{n}'})}}]}
    from taskuary.store import MemoryStore
    with mock.patch.object(apiagent, 'run_tool', side_effect=lambda *a: apiagent._cut(ANSWERS[next(k) % 3] + str(next(k)))), \
         (mock.patch.object(apiagent, 'sent', side_effect=lambda msgs, budget=None: [dict(m) for m in msgs]) if not stub else mock.MagicMock()):
        apiagent.turn(Brain(), MemoryStore(), 1, 'sizes', system, user, 500, tools=tools)
    return sent


def main():
    from taskuary import assistant, general, origin, quickwork, triage
    s, tid, mid = world()
    rows = []
    def row(kind, system, user, tools=0, calls=1, unit='per arriving message', each=None):
        per = each or (len(system) + len(user) + tools)
        rows.append((kind, len(system), len(user), tools, tok(per), calls, unit, tok(per) * calls if each is None else None))
    # triage: one call per arriving message, the guide whole
    seen = {}
    def rec(system, user, **kw): seen.update(system=system, user=user); return '{"intent": "fyi", "why": "x"}'
    triage.classify_intent({'from_email': 'erin@northwind.example', 'from_name': 'Erin Blake', 'subject': 'Re: Payworth renewal',
                            'body': s.get_message(mid)['BodyText']}, llm=rec, learned=(s.get_doc('learned') or '')[:20_000], soul=s.get_doc('soul') or '')
    row('triage', seen['system'], seen['user']); seen_triage = dict(seen)
    with mock.patch.object(origin, 'of_task', return_value=('owner', '')):
        system, user = general._prompt(s, tid)
        qs, qu = quickwork.prompt(s, tid, 'Can you confirm by Friday whether we renew?', False)
    tl = tools_list(tid); tchars = len(json.dumps(tl))
    row('quick_work (one call)', qs, qu, 0, 1, 'per reply owed (quick)')
    system += NL * 2 + 'TOOLS BRIEF ' * 200
    before, after = loop(system, user, tl, stub=False), loop(system, user, tl)
    row('agent step on an AI card, BEFORE', system, user, tchars, len(before), 'per agent turn (12 tools)', each=sum(before) // len(before))
    rows[-1] = rows[-1][:7] + (tok(sum(before)),)
    row('agent step on an AI card, NOW', system, user, tchars, len(after), 'per agent turn (12 tools)', each=sum(after) // len(after))
    rows[-1] = rows[-1][:7] + (tok(sum(after)),)
    seen.clear()
    with mock.patch.object(assistant, '_people_context', return_value=('', [])):
        try: assistant.think(s, [], lambda system, user, **kw: (seen.update(system=system, user=user), '{"lines": []}')[1])
        except Exception as e: seen.setdefault('system', ''); seen.setdefault('user', f'(not built: {e})')
    row('Advisor look', seen['system'], seen['user'], 0, 48, 'per day on its 30-minute clock (BEFORE; now only when something moved)')
    print(f"{'call kind':36} {'system':>8} {'user':>8} {'tools':>8} {'tok/call':>9} {'calls':>6}  {'tok/unit':>9}  unit   (tokens = chars/4, an estimate)")
    for k, sy, us, tl_, per, calls, unit, total in rows:
        print(f'{k:36} {sy:8,} {us:8,} {tl_:8,} {per:9,} {calls:6}  {total or 0:9,}  {unit}')
    t = seen_triage
    if hasattr(t['system'], 'blocks'):
        cache, own = sum(map(len, t['system'].blocks)), len(t['system'].rest) + len(t['user'])
        print(NL + f"triage, cached context vs this mail's own: {' + '.join(f'{tok(len(b)):,}' for b in t['system'].blocks)} tokens in the cached blocks, "
              f"{tok(own):,} new per mail")
        for d in (0.5, 0.9):     # billed-equivalent input = new + cached x (1 - discount): the discount is the provider's, not known here
            print(f'  billed as if {tok(own + cache * (1 - d)):,} tokens per mail at a {int(d * 100)}% discount on cached input (vs {tok(own + cache):,} uncached)')
    print(NL + 'agent turn, tokens per call, step by step:')
    print('  before: ' + ' '.join(f'{tok(x) // 1000}K' for x in before))
    print('  now:    ' + ' '.join(f'{tok(x) // 1000}K' for x in after))


if __name__ == '__main__': main()

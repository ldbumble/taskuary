"""A stand-in for the owner's own `reason-network` CLI (tests/test_reason_network.py) - never the real, internet-facing one.

It speaks the commands and the output shapes Reason Network's README and DESIGN.md document: `who --json` (its Directory),
`held` as it prints for a reader that is not a person, `approve`/`reject`, `send ... --from` with the text on stdin,
`listen --as <name> --wait 0` printing <reason-message> frames, `folder <path> off|on`, `stop`. Its world is a JSON file,
$REASON_NETWORK_HOME/fake.json, which the test writes and reads back; every call is recorded there.
Knobs: FAKE_RN_DROP=held,folder (commands this "version" lacks), FAKE_RN_NOJSON=1 (`who` without --json),
FAKE_RN_WHO=<raw text> (`who --json` answers in a shape nobody documented).
"""
import json, os, sys
from pathlib import Path

HOME = Path(os.environ['REASON_NETWORK_HOME'])
F = HOME / 'fake.json'
SUBS = ['who', 'send', 'listen', 'held', 'approve', 'reject', 'folder', 'stop', 'setup', 'link', 'leave']


def load(): return json.loads(F.read_text(encoding='utf-8')) if F.exists() else {}
def save(d): F.write_text(json.dumps(d, indent=1), encoding='utf-8')


def main(argv):
    d = load(); d.setdefault('calls', []).append(argv); save(d)
    drop = set(filter(None, os.environ.get('FAKE_RN_DROP', '').split(',')))
    subs = [s for s in SUBS if s not in drop]
    if not argv or argv == ['--help']:
        print('A team directory and message bus for coding agents\n\nUsage: reason-network <COMMAND>\n\nCommands:')
        for s in subs: print(f'  {s}  the {s} command')
        return 0
    sub, rest = argv[0], argv[1:]
    if sub not in subs: print(f"error: unrecognized subcommand '{sub}'", file=sys.stderr); return 2
    if rest == ['--help']:
        flags = {'who': '' if os.environ.get('FAKE_RN_NOJSON') else '--json', 'send': '--from --file --notify --fyi --reply-to',
                 'listen': '--as --wait'}.get(sub, '')
        print(f'Usage: reason-network {sub} [OPTIONS]\n\nOptions:\n  {flags}\n  -h, --help'); return 0
    if sub == 'who':
        if os.environ.get('FAKE_RN_WHO') is not None: print(os.environ['FAKE_RN_WHO']); return 0
        print(json.dumps({'team': d.get('team'), 'person': d.get('person'), 'machine': d.get('machine'),
                          'machines': d.get('machines', []), 'sessions': d.get('sessions', [])}, indent=2)); return 0
    if sub == 'held':
        h = d.get('held', [])
        if not h: print('Nothing held.'); return 0
        for m in h:
            meta = f" ({m['from_agent']})" if m.get('from_agent') else ''
            print(f"── {m['from']}{meta} · 2m ago · {m['id']}")
            print(m['body'] + '\n')
            for f in m.get('files', []): print(f"  file: {f['name']} (saved once approved)")
        print('`reason-network approve <id>` delivers, `reason-network reject <id>` drops (or --all).'); return 0
    if sub in ('approve', 'reject'):
        ids = set(rest)
        n = [m for m in d.get('held', []) if m['id'] in ids]
        d['held'] = [m for m in d.get('held', []) if m['id'] not in ids]
        d.setdefault('settled', []).extend({'id': m['id'], 'deliver': sub == 'approve'} for m in n); save(d)
        print(f"{'Delivered' if sub == 'approve' else 'Dropped'} {len(n)}."); return 0
    if sub == 'send':
        to, frm = rest[0], rest[rest.index('--from') + 1] if '--from' in rest else f"{d.get('person')}/terminal"
        body = sys.stdin.read()
        mid = '01JTESTSEND' + str(len(d.get('sent', []))).rjust(15, '0')
        d.setdefault('sent', []).append({'id': mid, 'to': to, 'from': frm, 'body': body}); save(d)
        print(f'→ {to}: delivered: {to} is busy, it sees this between tool calls\nmessage id {mid}'); return 0
    if sub == 'listen':
        name = rest[rest.index('--as') + 1] if '--as' in rest else 'agent'
        box = d.setdefault('inbox', {}).get(name, [])
        d['inbox'][name] = []; d.setdefault('registered', []).append(name); save(d)
        if not box: print(f"No messages. You are {d.get('person')}/{name}."); return 0
        for m in box:
            extra = f' reply_to="{m["reply_to"]}"' if m.get('reply_to') else ''
            print(f'<reason-message from="{m["from"]}" agent="{m.get("from_agent", "")}"{extra} id="{m["id"]}">\n{m["body"]}\n</reason-message>')
        print(f"From {box[-1]['from'].split('/')[0]}'s agent. Reply if useful: reason-network send {box[-1]['from']} --from {d.get('person')}/{name} \"<reply>\"")
        return 0
    if sub == 'folder':
        d.setdefault('folders', []).append({'path': rest[0], 'state': rest[1]}); save(d)
        print(f'Reason Network is {rest[1]} in {rest[0]}.'); return 0
    if sub == 'stop': d['stopped'] = d.get('stopped', 0) + 1; save(d); print('The daemon is not running.'); return 0
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8'); sys.stdin.reconfigure(encoding='utf-8')
    sys.exit(main(sys.argv[1:]))

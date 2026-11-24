"""ONE TASK THAT HOLDS EVERY KIND OF THING AN AGENT PUTS IN ITS TURN, to look at how each sits in the chat (the owner, 2026-11-23: "it should
adapt to the size of the item ... in general keep it left aligned"): tiles, a chart and a wide table drawn by `show`, a picture, an upright and
a landscape video, a PDF, an Excel sheet and a Word report, an email card, a post card with its picture and a bulk card of six emails.

    python tools/showcase_task.py --home PATH [--url http://127.0.0.1:7787] [--token T] [--each-card]

--home is the running app's TASKUARY_HOME - there is no default, so it never lands in a home by accident. The task is made through the app's
own door (POST /api/tasks, the owner token read from that home's config, or --token / TASKUARY_TOKEN); its turns are then written the way an
agent's session writes them - its words and its `show` calls as the ACP updates chatlog.feed keeps, its cards by the very tools it calls
(agenttools: propose_email, propose), each answer filed as the agent's comment. No route lets a page write an agent's turn, so this part
opens the same database beside the app (SQLite in WAL mode). Everything is invented Northwind content; nothing is sent, posted or pressed -
every card stays pending. Open the task the line prints (or reload it) to see it.

Cards stand ONE AT A TIME on a task (cardqueue.py): on the one task the email card stands and the post and the bulk card wait behind it.
--each-card puts the post card and the bulk card on a task of their own as well, so each can be seen standing."""
import argparse, json, math, os, struct, subprocess, sys, time, urllib.request, zlib
from pathlib import Path

TITLE = 'Showcase - how items sit in the chat'
SID = 'showcase'

def _png(w: int, h: int, px) -> bytes:
    "A PNG of `w`x`h` from px(x, y) -> (r, g, b): plain zlib, no imaging library."
    raw = b''.join(b'\0' + bytes(c for x in range(w) for c in px(x, y)) for y in range(h))
    def chunk(k, d): return struct.pack('>I', len(d)) + k + d + struct.pack('>I', zlib.crc32(k + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b'')

def _sky(x, y, w=1200, h=800):
    "A calm landscape: a sky over a hill, Northwind's colours."
    hill = h * .62 + 60 * math.sin(x / w * 6.3)
    return (88, 120, 96) if y > hill else (int(205 - y / h * 60), int(222 - y / h * 40), 238)

def _ffmpeg() -> str:
    "An ffmpeg to make the two videos with: the one imageio ships, else one on PATH, else ''."
    try: import imageio_ffmpeg; return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception: pass
    from shutil import which
    return which('ffmpeg') or ''

def _video(ff: str, out: Path, w: int, h: int, colour: str) -> bool:
    "A 4-second clip of `w`x`h`: a moving test pattern over the colour, H.264 so any browser plays it."
    src = f'testsrc2=size={w}x{h}:rate=24:duration=4,drawbox=x=0:y=0:w={w}:h={h}:color={colour}@0.25:t=fill'
    r = subprocess.run([ff, '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', src, '-pix_fmt', 'yuv420p', '-c:v', 'libx264', '-movflags', '+faststart', str(out)],
                       capture_output=True, text=True)
    return r.returncode == 0 and out.is_file()

TILES = {'root': 'k', 'title': 'Northwind renewals this quarter', 'elements': {'k': {'type': 'stats', 'props': {'items': [
    {'label': 'Due this quarter', 'value': 4}, {'label': 'Total', 'value': 18420, 'format': 'currency', 'note': 'across four vendors'},
    {'label': 'Biggest', 'value': 9310, 'format': 'currency', 'trend': {'dir': 'up', 'text': '+12% on last year'}}]}}}}
CHART = {'root': 'c', 'elements': {'c': {'type': 'chart', 'props': {'kind': 'bar', 'title': 'Renewal cost by vendor', 'format': 'currency', 'points': [
    {'label': 'Payworth', 'value': 9310, 'highlight': True}, {'label': 'Trainly', 'value': 5100}, {'label': 'Spendly', 'value': 2610},
    {'label': 'PhishGuard', 'value': 1400}]}}}}
TABLE = {'root': 't', 'elements': {'t': {'type': 'table', 'props': {'title': 'Every renewal, with who owns it', 'columns': [
    'Vendor', 'Plan', {'label': 'Seats', 'format': 'number'}, {'label': 'Per seat', 'format': 'currency'}, {'label': 'Total', 'format': 'currency'},
    'Renews', 'Owner', 'Notice period', 'Auto-renews', 'Note'], 'rows': [
    ['Payworth', 'Pro', 70, 133, 9310, '14 Oct', 'Erin Blake', '60 days', 'yes', 'Price went up 12% - ask for last year\'s rate'],
    ['Trainly', 'Team', 60, 85, 5100, '2 Nov', 'Gail Moreno', '30 days', 'no', 'Half the seats unused since June'],
    ['Spendly', 'Basic', 45, 58, 2610, '19 Nov', 'Paula Vance', '30 days', 'yes', 'Fine as it is'],
    ['PhishGuard', 'Standard', 70, 20, 1400, '30 Nov', 'Ray Colton', '90 days', 'yes', 'Notice window already closed'],
    ['Payworth', 'Payroll add-on', 70, 12, 840, '14 Oct', 'Erin Blake', '60 days', 'yes', 'Renews with the main plan'],
    ['Trainly', 'Content pack', 1, 600, 600, '2 Nov', 'Gail Moreno', '30 days', 'no', 'Only the sales team uses it']]}}}}
EMAIL = {'to': 'renewals@vendor.example', 'subject': 'Northwind renewal - can we hold last year\'s rate?',
         'text': "Hello,\n\nOur Payworth plan renews on 14 October at $9,310 - 12% over last year. Before it auto-renews, could you hold "
                 "last year's rate? We are 70 seats and have been with you three years.\n\nThanks,\nAlex Doyle, Northwind"}
POST = "Three years in, Northwind still runs payroll on one tool for 70 people. Renewal season is a good time to ask what each tool earns its seat for - we found four we use and two we only pay for."
BULK = [('erin@northwind.example', 'Erin'), ('gail@northwind.example', 'Gail'), ('paula@northwind.example', 'Paula'),
        ('ray@northwind.example', 'Ray'), ('marcus@northwind.example', 'Marcus'), ('omar@northwind.example', 'Omar')]
REPORT = ('# Q3 renewals - what to do before each date\n\n- Payworth: ask for last year\'s rate before 15 August (60 days\' notice).\n'
          '- Trainly: cut to 30 seats - half are unused since June.\n- Spendly: keep as it is.\n- PhishGuard: the notice window closed; plan for next year.\n\n'
          'Vendor | Total | Renews\nPayworth | 9310 | 14 Oct\nTrainly | 5100 | 2 Nov\nSpendly | 2610 | 19 Nov\nPhishGuard | 1400 | 30 Nov\n')
SHEET = 'Vendor | Seats | Per seat | Total\nPayworth | 70 | 133 | 9310\nTrainly | 60 | 85 | 5100\nSpendly | 45 | 58 | 2610\nPhishGuard | 70 | 20 | 1400\nAll | | | 18420\n'
PDF = '# Northwind - renewal brief\n\nFour tools renew this quarter, $18,420 in all.\n\nchart: Cost by vendor\nPayworth | 9310\nTrainly | 5100\nSpendly | 2610\nPhishGuard | 1400\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--home', required=True, help="the running app's TASKUARY_HOME")
    ap.add_argument('--url', default='', help='the running app (default: 127.0.0.1 and the port in its config)')
    ap.add_argument('--token', default='', help="the owner token (default: TASKUARY_TOKEN, else the home's config)")
    ap.add_argument('--each-card', action='store_true', help='also a task each for the post card and the bulk card, so each stands')
    a = ap.parse_args(argv)
    home = Path(a.home).expanduser().resolve()
    if not (home / 'taskuary.db').is_file() and not any(home.glob('*.db')): sys.exit(f'{home} holds no Taskuary database - give the home the app runs on')
    os.environ['TASKUARY_HOME'] = str(home)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from taskuary import agenttools, chatlog, config, outputs, proposals, slots, wrapup
    from taskuary.general import ASSISTANT_TYPE
    from taskuary.store import SQLiteStore
    srv = config.load().get('server') or {}
    url, tok = (a.url or f"http://127.0.0.1:{srv.get('port', 7787)}").rstrip('/'), a.token or os.getenv('TASKUARY_TOKEN') or srv.get('token') or ''

    store = SQLiteStore(config.db_path())
    def new_task(title: str, summary: str) -> int:
        "Made by the owner's own door, so the running app has it on its rail at once."
        rq = urllib.request.Request(f'{url}/api/tasks', json.dumps({'Title': title, 'Summary': summary}).encode(), method='POST',
                                    headers={'Content-Type': 'application/json', **({'X-Taskuary-Token': tok} if tok else {})})
        with urllib.request.urlopen(rq, timeout=20) as r: t = int(json.loads(r.read())['taskId'])
        # ...its chat begun in the log, empty, as the page's first read of a new task begins it - else that read freezes it from the old
        # list and the turns written here are lost (chatlog.migrate)
        for _ in range(50):
            if chatlog.migrated(store, t) or chatlog.migrate(store, t): return t
            time.sleep(.2)
        sys.exit(f'task {t}: its chat could not be begun in the log (no backup of the database yet?)')

    def draft(tid, text, to, subject, files=(), cc=(), mailbox='', guessed=(), slot=''):
        out = slots.draft(store, tid, text, to, subject, slot, 'agent', cc=cc, mailbox=mailbox, guessed=guessed)
        if out.get('ok') and files: out = {**out, **wrapup.attach_files(store, out['review_id'], files, 'agent')}
        return {**out, **wrapup.carries(store, out['review_id'])} if out.get('ok') and out.get('review_id') else out
    def propose(tid, p):
        q = proposals.queue(store, tid, agenttools.proposal_of(p), 'agent', refused=(miss := []))
        if not q: raise ValueError(proposals.refusal_line(miss[0] if miss else ''))
        return {'ok': True, 'queued': True, 'review': q['reviewId']}
    doors = {'draft': draft, 'propose': propose}

    def turn(tid: int, n: int, said: str, calls=(), answer: str = '', make=None):
        """One turn as an agent's session writes it: its words, then each tool it calls (the call's own answer on its step), then its answer.
        `make`: files it writes into the task's outputs folder while it works - drawn under the turn that made them."""
        chatlog.heard(store, tid, [('turn', f'{SID}:{tid}:{n}')], time.time())         # ...the turn begun, as a hand-over begins one
        chatlog.feed(store, tid, SID, 'acp', {'sessionUpdate': 'agent_message_chunk', 'messageId': f'{tid}.{n}.a', 'content': {'type': 'text', 'text': said}})
        if make: make()
        for i, (name, args) in enumerate(calls):
            out = agenttools.call(store, tid, name, args, doors)
            chatlog.feed(store, tid, SID, 'acp', {'sessionUpdate': 'tool_call', 'toolCallId': f'{tid}.{n}.{i}', 'title': name, 'kind': 'other', 'status': 'completed',
                                                  'rawInput': args, 'rawOutput': out, '_meta': {'taskuary': {'tool': f'mcp__taskuary__{name}'}}})
            time.sleep(.3)
        chatlog.flush(store, tid); chatlog.settled(10)
        store.add_comment(tid, 'agent', ASSISTANT_TYPE, answer)
        chatlog.settled(10); time.sleep(1.1)              # ...each turn in its own second: what it made is placed by its time

    tid = new_task(TITLE, 'Every kind of thing an agent puts in its turn - views, pictures, videos, files and cards - to look at how each sits in '
                          'the chat. Invented content; nothing here is sent.')
    out, work = outputs.folder(tid), outputs.work_folder(tid)
    out.mkdir(parents=True, exist_ok=True)
    ff = _ffmpeg()
    def media():
        (out / 'hill.png').write_bytes(_png(1200, 800, _sky))
        if not ff: print('no ffmpeg (pip install imageio-ffmpeg, or put ffmpeg on PATH): the two videos are left out'); return
        _video(ff, out / 'upright-clip.mp4', 720, 1280, 'teal'); _video(ff, out / 'landscape-clip.mp4', 1280, 720, 'orange')
    from taskuary import officefiles
    def files():
        officefiles.write(out / 'renewals.xlsx', SHEET); officefiles.write(out / 'renewal-report.docx', REPORT)
        officefiles.write(work / 'renewal-brief.pdf', PDF)

    turn(tid, 1, 'Here is where Northwind\'s renewals stand this quarter.', [('show', TILES), ('show', CHART)],
         'Payworth is the big one: $9,310, renewing on 14 October.')
    turn(tid, 2, 'And every line of it, with who owns each renewal:', [('show', TABLE)], 'Two need a word before their notice runs out.')
    turn(tid, 3, 'A picture for the post, and the two clips for the team page - one upright for phones, one landscape.',
         answer='All three are under this turn, as they were made.', make=media)
    turn(tid, 4, 'The brief as a PDF, the numbers as a sheet and the plan as a Word report:',
         [('show', {'files': [str(work / 'renewal-brief.pdf'), str(out / 'renewals.xlsx'), str(out / 'renewal-report.docx')]})],
         'All three are on the task.', make=files)
    post = {'action': 'run_tool', 'type': 'linkedin_post', 'text': POST, 'image': 'hill.png', 'why': 'the renewal-season post you asked for'}
    bulk = {'items': [{'to': to, 'subject': 'Your tools for next year', 'text': f'Hi {who},\n\nWhich of the tools you own do you still use every week? '
                       'One line back is plenty - I am sorting renewals.\n\nThanks,\nAlex'} for to, who in BULK]}
    turn(tid, 5, 'I wrote to Payworth about holding last year\'s rate:', [('propose_email', EMAIL)], 'It waits for your Send.')
    turn(tid, 6, 'The post, with the picture:', [('propose', post)], 'It waits for your Post.')
    turn(tid, 7, 'And the note to each tool owner:', [('propose_email', bulk)], 'Six emails, one card.')
    made = [tid]
    if a.each_card:
        for title, n, said, call in (('Showcase - a post card', 1, 'The post, with the picture:', ('propose', post)),
                                     ('Showcase - a bulk card', 1, 'The note to each tool owner:', ('propose_email', bulk))):
            t = new_task(title, 'One card of the showcase, standing on its own. Invented content; nothing here is sent.')
            if call[0] == 'propose':
                o = outputs.folder(t); o.mkdir(parents=True, exist_ok=True); (o / 'hill.png').write_bytes(_png(1200, 800, _sky))
            turn(t, n, said, [call], 'It waits for your press.'); made.append(t)
    store.close()
    for t in made: print(f'{url}/#task={t}')


if __name__ == '__main__': main()

"""Play a WhatsApp conversation through the real phone doorway and print exactly what the phone would receive - the text as the
bridge sends it (bubbles, WhatsApp emphasis) and the poll under it. Nothing reaches a phone: the bridge's send is replaced.

    python tools/wa_walk.py morning 1 2 next          # the demo world (invented work, a scripted model)
    python tools/wa_walk.py --home <dir> morning 7 1  # a COPY of a real home, with its real AI connection
    python tools/wa_walk.py --telegram morning 1      # the same doorway as Telegram spells it (buttons, no emphasis)

'morning' is the day's opener with its menu; a bare number is a poll tap (the pick runs as code, no model); anything else
is typed and goes to the model. Never point --home at the live ~/.taskuary: a walk marks items read and puts work on tasks.
"""
import os, sys, tempfile

args = sys.argv[1:]
home, CH = None, 'whatsapp'
if args[:1] == ['--telegram']: CH, args = 'telegram', args[1:]
if args[:1] == ['--home']: home, args = args[1], args[2:]
os.environ['TASKUARY_HOME'] = home or tempfile.mkdtemp(prefix='wa-walk-')
if not home: os.environ['TASKUARY_DEMO'] = '1'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest import mock
from loguru import logger
logger.remove()
from taskuary import config, demo, messengers, remote_assistant as ra
from taskuary.store import SQLiteStore

s = SQLiteStore(config.db_path())
if not home: demo.seed(s)
JID = '15550001111@s.whatsapp.net'
if CH == 'telegram': JID = '555000111'
DOOR = [{'channel': CH, 'label': CH.capitalize(), 'chat': JID, 'connectorId': 1, 'name': CH.capitalize()}]
out = []


def wa_send(store, jid, body, connector_id=None, poll=None):
    out.append((body, poll)); return {'ok': True}


def tg_send(store, chat_id, body, connector_id=None, buttons=None):
    out.append((body, [str(b) for b in buttons] if buttons else None)); return {'ok': True}


with mock.patch.object(messengers, 'wa_send', wa_send), mock.patch.object(messengers, 'tg_send', tg_send), \
        mock.patch.object(ra, 'doorways', lambda store: DOOR), \
        mock.patch.object(ra, 'quiet', lambda *a: True):
    for t in args or ['morning']:
        out.clear()
        pick = t.isdigit()
        print('\n' + '=' * 78 + f'\nYOU: {t}' + ('   (poll tap)' if pick else '') + '\n' + '-' * 78)
        if t == 'morning': ra.morning_line(s, force=True)
        else: ra.respond(s, CH, JID, t, 1, poll=pick)
        for body, poll in out:
            print(body)
            if poll: print(f"  [{'BUTTONS' if CH == 'telegram' else 'POLL'}] " + ' | '.join(f'{i}. {p}' for i, p in enumerate(poll, 1)))
            print('  ' + '·' * 30)

"""A stand-in Taskuary for tests/test_unpack_folder.py: it starts children down spawn's road, says their pids, and waits to be killed.

TQ_SPAWN_MODE=parent (the default): one tied child that starts a grandchild of its own, and one child started `outlive=True`; prints
`<child> <grandchild> <outliver>`. TQ_SPAWN_MODE=sleep: just a process that runs until it is ended; =say: one line said, and it ends;
=agent: an agent that starts a command of its own that runs on, writes that command's pid to the file TQ_SPAWN_PID names, and waits."""
import os, subprocess, sys, time
from pathlib import Path

if os.environ.get('TQ_SPAWN_MODE') == 'sleep': time.sleep(120); sys.exit()
if os.environ.get('TQ_SPAWN_MODE') == 'agent':
    kid = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
    Path(os.environ['TQ_SPAWN_PID']).write_text(str(kid.pid)); time.sleep(120); sys.exit()
if os.environ.get('TQ_SPAWN_MODE') == 'say': print('the page is open'); sys.exit(3)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from taskuary import spawn

SLEEP = 'import time; time.sleep(120)'
KID = 'import subprocess, sys, time; p = subprocess.Popen([sys.executable, "-c", %r]); print(p.pid, flush=True); time.sleep(120)' % SLEEP
kid = spawn.popen([sys.executable, '-c', KID], stdout=subprocess.PIPE, text=True)
grand = kid.stdout.readline().strip()
out = spawn.popen([sys.executable, '-c', SLEEP], outlive=True)
print(kid.pid, grand, out.pid, flush=True)
time.sleep(120)

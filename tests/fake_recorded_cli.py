"""A stand-in CLI that replays one recorded stream from tests/fixtures/agent_steps, whatever flags it is launched with
(tests/test_agent_steps_backends.py). It reads nothing else and runs nothing."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / 'fixtures' / 'agent_steps'
sys.stdin.read()
name = Path(sys.argv[1]).name
sys.stdout.write((HERE / name).read_text(encoding='utf-8'))
sys.stdout.flush()

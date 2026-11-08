"""ONE WAY TO BRING A PAGE UP (the owner, 2026-11-07). Asked for a report with no books connected, the task agent wrote "you can connect your
books here (for example QuickBooks or Intacct)" - the owner had to leave the chat to find the card - while the dock linked the real card.
The dock and every task agent now read one line (words.LINK_LINE); the `show` tool's button takes the same addresses, and the chat opens them
in place (md.jsx -> appLinks.openAppLink, website/test/canvasLinks.test.mjs). Invented people."""
import re

from taskuary import general, viewspec, words
from taskuary.store import MemoryStore

ADDRS = [a.rstrip('.') for a in re.findall(r'#[\w=&%.:/-]+', words.LINK_LINE.replace('#settings=<page>', '').replace('#report=<id>', ''))]


def test_the_dock_and_a_task_agent_read_the_same_line_once():
    s = MemoryStore()
    dock = s.create_task({'Title': 'Taskuary guide', 'Kind': 'general', 'Status': 'open', 'SourceRef': general.DOCK_TAG}, 'owner')
    own = s.create_task({'Title': 'Month-end spend report', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
    for tid in (dock, own): assert general._prompt(s, tid)[0].count(words.LINK_LINE) == 1
    assert '#connector=quickbooks' in words.LINK_LINE                 # the form that opens ONE card (canvasLinks: #connector=<type>)


def test_every_address_it_teaches_is_one_the_show_button_takes():
    assert {'#task=1', '#connector=quickbooks', '#connections', '#settings=policies', '#settings=updates', '#report=new', '#report=reports'} <= set(ADDRS)
    for h in ADDRS + ['#connector=quickbooks&step=1']:
        out = viewspec.check({'root': 'b', 'elements': {'b': {'type': 'button', 'props': {'label': 'Open it', 'open': h}}}})
        assert out['elements']['b']['props']['open'] == h

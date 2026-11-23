"""THE GATE (gate.py, redesign R5): one table of what waits for the owner's press, one check point every road calls. Code decides where code
can know the act; a separate guard model reads a press on a page only where facts cannot, once per control per page."""
import json, os, re, tempfile
from types import SimpleNamespace
from unittest import mock

from taskuary import browsergate as bg, gate
from taskuary.store import MemoryStore
from taskuary.testing import Factory

SIGNUP = 'https://app.vendor.example/signup'
FORM = '- textbox "Work email" [ref=e1]\n- textbox "Password" [ref=e2]\n- checkbox "I agree" [ref=e3]\n- button "Create account" [ref=e4]'


class Brain:
    takes_want = True
    def __call__(self, *a, **k): return self


def model(v, calls):
    "The guard model stood in: `v` for every act it is shown; `calls` counts its asks."
    bg.SEEN.clear()
    def ask(brain, system, user, want=None, need=(), **kw):
        calls.append(user)
        return SimpleNamespace(data={'acts': [v] * len(re.findall(r'^ACT \d+:', user, re.M))})
    return mock.patch('taskuary.llm.ask_json', ask)


def page(snap=FORM, url=SIGNUP, **kw): return mock.patch.object(bg, 'page', return_value={'url': url, 'open': True, 'elements': snap, **kw})
def cards(s, tid): return [json.loads(r['DraftText']) for r in s._rows("SELECT DraftText FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (tid,))]
def held(out): return (out.get('hookSpecificOutput') or {}).get('permissionDecision') == 'deny'


def world(ask='Sign me up for a free account on vendor.example and pull their price list.'):
    s = MemoryStore(); tid = Factory(s).task('Pull the vendor price list')
    from taskuary import general
    s.add_comment(tid, 'owner', general.USER_TYPE, ask)
    return s, tid


def test_a_free_sign_up_he_asked_for_runs_with_no_card():
    "Its boxes typed and ticked by fact - never put to the model - and its Create account, on an account form the agent typed, runs."
    s, tid, calls = *world(), []
    made = [{'k': 'email', 't': 'email', 'v': 'robin.tests@mail.example'}, {'k': 'tos', 't': 'checkbox', 'v': 'on'}]
    with page(fields=made, pw=True), model({'big': True, 'kind': 'speaks', 'sure': True, 'irreversible': True, 'what': 'Create the account'}, calls):
        for cmd in ('agent-browser fill @e1 "robin.tests@mail.example"', 'agent-browser click @e3', 'agent-browser click @e4'):
            assert gate.check(s, tid, 'run1', cmd, run=True, brain=Brain()) == {}, cmd
    assert cards(s, tid) == [] and len(calls) == 1, 'one ask, for the button; the boxes were facts'


def test_a_purchase_waits_for_him_and_is_never_the_agents_press():
    s, tid, calls = *world('Buy the Pro plan for me.'), []
    with page('- button "Pay $49" [ref=e9]'), model({'big': True, 'kind': 'money', 'sure': True, 'irreversible': True, 'what': 'Pay $49 for Pro'}, calls):
        out = gate.check(s, tid, 'run1', 'agent-browser click @e9', run=True, brain=Brain())
    assert held(out) and 'spends the owner' in gate.reason(out) and 'hand_over' in gate.reason(out)


def test_a_post_waits_as_one_card_until_his_press_covers_it():
    s, tid, calls = *world('Draft the launch post.'), []
    pg = dict(fields=[{'k': 'body', 't': 'textarea', 'v': 'We launched'}])
    v = {'big': True, 'kind': 'speaks', 'sure': True, 'irreversible': True, 'what': 'Post the launch note on social.example'}
    with page('- button "Post" [ref=e5]', **pg), model(v, calls):
        out = gate.check(s, tid, 'run1', 'agent-browser click @e5', run=True, brain=Brain())
        assert held(out) and gate.TABLE['speaks'].why in gate.reason(out)
        [c] = cards(s, tid)
        gate.remember(s, tid, c['keys'], 'approved')                                # his press on that card
        assert gate.check(s, tid, 'run1', 'agent-browser click @e5', run=True, brain=Brain()) == {}, 'the same post, his press covers it'
    assert len(calls) == 1, 'one verdict for the control on that page'


def test_a_delete_outside_the_work_folder_waits_and_one_inside_runs():
    s, tid = world('Tidy up.')
    work, docs = tempfile.mkdtemp(), os.path.join(os.path.expanduser('~'), 'Documents', 'old-reports')
    assert gate.check(s, tid, 'run1', 'rm -rf build', work) == {}
    out = gate.check(s, tid, 'run1', f'rm -rf "{docs}"', work)
    assert held(out) and gate.TABLE['erase'].why in gate.reason(out)
    [c] = cards(s, tid)
    assert c['action'] == 'shell_act' and 'old-reports' in c['what']


def test_one_verdict_per_control_per_page_whatever_its_ref():
    "A snapshot renumbers its refs: the same button on the same page and form is the same question, asked once."
    s, tid, calls = *world(), []
    ok = {'big': False, 'sure': True, 'irreversible': False, 'what': 'Next'}
    with model(ok, calls):
        for ref in ('e4', 'e14', 'e24'):
            with page(f'- button "Next" [ref={ref}]'): assert gate.check(s, tid, 'run1', f'agent-browser click @{ref}', run=True, brain=Brain()) == {}
        with page('- button "Delete account" [ref=e4]'): gate.check(s, tid, 'run1', 'agent-browser click @e4', run=True, brain=Brain())
    assert len(calls) == 2, 'another control on the page is its own question'


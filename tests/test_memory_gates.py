"""WHAT THE OWNER SAID THEY DO NOT CARE ABOUT, EVERYWHERE IT DECIDES (the owner, 2026-10-27: "if I don't care about something the system
knows it" - "certain processes are legacy, I haven't turned them off but I don't care about them"). A report finding becomes a task through
two gates - the report's routing judge, then triage - and the judge read no memory at all; "I don't care about X" said to the Assistant
opened the notes page and was never written. Now the words land in LEARNED.md's "What you care about", and that section reaches the judge,
triage and the Assistant's own chat, and survives the triage budget. Invented Northwind world; the brains are mocked."""
import json
from unittest import mock
from taskuary import concierge, ingest, learned_cut as lc, memoryedit, reports, server
from taskuary.store import MemoryStore

LEGACY = "I don't care about the legacy export job any more - it still runs, but it is not mine"
JSON_FYI = '{"intent": "fyi", "kind": "task", "why": "x", "title": "t", "summary": "s"}'


def _care(s): return [raw for raw, _ in lc.lines(s.get_doc('learned') or '', lc.CARE)]


def _remembered():
    s = MemoryStore()
    memoryedit.remember(s, LEGACY, section='care')
    return s


def test_the_routing_judge_reads_the_dont_care_line():
    s, seen = _remembered(), {}
    cfg = {'title': 'Nightly process check', 'route': {'triage': {'how': 'ai', 'when': 'a process failed'}}}
    def llm(system, user, **k): seen['sys'] = system; return 'TRIAGE: no'
    d = reports.decide_for(s, cfg, reports.read_result('1 rows', 'legacy export job: FAILED'), llm)
    assert d['triage'] is False
    assert LEGACY in seen['sys'] and 'is a no for TRIAGE and ALERT' in seen['sys']


def test_no_memory_leaves_the_judge_prompt_as_it_was():
    seen = {}
    def llm(system, user, **k): seen['sys'] = system; return 'TRIAGE: yes'
    cfg = {'route': {'triage': {'how': 'ai', 'when': 'a process failed'}}}
    reports.decide_for(MemoryStore(), cfg, reports.read_result('1 rows', 'x failed'), llm)
    assert seen['sys'] == reports.JUDGE_SYSTEM + reports.judge_prompt(cfg)


def test_triage_reads_the_dont_care_line_on_a_report_run():
    s, seen = _remembered(), {}
    def llm(system, user, **k): seen['sys'] = system; return JSON_FYI
    ingest.judge(s, {'external_id': 'report:7:x', 'channel': 'report', 'subject': 'Nightly process check — 1 rows',
                     'body': 'legacy export job: FAILED', 'from_name': 'Nightly process check', 'conversation_id': 'report:7',
                     'watch_for': 'a process failed'}, llm)
    # the owner's own line is in the EVIDENCE (LEARNED.md's standing lines, ingest.applicable_notes), this mail's own part of the prompt...
    assert LEGACY in seen['sys'].rest and 'what they told you they care about, or do not' in seen['sys'].rest
    # ...and the memory above it is whole, the same bytes on every mail: taking the line out of it made a memory per mail, and no
    # provider reads from its cache what is new each time (2026-11-11)
    assert sum(LEGACY in b for b in seen['sys'].blocks) == 1


def test_dont_care_said_to_the_assistant_lands_in_what_you_care_about():
    s = MemoryStore()
    dock = concierge.general.dock_task(s, 'owner')[0]['TaskId']
    out = concierge.call_turn(s, dock, {'kind': 'memory.remember', 'params': {'note': LEGACY}}, None, LEGACY)
    assert out['did'] == 'memory.remember' and not out.get('open'), 'kept at once, not the notes page'
    assert out['say'] == concierge.GOT_IT and '](' not in out['say'], 'no receipt, and no link for the page to follow'
    assert f'- {LEGACY}' in _care(s)
    # ...and the phone's road (server._run_operation) writes the same line, never a saved note
    s2 = MemoryStore()
    with mock.patch.object(server, 'store', s2):
        r = server._run_operation({'kind': 'memory.remember', 'target': 0, 'params': {'note': 'The payroll mirror is legacy - not mine to watch'}}, None)
    assert r['learned']['section'] == 'care' and '- The payroll mirror is legacy - not mine to watch' in _care(s2)


def test_the_owners_dont_care_line_survives_triages_budget():
    """Learned care lines fill the section first; the owner's line is appended last - it used to be the first cut."""
    s = MemoryStore()
    filler = [f'- Vendor statements from vendor{i}.example are fyi, never a task, whatever they say about the balance owed [s:5 | ev: m{i}a, m{i}b, '
              f'm{i}c | seen: 2026-10-20 | k: vendor statements {i}]' for i in range(14)]
    people = [f'- Person {i} (p{i}@northwind.example) is answered the same day [s:5 | ev: o{i}a, o{i}b, o{i}c | seen: 2026-10-20 | k: person {i}]'
              for i in range(8)]
    doc = s.get_doc('learned').replace(lc.CARE + '\n', lc.CARE + '\n' + '\n'.join(filler) + '\n', 1)
    doc = doc.replace(lc.PEOPLE + '\n', lc.PEOPLE + '\n' + '\n'.join(people) + '\n', 1)
    s.save_doc('learned', doc, 'reflect')
    memoryedit.remember(s, LEGACY, section='care')
    assert sum(len(l) + 1 for l in filler) > lc.BUDGET['triage']
    msg = {'from_email': 'p1@northwind.example', 'to': ['alex@northwind.example']}
    got = lc.for_reader(s, 'triage', lc.about_mail(msg), people=lc.people_of(msg))
    assert LEGACY in got and 'Person 1 (p1@' in got, "the sender's own line still reaches triage's priority"
    assert 'k: vendor statements 13' not in got and lc.over_budget(s), 'the learned lines are what the budget leaves out'
    # ...and the Advisor, whose people lines about others no longer push the care lines out first
    assert LEGACY in lc.for_reader(s, 'advisor', {'sender': 'p1@northwind.example'})


def test_the_assistants_chat_reads_the_memory():
    s = _remembered()
    assert LEGACY in concierge._system(s)
    assert 'WHAT YOU KNOW ABOUT HOW THE OWNER WORKS' not in concierge._system(MemoryStore()), 'a fresh memory is placeholders'


def test_agents_read_it_on_demand():
    """The owner, 2026-10-27: "agents can look at the memory LEARNED.md if they need it" - the brief points at it, the tool reads it. What
    he said in his own words rides in every brief (the walk, 2026-11-21: a rule he told one agent never reached the next); what was learned
    is the tool's to read."""
    from taskuary import agenttools, context
    s = _remembered()
    tid = s.create_task({'Title': 'Check the nightly run', 'Kind': 'general', 'Status': 'open'}, 'router')
    with mock.patch('taskuary.origin.of_task', return_value=('owner', '')):
        built = context.build(s, tid)
    assert LEGACY in built and context.MEMORY_LINE in built
    got = agenttools.call(s, tid, 'owner_memory', {}, {})
    assert f'## What you care about\n- {LEGACY}' in got, 'under its own heading'
    assert LEGACY in agenttools.call(s, tid, 'owner_memory', {'section': 'care'}, {})
    assert 'nothing learned' in agenttools.call(s, tid, 'owner_memory', {'section': 'promises'}, {})


def test_the_routing_judge_and_triage_read_every_section():
    s = _remembered()
    memoryedit.remember(s, 'Alex keeps Fridays for vendor renewals', section='work')
    assert 'Fridays for vendor renewals' in reports.judge_memory(s, {'title': 'Nightly process check'})


def test_a_fact_told_to_the_assistant_is_kept_and_answered_in_its_own_few_words_never_a_receipt():
    """The owner, 2026-11-14 ("memory should be silent"), from the recorded real chat: told "Marcus moved to security, laptop faults go to Omar
    now", the Assistant answered with four lines - "Remembered under Your people in your memory (read by triage (priority only) · drafts ·
    the Advisor · the Assistant · agents): “...” - “...” is kept as history, true until ..." - and the page followed the receipt's link to
    the Memory page, off the task the owner was on. Now: its own words above the CALL, or two words; nothing for the page to open."""
    s = MemoryStore()
    dock = concierge.general.dock_task(s, 'owner')[0]['TaskId']
    call = {'kind': 'memory.remember', 'params': {'note': 'Marcus Reed moved to security; laptop and badge faults go to Omar Keller now', 'section': 'people'}}
    tok = concierge._TURN.set({'lead': 'Got it - Omar for laptop and badge faults.'})
    try: out = concierge.call_turn(s, dock, call, None, 'Marcus moved to security, laptop faults go to Omar now')
    finally: concierge._TURN.reset(tok)
    assert out['say'] == 'Got it - Omar for laptop and badge faults.' and 'go to Omar Keller now' in s.get_doc('learned')
    for no in ('Remembered', 'memory', 'read by', '](', '#about'): assert no not in out['say'], no
    # ...with no words of its own, a plain two; and the guidance is one sentence where the tool is described
    out = concierge.call_turn(s, dock, {'kind': 'memory.remember', 'params': {'note': 'Gail always wants budget figures rounded to the nearest thousand.'}}, None, 'remember that')
    assert out['say'] == concierge.GOT_IT
    assert 'never that it was saved, where, or who reads it' in concierge.turn_system(s)
    # ...and a task's agent is told the same of its own tool: a few natural words, never a report of the save
    from taskuary import agenttools
    assert 'never say that you saved it, or where' in agenttools.TOOLS['remember'][1]

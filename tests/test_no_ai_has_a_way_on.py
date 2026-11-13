"""EVERY "NO AI CONNECTED" MESSAGE HAS A CONNECT AN AI BUTTON (owner-approved, 2026-10-21, the UI/UX audit's W11).

Each said an AI was needed and gave nothing to press - a typed request with no AI got "Nothing's waiting. Connect an AI under
Connections -> AI ..." and the chips under it were the empty table's own. The chat's no-AI answer now leads its chips with Connect an
AI, which opens Connections at the AI cards; a phone chat, which has no page to open, keeps the words alone."""
from taskuary import concierge, words
from taskuary.store import MemoryStore


def test_a_typed_request_with_no_ai_carries_connect_an_ai():
    out = concierge.say(MemoryStore(), 'bring up the invoice from Ray', llm=None)
    lead = (out.get('chips') or [{}])[0]
    assert (lead.get('verb'), lead.get('label'), lead.get('href')) == ('go', 'Connect an AI', words.href('ai')), out


def test_the_phone_keeps_the_words_alone():
    tok = concierge.DELIVERY.set(concierge.PHONE)
    try: out = concierge.say(MemoryStore(), 'bring up the invoice from Ray', llm=None)
    finally: concierge.DELIVERY.reset(tok)
    assert not any(c.get('label') == 'Connect an AI' for c in out.get('chips') or []), out


def test_a_typed_request_with_no_ai_and_nothing_waiting_leads_with_the_ai_it_needs():
    # "set up a report of my open tasks" with no AI answered "Nothing's waiting." first - true, and no answer to the ask (the overnight audit,
    # 2026-11-12): the line is what it needs, its button under it
    out = concierge.say(MemoryStore(), 'set up a report of my open tasks', llm=None)
    assert not out['say'].startswith(concierge.ALL_DONE) and words.name('ai') in out['say'], out['say']

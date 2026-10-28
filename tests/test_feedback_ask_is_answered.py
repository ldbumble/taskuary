"""Asked for thoughts on a draft pasted into the mail, the writer answered "I'll review this and send you my thoughts" (2026-10-28) -
a promise to read what it already had. These pin that the writer gets the WHOLE pasted draft, that its prompt forbids the promise,
and that a promise-only reply to a mail with something in it is drafted once more, then failed with a reason the owner sees."""
import pytest

from taskuary import responder
from taskuary.store import MemoryStore

ME, ERIN = 'alex@northwind.example', 'erin@northwind.example'
SECTIONS = ['SEO: organic sessions rose after the site audit; the blog moved to the main domain and the old links redirect.',
            'Tracking: the form events double-counted on the portal, so September leads read high; that is fixed from October 3.',
            'Dashboard: one page now shows spend, leads and cost per lead by channel, refreshed every morning.',
            'Next: a webinar in November, the newsletter back to monthly, and a test of two landing pages for the demo request.']
DRAFT = ('Hi all, here is where marketing stands for September and October.\n\n'
         + '\n\n'.join(f'{s} ' + 'Detail on this point so the update is as long as the real one was. ' * 6 for s in SECTIONS)
         + '\n\nThanks,\nErin')
BODY = f'This is the draft for the email I would send to everyone. Let me know your thoughts.\n\n{DRAFT}\n\nErin Blake\nNorthwind'


@pytest.fixture
def s():
    v = MemoryStore(); v.set_setting('owner_email', ME, 'test'); v.set_setting('owner_name', 'Alex Doyle', 'test')
    yield v
    v.close()


def ask(s, body=BODY):
    tid = s.create_task({'Title': 'Marketing update draft', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
    s.add_message({'TaskId': tid, 'ExternalId': f'graph:erin-{tid}', 'ConversationId': f'mkt-{tid}', 'Channel': 'email', 'SourceName': ME,
                   'Subject': 'Marketing update - draft', 'FromEmail': ERIN, 'FromName': 'Erin Blake', 'BodyText': body,
                   'SentAt': '2026-10-27 09:00:00', 'Status': 'routed', 'Direction': 'in'})
    return tid


def writer(*said):
    calls, said = [], list(said)
    def llm(system, user, **k): calls.append({'system': system, 'user': user, **k}); return said.pop(0) if len(said) > 1 else said[0]
    return llm, calls


GOOD = 'Hi Erin,\n\nReads well. Three things:\n1. Say the September lead count was inflated by the tracking bug.\n2. Put the dashboard link up top.\n3. Cut the webinar to one line.\n\nAlex'
LATER = "Hi Erin,\n\nThanks for sending this. I'll review this and send you my thoughts.\n\nAlex Doyle"


def test_the_writer_gets_the_whole_pasted_draft_and_the_no_promise_rule(s):
    assert len(BODY) > 1500
    llm, calls = writer(GOOD)
    assert responder.draft_reply(s, ask(s), llm=llm) == GOOD
    user, system = ' '.join(calls[0]['user'].split()), calls[0]['system']
    assert all(' '.join(x.split()) in user for x in SECTIONS)            # every section of the pasted draft, none cut
    assert 'Detail on this point' in user.split(SECTIONS[-1])[1]          # ...through to the end of the last one
    assert 'FEEDBACK' in system and "I'll review this and send you my thoughts" in system and 'Never answer with a promise' in system
    assert calls[0]['max_tokens'] == responder.FEEDBACK_TOKENS and len(calls) == 1


def test_a_promise_only_reply_is_asked_for_again_then_failed_with_the_reason(s):
    tid = ask(s)
    llm, calls = writer(LATER, GOOD)
    assert responder.draft_reply(s, tid, llm=llm) == GOOD and len(calls) == 2 and 'YOUR FIRST DRAFT only promised' in calls[1]['user']
    llm, calls = writer(LATER)
    with pytest.raises(RuntimeError, match='only promised to look into it later'): responder.draft_reply(s, tid, llm=llm)
    assert len(calls) == 2


def test_the_reason_lands_on_the_review_the_owner_sees(s):
    from taskuary import ingest
    tid = ask(s)
    mid = s.list_messages(tid)[0]['MessageId']
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'DraftText': '', 'Status': 'pending', 'Reason': 'asks for thoughts'})
    llm, _ = writer(LATER)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr('taskuary.llm.build_llm', lambda *a, **k: llm)
        ingest._auto_draft(s, tid, rid)
    assert 'only promised to look into it later' in (s.get_review(rid).get('DraftError') or '')


def test_needs_is_said_to_the_owner_never_mailed(s):
    llm, _ = writer('NEEDS: the attached budget sheet did not come through')
    with pytest.raises(RuntimeError, match='needs the attached budget sheet did not come through'): responder.draft_reply(s, ask(s), llm=llm)


def test_a_short_ask_is_never_answered_with_a_promise_either(s):
    """The owner, 2026-10-28: "don't draft AI slop answers 'I'm looking into it'" - a short ask that needs work gets no placeholder:
    asked once more, then not drafted (the reply task then goes to an agent, test_reply_needs_agent)."""
    llm, calls = writer("I'll take a look this afternoon.")
    tid = ask(s, 'Can you look at the portal login issue when you get a chance?')
    with pytest.raises(responder.NotDrafted): responder.draft_reply(s, tid, llm=llm)
    assert len(calls) == 2 and calls[0]['max_tokens'] == responder.REPLY_TOKENS


def test_an_owner_instruction_is_theirs_even_if_it_promises(s):
    llm, calls = writer(LATER)
    assert responder.draft_reply(s, ask(s), llm=llm, nudge='tell her I will read it tonight') == LATER and len(calls) == 1


@pytest.mark.parametrize('text,want', [
    (LATER, True), ("I'll take a look and get back to you.", True), ('Thanks! Will review and circle back.', True),
    (GOOD, False), ("Looks good. I'll send it to the team Friday.", False), ('Thanks, noted.', False)])
def test_promise_only(text, want): assert responder.promise_only(text, 'Alex Doyle') is want

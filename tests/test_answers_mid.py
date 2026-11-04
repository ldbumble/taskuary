"""A draft remembers which mail it answers (delivery target), apart from the newest mail it saw (freshness)."""
from taskuary.store import MemoryStore


def test_a_review_keeps_its_target_and_why_apart_from_its_freshness():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Repair the export', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
    rid = s.add_review({'TaskId': tid, 'MessageId': 10, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Done.'})
    s.update_review_message(rid, 12); s.set_review_answers(rid, 11); s.set_review_why(rid, 'Erin asked for the export. ' + 'x' * 600)
    r = s.get_review(rid)
    assert (r['MessageId'], r['AnswersMid']) == (12, 11) and r['DraftWhy'].startswith('Erin asked') and len(r['DraftWhy']) <= 400
    s.cx.execute("UPDATE review SET DeliveryState='sent' WHERE ReviewId=?", (rid,))
    s.set_review_answers(rid, 10); s.set_review_why(rid, 'later')
    r = s.get_review(rid)
    assert r['AnswersMid'] == 11 and r['DraftWhy'].startswith('Erin asked')
    s.set_review_answers(s.add_review({'TaskId': tid, 'MessageId': 1, 'Kind': 'draft_reply', 'Status': 'pending'}), None)

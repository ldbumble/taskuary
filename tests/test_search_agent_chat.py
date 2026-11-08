"""F28: search reaches the agent conversation - the owner's lines, the agent's answers, its drafts - never Taskuary's machinery."""
from taskuary import search
from taskuary.general import ASSISTANT_TYPE, BRIEF_ACTOR, SUMMARY_TYPE, USER_TYPE
from taskuary.store import MemoryStore


def test_a_chat_only_word_is_found_under_a_title_hit_tagged_and_at_its_line():
    s = MemoryStore()
    titled = s.create_task({'Title': 'Quokka badge order', 'Kind': 'general', 'Status': 'open'}, 't')
    chat = s.create_task({'Title': 'Plan the offsite', 'Kind': 'general', 'Status': 'open'}, 't')
    drafted = s.create_task({'Title': 'Reply to Erin', 'Kind': 'general', 'Status': 'open'}, 't')
    hidden = s.create_task({'Title': 'Machinery only', 'Kind': 'general', 'Status': 'open'}, 't')
    s.add_comment(chat, 'owner', USER_TYPE, 'book the room')
    cid = s.add_comment(chat, 'agent', ASSISTANT_TYPE, 'The quokka room at the venue is free on Friday.')
    s.add_review({'TaskId': drafted, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Erin, the zephyrine invoice is attached.'})
    s.add_comment(hidden, BRIEF_ACTOR, USER_TYPE, 'quokka zephyrine brief')            # Taskuary's brief to the agent
    s.add_comment(hidden, 'agent', SUMMARY_TYPE, '{"did": "quokka zephyrine"}')         # a turn's summary JSON
    h = [x for x in search.everything(s, 'quokka')['hits'] if x['type'] == 'task']
    assert [x['tid'] for x in h] == [titled, chat]
    c = h[1]
    assert c['tag'] == 'in agent chat' and c['line'] == f'comment-{cid}' and c['who'] == 'the agent' and 'quokka room' in c['snippet']
    d = [x for x in search.everything(s, 'zephyrine')['hits'] if x['type'] == 'task']
    assert [(x['tid'], x['who']) for x in d] == [(drafted, 'a draft')]
    assert not any(x['tid'] == hidden for x in search.everything(s, 'quokka zephyrine')['hits'] if x.get('tid'))

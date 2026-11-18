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


def test_the_assistants_own_chat_is_no_task_hit():
    """The demo's search for "overtime" listed "Taskuary guide · TQ-1000000001" with its snippet the raw card marker the Assistant's
    line carries (`<!-- tq:card {"key": ..., "lane": "approve", ...} -->`): the dock is the Assistant's chat, which no task list shows."""
    s = MemoryStore()
    dock = s.create_task({'Title': 'Taskuary guide', 'Kind': 'general', 'Status': 'open', 'SourceRef': 'assistant:dock'}, 't')
    s.add_comment(dock, 'assistant', ASSISTANT_TYPE, 'Opened TQ-0031.\n\n<!-- tq:card {"title": "September overtime by site"} -->')
    assert not [x for x in search.everything(s, 'overtime')['hits'] if x.get('tid') == dock]


def test_his_line_with_a_file_reads_as_his_words_and_the_files_name_never_the_block():
    """The attach stress round, 2026-11-18: a heard line keeps its files in a block for the agent (general.with_files), and search drew that
    block as his words - "look at this ATTACHED IMAGES (read these files) /home/.../scratch/outputs/TQ-0001/..." - and found the line by a word
    of the folder it was copied into."""
    from taskuary.general import with_files
    s = MemoryStore()
    tid = s.create_task({'Title': 'Plan the offsite', 'Kind': 'general', 'Status': 'open'}, 't')
    s.add_comment(tid, 'owner', USER_TYPE, with_files('look at this quokka', ['/home/alex/.taskuary/scratch/outputs/TQ-0001/venue plan.png']))
    [h] = [x for x in search.everything(s, 'quokka')['hits'] if x.get('tid') == tid]
    assert 'ATTACHED' not in h['snippet'] and 'scratch' not in h['snippet'] and 'look at this quokka' in h['snippet'], h['snippet']
    assert [x['snippet'] for x in search.everything(s, 'venue plan')['hits'] if x.get('tid') == tid] == ['look at this quokka · venue plan.png']
    assert not [x for x in search.everything(s, 'scratch')['hits'] if x.get('tid') == tid]

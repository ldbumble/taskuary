"""Who asked, by name (the owner, 2026-09-28: "the name of the email is hamos but it should pull the correct name ...
that's the first and last letter of their name").

Triage was handed only the sender's ADDRESS, so the summary every surface leads with named people after their
mailbox ("hamos@" -> "Hamos"). It now gets the display name too, as a person is called: Outlook's directory writes
"Last, First M." and appends " at <organisation>" to people outside it.
"""
import inspect

from taskuary import remote_assistant as ra, triage


def test_a_directory_name_reads_as_a_person_is_called():
    assert triage.person_name('Doyle, Alex M. at Northwind') == 'Alex M. Doyle'
    assert triage.person_name('Van Dyke, Paula') == 'Paula Van Dyke'
    assert triage.person_name('"Reed, Marcus"') == 'Marcus Reed'
    assert triage.person_name('Erin Blake at Northwind') == 'Erin Blake'
    assert triage.person_name('Erin Blake') == 'Erin Blake'


def test_an_address_is_never_a_name():
    assert triage.person_name('eblake@northwind.example') == ''
    assert triage.person_name('') == ''


def test_triage_is_handed_the_name_and_told_to_use_it():
    src = inspect.getsource(triage)
    assert "'from_name': person_name(msg.get('from_name'))" in src
    assert 'by `from_name`' in triage.TASK_FIELDS


def test_the_phone_names_the_asker_the_same_way():
    assert ra.story_who({'who': 'Doyle, Alex M. at Northwind', 'channel': 'email'}) == 'Alex M. Doyle'

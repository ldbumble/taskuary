from taskuary import hooks

def test_a_why_that_already_says_waiting_is_not_said_twice():
    assert hooks.ended_short('waiting for the build to finish') == 'it ended its turn still waiting on the build to finish'
    assert hooks.ended_short('Still waiting on its sub-agent') == 'it ended its turn still waiting on its sub-agent'
    assert hooks.ended_short('') == 'it ended its turn still waiting on work of its own'

def test_the_turn_end_judge_is_told_a_person_it_waits_on_is_not_unfinished_work():
    assert 'waiting on a PERSON' in hooks.ENDED_SYSTEM and 'drafted' in hooks.ENDED_SYSTEM

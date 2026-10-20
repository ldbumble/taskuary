"""A number box left blank reads back its default, in ONE place (the 2026-10-19 UI walk). The Settings page says
"blank = default"; the readers each chose their own fallback for '', and `int(get_setting('poll_minutes') or 0)` turned a cleared
Poll box into background sync OFF. The store answers the default now, so no reader can pick a different one."""
from taskuary import settings_schema
from taskuary.store import BLANK_DEFAULTS, DEFAULT_SETTINGS, MemoryStore


def test_every_number_knob_set_blank_reads_back_its_default():
    s = MemoryStore()
    nums = [k for k, m in settings_schema.knobs().items() if m.get('type') == 'number' and k in DEFAULT_SETTINGS]
    assert 'poll_minutes' in nums and 'startup_sync_days' in nums
    for k in nums:
        for blank in ('', '  ', None):
            s.set_setting(k, blank, 'owner')
            assert s.get_setting(k) == DEFAULT_SETTINGS[k], (k, blank)
            assert s.get_settings()[k] == DEFAULT_SETTINGS[k], (k, blank)
    assert set(BLANK_DEFAULTS) == set(nums)


def test_a_real_value_and_zero_are_kept():
    s = MemoryStore()
    s.set_setting('poll_minutes', '0', 'owner'); assert s.get_setting('poll_minutes') == '0', '0 is "do not poll" - a choice, not a blank'
    s.set_setting('poll_minutes', '25', 'owner'); assert s.get_setting('poll_minutes') == '25'
    # a text setting stored blank is still blank: only number knobs have a default to fall back on
    s.set_setting('email_signature', '', 'owner'); assert s.get_setting('email_signature', 'x') == ''
    assert s.get_setting('no_such_key', 'fallback') == 'fallback'

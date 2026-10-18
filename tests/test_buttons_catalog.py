"""Every button the owner can press is one the assistant can name and reach, or one that says why it is the page's alone:
a button added to buttons.json with no tool was invisible to the model ("reopen it" had no button name, 2026-10-18)."""
from taskuary import buttons, operations, toolcatalog as tc


def test_every_button_is_a_decision_a_tool_or_the_pages_alone():
    loose = [v for v in buttons.VERBS if v not in tc.DECISIONS and v not in tc.CHIP_TOOL and v not in tc.PAGE_ONLY]
    assert not loose, f'buttons the assistant cannot reach or name: {loose}'
    assert not set(tc.CHIP_TOOL) & set(tc.PAGE_ONLY) and set(tc.PAGE_ONLY) <= set(buttons.VERBS)


def test_every_tool_a_button_names_runs():
    assert all(t in operations.KINDS for t in tc.CHIP_TOOL.values())
    tools = {k for _, _, ks in tc.BUCKETS for k in ks}
    assert set(tc.CHIP_TOOL.values()) <= tools

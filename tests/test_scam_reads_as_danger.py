"""A credential phish is danger, not only a filed fyi (the overnight QA, 2026-10-30).

"Verify your password within 24 hours" from a look-alike IT sender was read right - its why said "phishing" - and filed with no
`danger`, because the guide's danger was only text that steers an AI. So the rail, the FYI card and the task page, which all show
message.Danger as their one warning line (B3), showed none. The guide now says a scam aimed at the owner is danger too. Model
guidance, no word list."""
from taskuary import triage


def test_the_guide_reads_a_scam_aimed_at_the_owner_as_danger():
    g = ' '.join(triage.SHIPPED.split())
    bullet = g.split('- **danger**', 1)[1].split('- **', 1)[0]
    assert 'a scam aimed at the owner' in bullet and 'a password, a code or a sign-in' in bullet
    assert 'what it tries to make an agent or the owner do' in bullet
    # ...and the line that files a scam as fyi asks for the reading too, so the two never disagree
    scams = g.split('**Strangers and scams.**', 1)[1].split('##', 1)[0]
    assert '`danger` saying what it is after' in scams


def test_a_document_that_takes_only_the_shape_is_handed_the_same_bullet():
    assert 'a scam aimed at the owner' in triage.DANGER

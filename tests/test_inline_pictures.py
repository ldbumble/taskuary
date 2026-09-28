"""A picture pasted into an email is fetched and reaches the card (the owner, 2026-09-28: "images inline of the email are
not coming through").

Graph's hasAttachments is FALSE for a mail whose only attachments are inline, and ingest fetched attachments only when
that flag said so - so the screenshot that IS the ask in a "see below" mail was never downloaded. The body's HTML
still points at it (<img src="cid:...">); that is what now says to fetch.
"""
import os
from taskuary import channels

SEE_BELOW = {'hasAttachments': False,
             'body': {'contentType': 'html', 'content': '<p>Erin - see below.</p><img src="cid:image001.png@01DB1234.5678">'}}


def test_a_pasted_picture_is_fetched_though_graph_says_no_attachments():
    assert channels.wants_attachments(SEE_BELOW)


def test_plain_mail_costs_no_extra_call():
    assert not channels.wants_attachments({'hasAttachments': False, 'body': {'content': '<p>Thanks, Gail</p>'}})


def test_a_real_attachment_still_is():
    assert channels.wants_attachments({'hasAttachments': True, 'body': {'content': ''}})


def test_both_ingest_roads_ask_the_same_question():
    """New mail (channels) and a thread's history completed later (chains) - one rule, not two flags."""
    here = os.path.dirname(channels.__file__)
    for f in ('channels.py', 'chains.py'):
        src = open(os.path.join(here, f), encoding='utf-8').read()
        assert "if m.get('hasAttachments')" not in src, f
        assert 'wants_attachments(m)' in src, f

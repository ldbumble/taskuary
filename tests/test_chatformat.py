"""A report as a CHAT can hold it.

The morning digest arrived on WhatsApp as two bubbles of seven thousand characters, split
mid-sentence, both collapsed behind "Read more", and most of it was the `--- raw data ---`
evidence dump the desktop has always hidden (the owner, 2026-09-19, with a screenshot). The
desktop already knows how to show a report: cut at the raw-data marker, group it into sections,
list the items. These tests hold the phone to the same rules.
"""
import unittest

from taskuary import chatformat as cf

DIGEST = """\U0001f64b People want
1. Christine St John wants an explanation for the Sawyers refund.
2. Autumn Evans wants resolution on two refund threads.

\U0001f680 In flight
1. TQ-0646 is finished for the Careview thread.

\U0001f50e What happened
1. No meetings are listed for today.

--- raw data ---
NOW: Saturday 19 September 2026 21:00

THEIR ASKS YOU HAVE NOT ANSWERED (their last word wants something):
  Anthropic asked Fri 18 Sep 14:55 re "Your secure link": "Sign in to Claude.ai" - no answer
"""

MARKDOWN = """# Morning Report — GitHub Trending

## What happened

| Step | Tool | Result |
|---|---|---|
| Fetch trending | WebFetch | OK, 15 rows |

## Top 15

1. [cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill) is **first** today.
"""


class RawDataTests(unittest.TestCase):
    def test_the_evidence_dump_never_reaches_a_chat(self):
        """The desktop cuts at this exact marker in three places (assistantCards, FeedView,
        digestText). The phone sent all of it, which was most of the seven thousand characters."""
        kept = cf.strip_raw(DIGEST)
        self.assertIn('People want', kept)
        self.assertNotIn('raw data', kept)
        self.assertNotIn('THEIR ASKS YOU HAVE NOT ANSWERED', kept)

    def test_a_report_with_nothing_but_evidence_sends_no_bubble(self):
        """'Process Error Check - 0 rows' files a bare marker and nothing else. The card header
        already names the run, so an empty bubble under it is noise, not information."""
        self.assertEqual(cf.strip_raw('--- raw data ---').strip(), '')
        self.assertEqual(cf.blocks('--- raw data ---'), [])


class SectionTests(unittest.TestCase):
    def test_a_digest_arrives_as_its_sections_in_order(self):
        got = cf.sections(cf.strip_raw(DIGEST))
        self.assertEqual([t for t, _ in got],
                         ['\U0001f64b People want', '\U0001f680 In flight', '\U0001f50e What happened'])
        self.assertIn('Christine St John', got[0][1])
        self.assertIn('Autumn Evans', got[0][1])

    def test_markdown_headings_are_sections_too(self):
        """Not every report is the digest: the GitHub one is ordinary markdown. Its top-level
        title has nothing under it and is not a section - the card header already names the
        run, so a bubble holding only its title would say nothing twice."""
        self.assertEqual([t for t, _ in cf.sections(MARKDOWN)], ['What happened', 'Top 15'])

    def test_prose_with_no_headings_is_one_section(self):
        got = cf.sections('Summary of accomplishments: nothing completed.\nNothing else.')
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][0], '')


class RenderTests(unittest.TestCase):
    def test_whatsapp_keeps_the_emphasis_in_its_own_spelling(self):
        """WhatsApp formats client-side, so *one* star is bold there and ** arrives as literal
        punctuation. Telegram renders nothing without a parse mode, so it gets none."""
        self.assertEqual(cf.render('this is **first** today', 'whatsapp'), 'this is *first* today')
        self.assertEqual(cf.render('this is **first** today', 'telegram'), 'this is first today')

    def test_a_link_keeps_its_words_and_drops_its_url(self):
        for channel in ('whatsapp', 'telegram'):
            self.assertEqual(cf.render('[cloudflare/audit](https://github.com/x)', channel),
                             'cloudflare/audit')

    def test_a_table_becomes_lines_a_phone_can_read(self):
        """Fifteen repos by six columns of pipes is unreadable in a bubble."""
        out = cf.render('| Step | Tool |\n|---|---|\n| Fetch trending | WebFetch |', 'whatsapp')
        self.assertNotIn('|', out)
        self.assertNotIn('---', out)
        self.assertIn('Fetch trending · WebFetch', out)

    def test_a_rank_column_is_not_mistaken_for_a_heading(self):
        """The GitHub report's table is numbered, so its header row starts "| # | Repo |".
        Read as markdown that is a level-one heading, and the rank column disappeared into
        one bold line: "*· Repo · Stars today · ...*"."""
        out = cf.render('| # | Repo |\n|---|---|\n| 1 | cloudflare/x |', 'whatsapp')
        self.assertIn('# · Repo', out)
        self.assertNotIn('*', out)

    def test_a_wide_table_arrives_as_one_record_per_row(self):
        """Six columns as a dotted line ran to three wrapped lines of numbers nobody could tell apart (the
        GitHub Trending report, 2026-09-20). Each row is a record: bold title, short cells as label-value
        pairs, the description on its own line; the header names the labels and is not repeated."""
        md = ('| # | Repo | Stars today | Total ★ | Lang | What it is |\n|---|---|---|---|---|---|\n'
              '| 1 | [affaan-m/ECC](https://github.com/affaan-m/ECC) | 1,012 | 263,352 | JavaScript | Agent harness optimization system: skills, instincts, memory, security |\n'
              '| 14 (W) | Tencent/WeKnora | 4,867 /wk | 27,849 | Go | Open LLM knowledge platform: documents to RAG plus reasoning agent |')
        out = cf.render(md, 'whatsapp')
        self.assertIn('*1. affaan-m/ECC*\nStars today 1,012 · Total ★ 263,352 · Lang JavaScript\nAgent harness optimization system', out)
        self.assertIn('\n\n*14 (W). Tencent/WeKnora*\nStars today 4,867 /wk', out)
        self.assertNotIn('# · Repo', out); self.assertNotIn('|', out)
        self.assertIn('1. affaan-m/ECC\nStars today', cf.render(md, 'telegram'))        # the same record, no stars
        # a SHORT description still gets its own line: the column is prose, whatever this row's length
        short = md + '\n| 2 | BuilderIO/agent-native | 89 | 5,014 | TypeScript | Framework for agentic apps |'
        self.assertIn('*2. BuilderIO/agent-native*\nStars today 89 · Total ★ 5,014 · Lang TypeScript\nFramework for agentic apps', cf.render(short, 'whatsapp'))
        # ...and a narrow table keeps its dotted lines, header included
        self.assertIn('Step · Tool · Result\nFetch · WebFetch · OK',
                      cf.render('| Step | Tool | Result |\n|---|---|---|\n| Fetch | WebFetch | OK |', 'whatsapp'))

    def test_a_reports_html_fold_is_unwrapped_and_an_errors_angle_brackets_are_not(self):
        """Ten of the last 400 live reports carry a <details><summary> evidence fold; a chat draws tags as
        text. The tags go, the words stay - and "<urlopen error ...>" is an error's words, not a tag."""
        out = cf.render('<details><summary>Evidence</summary>\n<ul><li>row 1</li><li>row 2</li></ul>\n<p>failed: <urlopen error x></p></details>', 'whatsapp')
        self.assertIn('Evidence\n- row 1\n- row 2', out.replace('\n\n', '\n'))
        self.assertIn('failed: <urlopen error x>', out)
        for tag in ('<details', '<summary', '<ul', '<li', '<p>', '</p>'): self.assertNotIn(tag, out)

    def test_a_heading_is_not_left_wearing_its_hashes(self):
        self.assertNotIn('#', cf.render('## What happened', 'telegram'))


class BlockTests(unittest.TestCase):
    def test_the_digest_arrives_as_readable_blocks_not_one_wall(self):
        got = cf.blocks(DIGEST)
        self.assertGreater(len(got), 1)
        self.assertTrue(all(len(b) <= cf.HARD for b in got))
        self.assertNotIn('raw data', ' '.join(got))

    def test_a_block_never_ends_mid_sentence(self):
        """The old splitter took max() of the paragraph, line and space positions, so the space
        always won and every break landed mid-sentence: '...asked Fri 18 Sep 10:34 re "Northwind and'."""
        for b in cf.blocks(DIGEST):
            self.assertFalse(b.rstrip().endswith(' and'), b[-60:])
            self.assertTrue(b.strip())

    def test_a_section_is_never_torn_across_two_blocks(self):
        got = cf.blocks(DIGEST)
        starts = [b for b in got if 'People want' in b]
        self.assertEqual(len(starts), 1)
        self.assertIn('Christine St John', starts[0])
        self.assertIn('Autumn Evans', starts[0])

    def test_a_section_longer_than_one_message_splits_on_an_item(self):
        long_items = '\n'.join(f'{i}. item number {i} ' + 'x' * 200 for i in range(1, 40))
        got = cf.blocks('\U0001f64b People want\n' + long_items)
        self.assertTrue(all(len(b) <= cf.HARD for b in got))
        self.assertGreater(len(got), 1)

    def test_blocks_leave_the_spelling_to_the_door(self):
        """Structure here, channel spelling in remote_assistant.send - so a report is cut
        into sections once however many chats it is bound for."""
        got = cf.blocks('## Top\n\nthis is **first**')
        self.assertIn('**first**', got[0])
        self.assertIn('## Top', got[0])


if __name__ == '__main__':
    unittest.main()

class PhoneDoorTests(unittest.TestCase):
    """remote_assistant.send is the one door everything we say to the owner passes through, so
    the channel's own spelling belongs there and nowhere else."""

    def setUp(self):
        from taskuary import messengers, remote_assistant
        from taskuary.store import MemoryStore
        self.ra, self.messengers = remote_assistant, messengers
        self.s = MemoryStore()

    def sent(self, channel, text):
        from unittest import mock
        name = 'tg_send' if channel == 'telegram' else 'wa_send'
        with mock.patch.object(self.messengers, name) as out:
            self.ra.send(self.s, channel, 'chat-1', text)
        return [c.args[2] for c in out.call_args_list]

    def test_a_bubble_break_becomes_a_separate_message(self):
        got = self.sent('whatsapp', 'first part' + cf.BREAK + 'second part')
        self.assertEqual(len(got), 2)
        self.assertIn('first part', got[0])
        self.assertIn('second part', got[1])
        self.assertNotIn('second part', got[0])

    def test_the_door_spells_the_text_the_way_the_channel_draws_it(self):
        self.assertIn('*first*', self.sent('whatsapp', 'this is **first**')[0])
        self.assertNotIn('*', self.sent('telegram', 'this is **first**')[0])

    def test_only_the_opening_bubble_wears_the_name(self):
        """Four bubbles each labelled "Taskuary (2/4):" over a section heading that already says
        what it is reads as machinery, not as somebody talking."""
        got = self.sent('whatsapp', 'one' + cf.BREAK + 'two' + cf.BREAK + 'three')
        self.assertTrue(got[0].startswith('Taskuary:'))
        self.assertFalse(any(g.startswith('Taskuary') for g in got[1:]))

    def test_a_report_reaches_the_phone_as_its_sections(self):
        mid = self.s.add_message({'ExternalId': 'report:1', 'Channel': 'report', 'ConversationId': 'report-1',
                                  'Subject': 'Morning digest', 'BodyText': DIGEST, 'FromName': 'Taskuary',
                                  'FromEmail': None, 'SentAt': '2026-09-19 21:00:00', 'Status': 'open'})
        # the card's box is the first section; More sends every section after it, a bubble apiece
        block = self.ra.decision_block(self.s, {'mid': mid, 'kind': 'report'}) + self.ra.more_text(self.s, {'mid': mid, 'kind': 'report'})
        self.assertNotIn('raw data', block)
        self.assertNotIn('Anthropic asked', block)                  # the evidence dump
        self.assertNotIn('combined by triage', block)               # a report is not a thread
        self.assertIn(cf.BREAK, block)
        self.assertIn('People want', block)
        self.assertIn('In flight', block)


class ADraftToAPersonTests(unittest.TestCase):
    """A reply we send in the owner's name is not a card and carries no Taskuary chrome - but it
    is still written by a model that reaches for markdown, and the person reading it is on the
    same WhatsApp that folds a long bubble and prints ** as punctuation."""

    def setUp(self):
        from taskuary import messengers, outbound
        from taskuary.store import MemoryStore
        self.outbound, self.messengers, self.s = outbound, messengers, MemoryStore()
        self.mid = self.s.add_message({'ExternalId': 'whatsapp:1', 'Channel': 'whatsapp',
                                       'ConversationId': 'whatsapp:1234@s.whatsapp.net', 'Subject': 'hi',
                                       'BodyText': 'can you check this?', 'FromName': 'Tess',
                                       'FromEmail': None, 'SentAt': '2026-09-19 10:00:00', 'Status': 'open'})

    def reply(self, body):
        from unittest import mock
        msg = self.s.get_message(self.mid)
        with mock.patch.object(self.messengers, 'wa_send') as out:
            self.outbound.reply_to_message(self.s, msg, body)
        return [c.args[2] for c in out.call_args_list]

    def test_a_draft_does_not_reach_them_wearing_its_markdown(self):
        got = self.reply('I checked it - the **batch date** is fixed now.')
        self.assertEqual(len(got), 1)
        self.assertIn('*batch date*', got[0])
        self.assertNotIn('**', got[0])

    def test_a_long_draft_goes_in_pieces_rather_than_over_the_limit(self):
        got = self.reply('\n\n'.join(f'Paragraph {i}. ' + 'word ' * 120 for i in range(12)))
        self.assertGreater(len(got), 1)
        self.assertTrue(all(len(g) <= cf.HARD for g in got))


class NotifyTests(unittest.TestCase):
    def test_a_notify_ping_is_spelled_for_its_channel(self):
        from unittest import mock
        from taskuary import messengers, outbound
        from taskuary.store import MemoryStore
        s = MemoryStore()
        with mock.patch.object(outbound, 'notify_targets', return_value=[('whatsapp', 'c1', None)]), \
             mock.patch.object(messengers, 'wa_send') as out:
            outbound.notify(s, 'triage stopped: **no AI connector**')
        said = out.call_args.args[2]
        self.assertNotIn('**', said)                 # ** would have matched the one-star test too
        self.assertIn('*no AI connector*', said)


if __name__ == '__main__':
    unittest.main()

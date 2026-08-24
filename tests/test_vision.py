""""See below." is half the mail this app reads, and below was a screenshot - so these cover the
paths where a picture, a wider poll window, or a chart the AI chose has to actually land: vision
input to triage, the startup backfill, and the report chart.
"""
import json, tempfile, unittest
from unittest import mock
from pathlib import Path
from taskuary import artifacts, channels, llm as llm_mod
from taskuary.store import MemoryStore
from taskuary.triage import classify_intent


def _png(d, name='shot.png', n=64):
    f = d / name
    f.write_bytes(b'\x89PNG\r\n\x1a\n' + b'x' * n)
    return f


class VisionTests(unittest.TestCase):
    def test_only_real_pictures_reach_the_model_and_the_setting_switches_it_off(self):
        d = Path(tempfile.mkdtemp())
        s = MemoryStore()
        mid = s.add_message({'Channel': 'email', 'BodyText': 'see below', 'Status': 'filed'})
        png = _png(d)
        svg = d / 'chart.svg'
        svg.write_text('<svg/>', encoding='utf-8')
        s.add_attachment({'MessageId': mid, 'Name': 'shot.png', 'ContentType': 'image/png',
                          'Size': png.stat().st_size, 'Path': str(png)})
        # no provider takes SVG as image input, and a row with no Path has no bytes to send
        s.add_attachment({'MessageId': mid, 'Name': 'chart.svg', 'ContentType': 'image/svg+xml',
                          'Size': 6, 'Path': str(svg)})
        s.add_attachment({'MessageId': mid, 'Name': 'book.xlsx', 'ContentType': artifacts.XLSX_TYPE,
                          'Size': 10, 'Path': None})
        self.assertEqual([ct for ct, _b in llm_mod.readable_images(s, [mid])], ['image/png'])
        # too big to send is skipped rather than blowing the request up
        big = _png(d, 'huge.png', llm_mod.VISION_BYTES + 10)
        s.add_attachment({'MessageId': mid, 'Name': 'huge.png', 'ContentType': 'image/png',
                          'Size': big.stat().st_size, 'Path': str(big)})
        self.assertEqual(len(llm_mod.readable_images(s, [mid])), 1)
        s.set_setting('vision_enabled', '0', 'owner')
        self.assertEqual(llm_mod.readable_images(s, [mid]), [])

    def test_triage_reads_the_screenshot_before_deciding(self):
        seen = {}
        def llm(system, user, max_tokens=400, images=None):
            seen['system'], seen['images'] = system, images
            return '{"intent": "task", "why": "the screenshot is a stack trace"}'
        out = classify_intent({'from_email': 'a@b.com', 'subject': 'See below', 'body': 'See below.'},
                              llm=llm, images=[('image/png', 'AAAA')])
        self.assertEqual(out['intent'], 'task')
        self.assertEqual(seen['images'], [('image/png', 'AAAA')])
        self.assertIn('screenshot of the error IS the request', seen['system'])

    def test_graph_attachments_are_read_for_triage_before_the_message_row_exists(self):
        """They used to be saved AFTER ingest, so whatever classified "See below." never saw what
        was below it and filed a stack trace as informational."""
        s = MemoryStore()
        items = [{'id': 'a', 'name': 's.png', 'contentType': 'image/png', 'size': 40, 'contentBytes': 'AAAA'},
                 {'id': 'b', 'name': 'x.pdf', 'contentType': 'application/pdf', 'size': 40, 'contentBytes': 'BBBB'},
                 {'id': 'c', 'name': 'big.png', 'contentType': 'image/png',
                  'size': 99 * 1024 * 1024, 'contentBytes': 'CCCC'}]
        self.assertEqual(channels.images_for_triage(s, items), [('image/png', 'AAAA')])
        s.set_setting('vision_enabled', '0', 'owner')
        self.assertEqual(channels.images_for_triage(s, items), [])

    def test_a_brain_that_cannot_see_still_takes_the_call(self):
        """The CLI brain has no image input - it reads files off disk itself. Accepting and
        dropping the kwarg beats a TypeError in the middle of triage."""
        s = MemoryStore()
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        with mock.patch('taskuary.agents.run_cli', return_value=('{"intent": "fyi", "why": "x"}', None, None)):
            fn = llm_mod.make_cli_llm(s, 'coder')
            self.assertIn('fyi', fn('sys', 'user', images=[('image/png', 'AAAA')]))


class StartupSyncTests(unittest.TestCase):
    def test_the_backfill_window_reaches_past_the_watermark_without_moving_it(self):
        """"Anything since I last ran" is the wrong question after a weekend off: whatever arrived
        while the app was closed was polled by nobody."""
        from datetime import datetime, timedelta
        src = {'LastPolledAt': (datetime.now() - timedelta(minutes=5)).isoformat(sep=' ', timespec='seconds')}
        # minutes, not days - the incremental window is the watermark plus POLL_OVERLAP, which
        # reaches back past it on purpose (see test_poll_overlap.py: an API that indexes late
        # otherwise loses anything that arrived just before a poll)
        self.assertLess((datetime.now() - channels._since(src)).total_seconds(),
                        400 + channels.POLL_OVERLAP.total_seconds())
        wide = channels._since(src, 3)
        self.assertGreater((datetime.now() - wide).total_seconds(), 2.9 * 86400)
        self.assertLess((datetime.now() - wide).total_seconds(), 3.1 * 86400)
        # a source last polled a month ago is NOT pulled forward - the backfill only ever widens
        old = {'LastPolledAt': (datetime.now() - timedelta(days=30)).isoformat(sep=' ', timespec='seconds')}
        self.assertGreater((datetime.now() - channels._since(old, 3)).total_seconds(), 29 * 86400)


class ReportChartTests(unittest.TestCase):
    ROWS = [{'vendor': 'Acme', 'ref': 1001, 'amount': 120.5}, {'vendor': 'Globex', 'ref': 1002, 'amount': 80}]

    def test_the_ai_picks_the_column_to_plot_and_the_directive_never_reaches_the_reader(self):
        """A heuristic hunting for "all numeric" picks the ref column. The model that just read
        every row knows which one is the measure."""
        body = '\n'.join([json.dumps(r) for r in self.ROWS] + ['CHART: amount | vendor | Spend by vendor'])
        self.assertEqual(artifacts.chart_directive(body), ('amount', 'vendor', 'Spend by vendor'))
        self.assertNotIn('CHART:', artifacts.strip_directive(body))
        svg = artifacts.to_svg_chart(self.ROWS, None, 'Spend by vendor', 'amount', 'vendor')
        self.assertIn('Spend by vendor', svg)
        self.assertIn('amount by vendor', svg)
        # a column the model invented must not lose the chart - it falls back to the guess
        self.assertTrue(artifacts.to_svg_chart(self.ROWS, None, 't', 'made_up', 'also_fake'))
        self.assertEqual(artifacts.chart_directive('no directive here'), (None, None, ''))

    def test_charts_can_be_switched_off_without_losing_the_spreadsheet(self):
        s = MemoryStore()
        s.set_setting('report_images_enabled', '0', 'owner')
        mid = s.add_message({'Channel': 'report', 'Subject': 'Spend', 'BodyText': 'x', 'Status': 'feed'})
        made = artifacts.attach_report_output(s, mid, 'Spend', '\n'.join(json.dumps(r) for r in self.ROWS))
        kinds = [a['ContentType'] for a in s.list_attachments(mid)]
        self.assertIn(artifacts.XLSX_TYPE, kinds)
        self.assertNotIn('image/svg+xml', kinds)
        self.assertEqual(len(made), 1)



class ReportOutputApiTests(unittest.TestCase):
    """A report's rows have to come back as things you can USE - a spreadsheet to open and a
    chart to look at - and the panel has to be able to draw the chart where you read about it."""
    from fastapi.testclient import TestClient
    from taskuary import server as _srv
    c, srv = TestClient(_srv.app), _srv

    def test_the_chart_is_attached_served_as_an_image_and_drawn_inline(self):
        rows = [{'vendor': 'Acme', 'amount': 120.5}, {'vendor': 'Globex', 'amount': 80}]
        body = '\n'.join([json.dumps(r) for r in rows] + ['CHART: amount | vendor | Spend by vendor'])
        mid = self.srv.store.add_message({'Channel': 'report', 'Subject': 'Spend — 2 rows',
                                         'SourceName': 'Spend', 'BodyText': artifacts.strip_directive(body),
                                         'SentAt': '2026-08-20 09:00', 'Status': 'feed'})
        made = artifacts.attach_report_output(self.srv.store, mid, 'Spend', body)
        self.assertEqual(len(made), 2)                                  # the spreadsheet and the chart
        rows_out = self.c.get(f'/api/messages/{mid}/attachments').json()['data']
        chart = next(a for a in rows_out if a['content_type'] == 'image/svg+xml')
        sheet = next(a for a in rows_out if a['content_type'] == artifacts.XLSX_TYPE)
        self.assertTrue(chart['is_image'] and chart['inline'] and chart['url'])
        r = self.c.get(chart['url'])
        self.assertEqual(r.status_code, 200)
        self.assertIn('Spend by vendor', r.text)                        # the AI's title, not the guess
        self.assertIn('amount by vendor', r.text)
        # SVG as a document on this origin is XSS; the panel still draws it via <img>
        self.assertIn('attachment', r.headers.get('content-disposition', ''))
        # the spreadsheet is a download, and a real zip
        self.assertIn('attachment', self.c.get(sheet['url']).headers.get('content-disposition', ''))
        self.assertEqual(self.c.get(sheet['url']).content[:2], b'PK')
        # and the row that carries them says so
        feed = next(x for x in self.c.get('/api/feed').json()['data'] if x['MessageId'] == mid)
        self.assertEqual(feed['Attachments'], 2)

    def test_the_dry_run_shows_the_chart_it_would_hand_back(self):
        """Preview files no message, so there is nothing to hang an attachment on - the SVG is
        rendered in memory and returned, or a report's chart could only be seen after scheduling it."""
        rows = [{'host': 'web01', 'errors': 12}, {'host': 'web02', 'errors': 3}]
        cfg = {'type': 'rest', 'title': 'Errors by host'}
        with mock.patch.dict(artifacts.__dict__):
            with mock.patch('taskuary.reports.REGISTRY', {'rest': lambda c: ('2 rows',
                            '\n'.join(json.dumps(r) for r in rows) + '\nCHART: errors | host | Errors by host')}):
                out = self.c.post('/api/reports/preview', json=cfg).json()
        self.assertTrue(out['ok'])
        self.assertEqual(out['rows'], 2)
        self.assertIn('Errors by host', out['chart'])
        self.assertNotIn('CHART:', out['summary'])          # the directive is not prose for the reader

    def test_charts_off_means_no_chart_in_the_preview_either(self):
        self.srv.store.set_setting('report_images_enabled', '0', 'test')
        try:
            with mock.patch('taskuary.reports.REGISTRY', {'rest': lambda c: ('1 row', json.dumps({'a': 'x', 'n': 5}))}):
                out = self.c.post('/api/reports/preview', json={'type': 'rest'}).json()
            self.assertEqual(out['chart'], '')
        finally:
            self.srv.store.set_setting('report_images_enabled', '1', 'test')

if __name__ == '__main__':
    unittest.main()

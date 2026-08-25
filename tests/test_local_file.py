"""A file on the owner's own computer as a report source. Taskuary already runs on that machine,
so the spreadsheet somebody drops in a folder every morning should be a source like any other -
and until now the choices were a WinRM script or nothing. smb_file (a NETWORK share) stays
planned; this is a plain local path.
"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from taskuary import server
from taskuary.reports import run_local_file

c = TestClient(server.app)


def _dir(**files):
    d = Path(tempfile.mkdtemp(prefix='taskuary_lf_'))
    for name, body in files.items():
        (d / name.replace('__', '.')).write_text(body, encoding='utf-8')
        time.sleep(0.01)                     # distinct mtimes, so "newest" means something
    return d


class WhatItReadsTests(unittest.TestCase):
    def test_csv_and_tsv_become_rows_with_the_separator_sniffed(self):
        d = _dir(a__csv='name,qty\nwidget,4\nbolt,9\n', b__tsv='name\tqty\nnut\t7\n')
        head, body = run_local_file({'path': str(d / 'a.csv')})
        self.assertIn('2 rows', head)
        self.assertIn('a.csv', head)                       # WHICH file it read, always
        self.assertIn('widget', body)
        # a semicolon export from a European locale is still a csv
        (d / 'c.csv').write_text('name;qty\nscrew;3\n', encoding='utf-8')
        self.assertIn('screw', run_local_file({'path': str(d / 'c.csv')})[1])
        self.assertIn('nut', run_local_file({'path': str(d / 'b.tsv')})[1])

    def test_a_log_shows_the_END_because_that_is_where_the_news_is(self):
        d = _dir(app__log='\n'.join(f'line {i}' for i in range(200)) + '\nERROR boom\n')
        head, body = run_local_file({'path': str(d / 'app.log'), 'tail': 3})
        self.assertIn('last 3 of 201 lines', head)
        self.assertIn('ERROR boom', body)
        self.assertNotIn('line 1\n', body)
        self.assertIn('line 199', run_local_file({'path': str(d / 'app.log')})[1])   # 50 by default

    def test_json_comes_back_as_rows_when_it_is_a_list_and_as_itself_when_it_is_not(self):
        d = _dir(x__json=json.dumps({'items': [{'a': 1}, {'a': 2}], 'meta': {'ok': True}}),
                 y__jsonl='{"a": 1}\n{"a": 2}\n{"a": 3}\n')
        self.assertIn('2 records', run_local_file({'path': str(d / 'x.json'), 'path_expr': 'items'})[0])
        self.assertIn('3 records', run_local_file({'path': str(d / 'y.jsonl')})[0])
        head, body = run_local_file({'path': str(d / 'x.json')})           # no path: the object itself
        self.assertIn('x.json', head)
        self.assertIn('meta', body)

    def test_a_folder_answers_did_todays_export_arrive(self):
        d = _dir(one__csv='a\n1\n', two__csv='a\n2\n')
        head, body = run_local_file({'path': str(d)})
        self.assertIn('2 files', head)
        self.assertIn('two.csv', body)
        self.assertIn('modified', body)

    def test_anything_else_is_read_as_text_rather_than_refused(self):
        d = _dir(notes__rst='just some words')
        self.assertIn('just some words', run_local_file({'path': str(d / 'notes.rst')})[1])


class WhichFileTests(unittest.TestCase):
    """An export named by its date has a different name every morning, so a report naming one
    file exactly is a report that works for a day."""
    def _two(self):
        d = _dir()
        (d / 'sales-2026-08-25.csv').write_text('name,qty\nnew,2\n', encoding='utf-8')
        time.sleep(0.02)
        (d / 'sales-2026-08-01.csv').write_text('name,qty\nold,1\n', encoding='utf-8')   # copied LATER
        return d

    def test_newest_by_default_means_the_one_that_just_arrived(self):
        d = self._two()
        self.assertIn('sales-2026-08-01.csv', run_local_file({'path': str(d / 'sales-*.csv')})[0])

    def test_and_by_name_for_the_case_where_the_clock_lies(self):
        """Re-copy last month's archive and it becomes the newest file on disk, while
        sales-2026-08-01 is plainly not the latest sales."""
        d = self._two()
        head, body = run_local_file({'path': str(d / 'sales-*.csv'), 'pick': 'name'})
        self.assertIn('sales-2026-08-25.csv', head)
        self.assertIn('new', body)

    def test_a_pattern_that_matches_nothing_says_so(self):
        d = _dir(a__csv='x\n1\n')
        with self.assertRaises(RuntimeError) as e:
            run_local_file({'path': str(d / 'nope-*.csv')})
        self.assertIn('nothing matches', str(e.exception))

    def test_a_path_that_is_not_there_says_that_instead(self):
        with self.assertRaises(RuntimeError) as e:
            run_local_file({'path': os.path.join(tempfile.gettempdir(), 'no_such_taskuary_file.csv')})
        self.assertIn('does not exist', str(e.exception))


class WiredInTests(unittest.TestCase):
    def test_it_is_offered_as_a_built_in_type_not_a_planned_one(self):
        types = {t['type']: t['status'] for t in c.get('/api/report-types').json()['data']}
        self.assertEqual(types.get('local_file'), 'builtin')
        self.assertEqual(types.get('smb_file'), 'planned')      # a network share is still planned

    def test_reading_a_path_is_a_read_like_the_sqlite_beside_it(self):
        from taskuary.scopes import ACTIONS
        self.assertEqual(ACTIONS['local_file'], 'read')

    def test_the_whole_pipeline_runs_it_through_preview(self):
        d = _dir(nums__csv='label,value\na,1\nb,2\n')
        out = c.post('/api/reports/preview', json={'type': 'local_file', 'title': 'nums',
                                                   'path': str(d / 'nums.csv')}).json()
        self.assertTrue(out['ok'], out)
        self.assertIn('2 rows', out['headline'])
        self.assertEqual(out['rows'], 2)


if __name__ == '__main__':
    unittest.main()

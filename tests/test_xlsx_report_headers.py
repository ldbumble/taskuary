"""Excel report columns must not overwrite each other when their headers repeat."""
import json
from unittest import mock

import pytest
import requests
from openpyxl import Workbook

from taskuary import reports, sharepoint


@pytest.mark.parametrize('source', ['local', 'sharepoint'])
@pytest.mark.parametrize('headers, values, expected', [
    (['Name', 'Name', 'Qty'], [['left', 'right', 3]],
     [{'Name': 'left', 'Name_2': 'right', 'Qty': 3}]),
    (['Name', 'Name', 'Name_2'], [['a', 'b', 'c']],
     [{'Name': 'a', 'Name_2': 'b', 'Name_2_2': 'c'}]),
    (['', ' ', None, 'col0', 'col1', 'col2'], [[1, 2, 3, 4, 5, 6]],
     [{'col0': 1, 'col1': 2, 'col2': 3, 'col0_2': 4, 'col1_2': 5, 'col2_2': 6}]),
    (['Name'], [['a'], ['b', 'c', 'd']],
     [{'Name': 'a', 'col1': '', 'col2': ''}, {'Name': 'b', 'col1': 'c', 'col2': 'd'}]),
    (['Left', 'Right', 'Qty'], [['a', 'b', 3]],
     [{'Left': 'a', 'Right': 'b', 'Qty': 3}]),
])
def test_xlsx_report_keeps_every_column(tmp_path, source, headers, values, expected):
    workbook = Workbook()
    workbook.active.append(headers)
    for row in values: workbook.active.append(row)
    path = tmp_path / 'report.xlsx'
    workbook.save(path); workbook.close()

    if source == 'local':
        headline, body = reports.run_local_file({'path': str(path)})
    else:
        def get(url, **kwargs):
            response = requests.Response(); response.status_code = 200
            if url.endswith('/sites/northwind.example:/sites/Reports'):
                response._content = b'{"id": "test-site"}'
            else:
                assert url.endswith('/drive/root:/Shared Documents/report.xlsx:/content')
                response._content = path.read_bytes()
            return response
        with mock.patch.object(sharepoint, '_token', return_value='offline-test-token'), \
             mock.patch.object(sharepoint.requests, 'get', side_effect=get):
            headline, body = sharepoint.run_sharepoint_file({
                'site': 'northwind.example/sites/Reports', 'path': 'Shared Documents/report.xlsx'})

    assert [json.loads(row) for row in body.splitlines()] == expected
    assert f'{len(expected)} rows from report.xlsx' in headline

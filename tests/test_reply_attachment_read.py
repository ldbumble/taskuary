"""A file on a pending reply is read back for its preview (the owner, 2026-11-05: "can't click the file") - only a file named in that reply's
envelope, never a path from the request. Invented names only."""
import json, os, tempfile
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import server
from taskuary.store import MemoryStore


def _reply_with_file():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Aging workbook for Erin', 'Kind': 'general', 'Status': 'open'}, 'owner')
    d = tempfile.mkdtemp(); path = os.path.join(d, 'aging.csv')
    open(path, 'w', encoding='utf8').write('Site,Open\nNorth,12\n')
    rid = s.add_review({'TaskId': tid, 'Kind': 'reply', 'Status': 'pending', 'DraftText': 'Attached.'})
    s.set_review_deliver(rid, json.dumps({'attachments': [{'name': 'aging.csv', 'path': path, 'size': 20}]}))
    return s, rid


def test_a_file_on_the_reply_reads_back():
    s, rid = _reply_with_file()
    with mock.patch.object(server, 'store', s):
        r = TestClient(server.app).get(f'/api/reviews/{rid}/attachment', params={'name': 'aging.csv'})
    assert r.status_code == 200 and 'North,12' in r.text


def test_a_name_not_on_the_reply_is_refused():
    s, rid = _reply_with_file()
    with mock.patch.object(server, 'store', s):
        c = TestClient(server.app)
        assert c.get(f'/api/reviews/{rid}/attachment', params={'name': '../secrets.txt'}).status_code == 404
        assert c.get(f'/api/reviews/{rid}/attachment', params={'name': 'other.csv'}).status_code == 404

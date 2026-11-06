"The task's outputs folder opens on this computer at the owner's press - the folder the server knows, never a path the page sends."
import os
from fastapi.testclient import TestClient
from taskuary import outputs, server


def test_owner_opens_the_tasks_own_folder(monkeypatch, tmp_path):
    tid = server.store.create_task({'Title': 'Pull the Payworth export'}, 'owner')
    monkeypatch.setattr(outputs, 'folder', lambda t: tmp_path / f'TQ-{t:04d}')
    opened = []
    monkeypatch.setattr('webbrowser.open', lambda u: opened.append(u))
    monkeypatch.setattr(server.threading, 'Thread', lambda target, args, daemon: type('T', (), {'start': lambda self: target(*args)})())
    c = TestClient(server.app)
    assert c.post(f'/api/task-outputs/{tid}/open').status_code == 404          # no files yet: nothing opens
    (tmp_path / f'TQ-{tid:04d}').mkdir()
    r = c.post(f'/api/task-outputs/{tid}/open')
    assert r.status_code == 200 and opened == [(tmp_path / f'TQ-{tid:04d}').resolve().as_uri()]

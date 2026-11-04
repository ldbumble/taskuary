"""A file the agent named that cannot go is said by its name, in words - never the path it wrote (the overnight run, 2026-11-03: "Not attached
to the reply - C:\\Users\\...\\files\\vendors-2026.txt: only a file from the working folder ..." stood on the task)."""
import tempfile
from pathlib import Path

from taskuary import general
from taskuary.store import MemoryStore


def test_a_refused_attachment_and_show_name_the_file_without_its_path():
    s = MemoryStore(); tid = s.create_task({'Title': 'Vendor list', 'Kind': 'general', 'Status': 'open'}, 't')
    outside = str(Path(tempfile.gettempdir()).parent / 'Elsewhere' / 'files' / 'vendors-2026.txt')
    assert general._files_to_attach(s, tid, [outside], []) == []
    general._show_files(s, tid, [outside], [])
    said = [c['Body'] for c in s.list_comments(tid)]
    assert said == ["vendors-2026.txt was not attached to the reply - only a file from the agent's own folder, or one that came with this task, can go with it.",
                    "vendors-2026.txt was not shown - only a file from the agent's own folder can be shown."]
    assert not any('Elsewhere' in x or '\\' in x for x in said)

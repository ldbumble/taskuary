"""Explicit startup cutover, before intake or navigation can change legacy state."""
from datetime import datetime
from pathlib import Path
import json
import sqlite3
import uuid


def initialize(store, *, live_state=None):
    from .processing_unread import FILED_SINCE
    # what was filed onto a task before the FYI lane raised it is not news now (processing_unread.filed_news reads this, never writes it)
    if not store.get_setting(FILED_SINCE): store.set_setting(FILED_SINCE, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'system')
    if store.processing_reads_active():
        return {'status': 'already_active'}
    # SQLite's backup API includes committed WAL content. Never copy a live .db
    # file directly, overwrite a previous backup, or restore over subsequent work.
    backup_path = None
    with store.lock:
        filename = next((row[2] for row in store.cx.execute('PRAGMA database_list') if row[1] == 'main'), '')
        if filename:
            source = Path(filename)
            backup_path = source.with_name(source.name + '.before-processing-' + uuid.uuid4().hex + '.sqlite')
            with sqlite3.connect(str(backup_path)) as backup:
                backup.row_factory = sqlite3.Row
                store.cx.backup(backup)
                attachments = [dict(row) for row in backup.execute('SELECT * FROM attachment')]
            backup_path.with_suffix('.attachments.json').write_text(
                json.dumps(attachments, ensure_ascii=False, indent=2), encoding='utf-8')
    store.reconcile_processing_membership()
    result = store.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=live_state)
    return {**result, 'backup': str(backup_path) if backup_path else None}

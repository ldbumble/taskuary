"""The Morning digest row an OLDER install carries.

A fresh install no longer gets one (store.RETIRED_SEEDS, 2026-09-23: the walk opens the day with who
wants what), but every install seeded before that still has it and the report still runs - so the
tests of the digest itself start from exactly the row the old seeder wrote.
"""
import json

from taskuary.digest import PROMPT


def add_digest(store) -> dict:
    """Write the retired seed's row and sentinel, as the old seeder did, and return the source."""
    cfg = {'type': 'digest', 'title': 'Morning digest', 'days': 1, 'daily_at': '08:00',
           'on_startup': True, 'once_per_day': True, 'ai_prompt': PROMPT}
    store.cx.execute('INSERT INTO source (Channel, Address, Owner, Active, ConfigJson) VALUES (?,?,?,?,?)',
                     ('report', 'Morning digest', 'template', 1, json.dumps(cfg)))
    store.cx.execute("INSERT OR IGNORE INTO setting (Name, Value, UpdatedBy) VALUES ('digest_report_seeded', '1', 'template')")
    store.cx.commit()
    return next(x for x in store.list_sources(active_only=False)
                if x['Channel'] == 'report' and json.loads(x['ConfigJson'] or '{}').get('type') == 'digest')

"""The Automation ideas row an OLDER install carries.

A fresh install no longer gets one (store.RETIRED_SEEDS, 2026-09-25: the Advisor reads the same month of
counts once a week and raises what is worth automating itself), but every install seeded before that
still has it and the report still runs - so its tests start from exactly the row the old seeder wrote.
"""
import json

from taskuary.toil import PROMPT


def add_automate(store) -> dict:
    """Write the retired seed's row and sentinel, as the old seeder did, and return the source."""
    cfg = {'type': 'automate', 'title': 'Automation ideas', 'days': 30, 'cron': '0 8 * * 1',
           'on_startup': True, 'once_per_week': True, 'ai_prompt': PROMPT}
    store.cx.execute('INSERT INTO source (Channel, Address, Owner, Active, ConfigJson) VALUES (?,?,?,?,?)',
                     ('report', 'Automation ideas', 'template', 1, json.dumps(cfg)))
    store.cx.execute("INSERT OR IGNORE INTO setting (Name, Value, UpdatedBy) VALUES ('automate_report_seeded', '1', 'template')")
    store.cx.commit()
    return next(x for x in store.list_sources(active_only=False)
                if x['Channel'] == 'report' and json.loads(x['ConfigJson'] or '{}').get('type') == 'automate')

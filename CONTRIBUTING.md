# Contributing to Taskuary

Thanks for helping build the local-first way to automate your job. Small, focused PRs
are the fastest path to merge — a new report connector is ~15 lines and the single best
first contribution.

## Dev setup

```bash
git clone https://github.com/ldbumble/taskuary && cd taskuary
pip install -e ".[dev,mssql,desktop]"     # dev = pytest; extras optional
python -m pytest -q                        # the whole suite runs offline in ~2s
taskuary --debug                           # run the server with debug logging
```

UI work needs Node 20+ (build-time only — users never need node):

```bash
cd website && npm ci
npm run build        # builds into taskuary/web/ (COMMIT the built assets)
node render_check.mjs http://127.0.0.1:7787   # headless smoke: every tab, zero console errors
```

## Repo map

| path | what lives there |
|------|------------------|
| `taskuary/store.py` | SQLite store — schema, seeds, one dict-shaped contract (MemoryStore for tests) |
| `taskuary/ingest.py` / `triage.py` / `routing.py` / `policy.py` | the funnel: dedupe → policy → route → AI triage |
| `taskuary/agents.py` / `coder.py` | CLI agents: live-streamed runs, diffs, the coder report contract |
| `taskuary/channels.py` | Outlook / Teams / Slack / GitHub connectors + live Test probes |
| `taskuary/reports.py` | scheduled report executors (**start here** — see below) |
| `taskuary/llm.py` | AI connectors (Anthropic / OpenAI / Azure) → one `llm(system, user)` callable |
| `taskuary/server.py` | the FastAPI API |
| `website/src/` | React 18 + MUI 6 UI (Vite) |
| `tests/` | offline unit tests — no network, no credentials |

## The 15-line contribution: a report connector

Every type in the "planned" list (`postgres`, `google_sheets`, `snowflake`, `prometheus`,
`jira`, …) is one function away. In `taskuary/reports.py`:

```python
def run_postgres(cfg):
    """{"dsn", "query"} - rows from a Postgres query."""
    import psycopg
    with psycopg.connect(cfg['dsn']) as cx:
        rows = cx.execute(cfg['query']).fetchall()[:20]
    body = '\n'.join(str(r) for r in rows)
    return f'{len(rows)} rows', body[:4000]
```

Then: add it to `REGISTRY`, remove it from `PLANNED`, add its fields to `FIELDS` in
`website/src/ReportsView.jsx`, keep any heavy import inside the function (optional
dependency), and add one offline test (see `test_report_schedule_and_run`). Done — the
Reports wizard, scheduling, AI summaries, and the Timeline all work automatically.

## Ground rules

- **Tests must pass offline.** `python -m pytest -q` uses MemoryStore and mocks — never
  real credentials or network. New behavior needs a test.
- **Match the code style you see** — dense, screen-fitting, comments say *why* not *how*.
  Don't run black/autopep8; there is no format check on purpose.
- **`taskuary/web/` is generated** — never hand-edit it; rebuild from `website/` and
  commit the output.
- **UI changes**: run `render_check.mjs` and include a screenshot in the PR.
- **Update the README** when behavior users can see changes.
- CI runs the suite on Ubuntu/Windows/macOS × Python 3.10/3.12 and builds the exe —
  green CI is required to merge.

## Reporting bugs & proposing features

Use the issue templates. For bugs, `taskuary --debug` and the log at
`~/.taskuary/taskuary.log` usually contain the answer — paste the relevant lines.

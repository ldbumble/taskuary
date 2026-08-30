"""A stand-in coding agent for the README's Wall shot: prints the kind of thing a CLI agent
prints while it works, slowly, forever. Demo data - no repo is touched."""
import sys, time, itertools
import os
# no argv from the agent profile: the Nth launch plays the Nth script (a counter file beside this one)
_c = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fake_agent.count')
try: _n = int(open(_c).read() or 0)
except (OSError, ValueError): _n = 0
open(_c, 'w').write(str(_n + 1))
role = sys.argv[1] if len(sys.argv) > 1 else ['census', 'csv', 'darkmode'][_n % 3]
SCRIPTS = {
 'census': [
  ('●', 'Reading taskuary/reports.py'), ('  ', 'Read 412 lines'),
  ('●', 'Searching for the facility filter'), ('  ', 'grep "facility" taskuary/reports.py tests/'),
  ('●', 'The query joins facility on the OLD id column; Summit was added after the rename.'),
  ('●', 'Update(taskuary/reports.py)'), ('  ', '  -   JOIN facility f ON f.legacy_id = c.facility_id'),
  ('  ', '  +   JOIN facility f ON f.id = c.facility_id'),
  ('●', 'Write(tests/test_reports.py)'), ('  ', '  + def test_census_includes_every_active_facility():'),
  ('●', 'Bash(pytest -q tests/test_reports.py)'), ('  ', '  14 passed in 1.2s'),
  ('●', 'Committing: "Census: join facilities on id, not legacy_id - Summit was missing"'),
 ],
 'csv': [
  ('●', 'Reading website/src/ReportsView.jsx'), ('  ', 'Read 933 lines'),
  ('●', 'The rows already come back as .xlsx (artifacts.py); CSV is one more writer, not a new pipeline.'),
  ('●', 'Update(taskuary/artifacts.py)'), ('  ', '  + def write_csv(rows, path): ...'),
  ('●', 'Update(website/src/ReportsView.jsx)'), ('  ', '  + <Button startIcon={<DownloadIcon />}>CSV</Button>'),
  ('●', 'Bash(npm test)'), ('  ', '  # pass 45'),
  ('●', 'Bash(pytest -q tests/test_artifacts.py)'), ('  ', '  9 passed in 0.8s'),
 ],
 'darkmode': [
  ('●', 'Reading website/src/theme.jsx'), ('●', 'Searching for the chart palette'),
  ('  ', 'grep "CHART" website/src/*.jsx'),
  ('●', 'The chart reads its ink from a light-only token; in dark mode that is #262521 on #1e1e2e - invisible, not blank.'),
  ('●', 'Update(website/src/theme.jsx)'), ('  ', '  + chart: { ink: "var(--tq-ink)", grid: "var(--tq-border)" }'),
  ('●', 'Bash(npm run build)'), ('  ', '  ✓ built in 9.8s'),
  ('?', 'Should the legend follow the same token, or stay grey in both modes? (waiting on you)'),
 ],
}
lines = SCRIPTS.get(role, SCRIPTS['census'])
print(f'\x1b[1m{role} · claude\x1b[0m  demo session - nothing here touches a real repository\n')
for mark, text in lines:
    print(f'\x1b[32m{mark}\x1b[0m {text}' if mark == '●' else f'\x1b[33m{mark}\x1b[0m {text}' if mark == '?' else f'{mark} {text}', flush=True)
    time.sleep(0.6 if mark == '  ' else 1.4)
# then hold the pane: a live session, quiet
for _ in itertools.count():
    time.sleep(60)

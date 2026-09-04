---
name: deploy
description: >
  Cut and publish a Taskuary release: bump the version in all four places, run the three
  gates, rebuild the committed UI, push, wait for CI on that exact commit, then tag so the
  publish workflow uploads to PyPI. Use when asked to deploy, release, ship, publish, "push
  to PyPI", cut a version, or bump the tag. Encodes the ordering that keeps a permanent PyPI
  number from going out broken.
---

# Deploying Taskuary

A PyPI version **can never be reused**, even after deletion (RELEASING.md). Everything below is
ordered so that nothing irreversible happens until the reversible things have all passed.

## The one rule

**Tag only after CI is green on the exact commit you are about to tag.** The tag fires
`.github/workflows/publish.yml`, and that upload is permanent. Pushing `master` is cheap and
reversible; pushing a tag is not.

## 1. Know whose work you are shipping

A Taskuary coding agent commits to **this same checkout**, so `git status` is usually not just
yours. Before anything else:

```bash
git status --short
git log --oneline origin/master..HEAD      # anything of mine not yet pushed
```

- If the owner said "push everything", the coder's in-flight work is included. Say so explicitly
  and list it — its own tests passing does not prove a half-built feature is finished.
- If they did not, commit **only your own paths** and leave theirs alone. Prove a shared file
  holds only your hunks: `git diff --stat HEAD -- <file>` (do the counts match what you wrote?)
  then `git diff HEAD -- <file> | grep '^+'` read against your own phrases.
- Commit through a **temp index** so a concurrent agent's staged work is never swept in:

```bash
export GIT_INDEX_FILE="$(pwd)/.git/claude-tmp-index"
rm -f "$GIT_INDEX_FILE"; git read-tree HEAD
git update-index --add -- <your paths>      # or `git add -A` for a deliberate ship-everything
TREE=$(git write-tree); PARENT=$(git rev-parse HEAD)
COMMIT=$(echo "$MSG" | git commit-tree "$TREE" -p "$PARENT")
git update-ref -m "release X" refs/heads/master "$COMMIT" "$PARENT"
rm -f "$GIT_INDEX_FILE"; unset GIT_INDEX_FILE
git reset -q                                # ALWAYS: refreshes the shared index to the new HEAD
```

Skipping that last `git reset -q` leaves the shared index showing your own files as modified and
your new test file as deleted. It is confusing, not harmful — but fix it, do not commit over it.

## 2. Bump the version in all four places

`pyproject.toml` is the one source of truth (`taskuary/__init__._version()` reads it), but three
documents *announce* the number and drift if you forget them. `docs/roadmap.md` sat three releases
behind this way.

| File | What to change |
|---|---|
| `pyproject.toml` | `version = "X.Y.Z.W"` |
| `README.md` | `currently **vX.Y.Z.W**` |
| `README.md` | the badge's `release=X.Y.Z.W` cache-buster |
| `docs/roadmap.md` | `currently vX.Y.Z.W` |

`tests/test_promptmap_and_catalog.py::test_no_shipped_doc_advertises_an_older_version` fails if
README or roadmap disagree with `pyproject`. The badge buster is not covered by a test: shields
caches per-URL, so without bumping it the README shows the previous number for up to an hour.

Leave the `?v=0.3.3.2` suffixes on **screenshot** URLs alone unless the picture actually changed —
and never re-shoot `docs/hero.gif` for a UI change (it is the agents-at-work animation on purpose).

## 3. Rebuild the committed UI

The bundle is committed, and a release must not ship a stale one:

```bash
cd website && npm run build && cd ..
```

This rewrites `taskuary/web/assets/*` with new content hashes, so the release commit contains the
old files as deletions and the new ones as additions. That is expected.

## 4. Run all three gates

```bash
python -m pytest -q          # FROM THE REPO ROOT
cd website && npm test && cd ..
node --test taskuary/whatsapp/
```

- **From the repo root.** `pytest` in `website/` prints `no tests ran` and exits 5 — that is a
  failure, not a pass.
- **`npm test` is not optional.** It asserts on JSX *source text* that pytest never loads, so it
  is the only thing that catches a changed `AssistantView.jsx` line breaking
  `website/test/funnelPile.test.mjs`.
- The whatsapp tests are **not run by CI** (the workflow only runs `npm test` in `website/`), so
  run them by hand or they are unguarded.

Browser-only behaviour has its own checks, which no suite can replace — run them against a demo
server when the change touches the rail, the pipe or the stage:

```bash
TASKUARY_HOME=<a scratch dir> python -m taskuary.cli --demo --port 7911 --no-browser &
node website/task_mode_check.mjs   http://127.0.0.1:7911/     # Chat/Task on the unread rail
node website/pipe_geometry_check.mjs http://127.0.0.1:7911/   # pile rows on the Timeline's edges
```

Never point a demo or a test at the real `~/.taskuary`: `tests/conftest.py` forces a temp home,
but only for files **inside `tests/`**.

## 5. Push, then wait, then tag

```bash
git push origin master
# wait for CI on THIS sha - all 9 jobs
gh run watch "$(gh run list --branch master --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status
gh run view <id> --json jobs -q '.jobs[] | "\(.conclusion)\t\(.name)"'
```

Confirm the run's `headSha` is the commit you mean — an automated `Downloads:` commit (a daily
cron, `.github/workflows/downloads.yml`) can land between your push and your check. If it does and
your push is rejected, do **not** rebase the dirty shared tree: rebuild the commit off-index with
`git read-tree origin/master`, re-add your paths, and `commit-tree -p origin/master`.

Only once CI is green:

```bash
git tag -a vX.Y.Z.W -m "taskuary X.Y.Z.W - <the release line>" <sha>
git push origin vX.Y.Z.W
```

The tag must match `pyproject.toml` exactly, or you publish a number nobody can see.

## 6. Verify what actually shipped

```bash
gh run list --workflow=publish.yml --limit 1
curl -s https://pypi.org/pypi/taskuary/X.Y.Z.W/json | python -c "import sys,json; d=json.load(sys.stdin); print(d['info']['version']); [print(' ', u['filename']) for u in d['urls']]"
curl -s https://api.github.com/repos/ldbumble/taskuary/releases/latest | python -c "import sys,json; d=json.load(sys.stdin); print(d['tag_name'], [a['name'] for a in d['assets']])"
```

- Query the **version endpoint**, not `/pypi/taskuary/json` — the index lags a minute or two
  behind the upload and will still say the previous version.
- The GitHub release must carry `Taskuary.exe` as well as both dists, or Settings → Updates has
  nothing to offer exe installs.
- A stale shields badge right after a release is cache, not a broken publish, as long as PyPI's
  own JSON says the new number.

The publish workflow already refuses to upload a wheel that does not contain `index.html`, the JS
and CSS bundles, the operator templates and the WhatsApp bridge, and it installs the wheel into a
clean venv and starts it. Do not re-verify that by hand; read its log if it fails.

## 7. Tell the owner the one thing a release does not do

Publishing does not touch their running app. It is an **editable install** off this checkout, so
Python changes need a **restart** — a browser refresh only picks up the rebuilt UI. A fix that is
live on PyPI and in `master` will keep misbehaving in their console until they restart, because the
process loaded the old module at launch.

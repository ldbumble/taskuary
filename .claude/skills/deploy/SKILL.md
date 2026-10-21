---
name: deploy
description: >
  Cut and publish a Taskuary release: freeze scope, bump the version in all seven places, run the
  fast local gates, rebuild the committed UI, push, wait for CI on that exact commit, then tag so the
  publish workflow uploads to PyPI. Use when asked to deploy, release, ship, publish, "push
  to PyPI", cut a version, or bump the tag. Encodes the ordering that keeps a permanent PyPI
  number from going out broken.
---

# Deploying Taskuary

A PyPI version **can never be reused**, even after deletion (RELEASING.md). Everything below is
ordered so that nothing irreversible happens until the reversible things have all passed.

## The one rule

**Nothing reaches PyPI unless CI is green on the exact commit the tag points at.** Since 2026-10-21 the
publish workflow enforces that itself: its first job (`ci-green`) waits for `ci.yml` on the tag's commit
and stops the upload on anything but success. So the tag goes on **right after the push** - no sitting
through CI first (that wait made every release ~40 minutes). A tag on a commit that turns red publishes
nothing: delete the tag (`git push --delete origin vX.Y.Z.W; git tag -d vX.Y.Z.W`), fix forward, re-tag.
The upload itself is still permanent, which is exactly why the gate lives in the workflow.

## Keep it to one round (about 20 minutes)

Release 0.3.9.2 took over an hour of rounds (2026-10-16): every change added mid-release restarted a
10-minute local suite and a 15-minute CI run, and a browser test nobody ran locally turned CI red.

- **Freeze scope.** Once the release starts, nothing new goes in. A request that arrives mid-release is
  done AFTER the tag, in the next release - say so, do not fold it in.
- **CI is the gate, not the local full suite.** CI runs pytest on six machines and nothing is tagged
  until it is green. Locally run the FAST gates (§4) - not a 10-minute `pytest` that CI repeats.
- **Run the browser tests locally when the UI changed.** `npm run test:browser` is the CI job nobody
  runs by hand, and it finds buttons by their label or tooltip: a renamed tooltip broke it on 0.3.9.2.
  Before pushing, `grep -rn "<old label or title>" website/browser/` for any UI text you changed.
- **Tell the other sessions.** Another Claude session may push to the same master. `ListAgents`, then
  `SendMessage` each one: "release starting - push now or hold until I say the tag is out". A push
  between your CI run and your tag lands untagged; one before it forces a rebase.

## 1. Know whose work you are shipping

A Taskuary coding agent commits to **this same checkout**, so `git status` is usually not just
yours. Before anything else:

```bash
git status --short
git log --oneline origin/master..HEAD      # anything of mine not yet pushed
```

- If the owner said "push everything", the coding agent's in-flight work is included. Say so explicitly
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

## 2. Bump the version in all seven places

`pyproject.toml` is the one source of truth (`taskuary/__init__._version()` reads it), but the
other places *announce* the number and drift if you forget them. `docs/roadmap.md` sat three
releases behind this way, and the public demo sat on v0.3.3.2 through four.

| File | What to change |
|---|---|
| `pyproject.toml` | `version = "X.Y.Z.W"` |
| `README.md` | `currently **vX.Y.Z.W**` |
| `README.md` | the badge's `release=X.Y.Z.W` cache-buster (and `asof=` — see below) |
| `README.zh-CN.md` | `目前为 **vX.Y.Z.W**`, and its own `release=`/`asof=` buster |
| `docs/roadmap.md` | `currently vX.Y.Z.W` |
| `website/src/demoFixtures.json` | `/api/version.version`, `/api/build.version`, `/api/build.disk_version` |
| `docs/site/manifest.json` | `version` and `updated` (today) - the docs footer; then `npm run build:docs` |

The fifth is the one that hides. taskuary.com/demo has **no server**, so its header reads
`/api/version` out of a recording — `website/demo_fixtures.mjs` freezes a live `--demo` instance
into `demoFixtures.json`, and the recording is only re-dumped when the fixtures themselves change.
Patch exactly those three fields and leave the rest byte-identical: it is a real instance's output,
not a document. Three occurrences of the old number, no more.

Three tests guard this. `tests/test_docs_manifest.py` pins the manifest (0.3.8.0 shipped with it stale, 2026-10-12). The other two are in `tests/test_promptmap_and_catalog.py`:
`test_no_shipped_doc_advertises_an_older_version` (both READMEs and the roadmap against `pyproject`) and
`test_the_demo_does_not_advertise_an_older_version` (the recording). The badge buster is covered by
neither: shields caches per-URL, so without bumping it the README shows the previous number for up
to an hour.

Leave the `?v=0.3.3.2` suffixes on **screenshot** URLs alone unless the picture actually changed —
and never re-shoot `docs/hero.webp` for a UI change (it is the agents-at-work animation on purpose).

## 3. Rebuild the committed UI

The bundle is committed, and a release must not ship a stale one:

```bash
cd website && npm run build && cd ..
```

This rewrites `taskuary/web/assets/*` with new content hashes, so the release commit contains the
old files as deletions and the new ones as additions. That is expected.

`demoApi.js` imports `demoFixtures.json`, so step 2 edited a **compiled-in** file. Rebuild the
public demo too, or taskuary.com keeps serving the old number even though the JSON is right:

```bash
cd website && npm run build:demo && cd ..     # writes site/demo, also committed
```

## 4. Run the fast gates

```bash
python -m pytest -q tests/<the files your change touches>      # FROM THE REPO ROOT - targeted, seconds
cd website && npm test && cd ..                                  # ~2 min, all of it
cd website && npm run test:browser && cd ..                      # when the UI changed (~5 min); CI runs it
cd website && npm run test:walk && cd ..                         # the dead-end walk, ~10+ min; its own CI job
node --test taskuary/whatsapp/*.test.mjs                         # CI does NOT run these
```

**Locally: only the tests for what changed - CI runs the whole suite** (owner, 2026-10-21: the release took
~40 minutes, ~17 of them a local full pytest that CI repeats). Run the targeted pytest files, `npm test`
(it is the only thing that reads JSX source text, and it is ~2 min), and the browser test FILES the change
touches. Skip the full `python -m pytest -q` and the full `test:browser` - CI runs both (the browser suite
in three parts, `browser/shard.mjs`). A web-only change can still fail pytest (`tests/test_every_card_is_reachable.py`
slices ConnectorsView.jsx), so include the pytest files that read the JSX you changed. Rules that cost a round when broken:

- **Never rebuild the bundle while a pytest run is going.** `tests/test_floor_wave_b.py` reads the
  built files and fails when they are replaced mid-run - a false red that cost a rerun.
- **`-p no:cacheprovider` has no `--lf`.** Grep the run for `^FAILED` so a failure is named, or a
  rerun is the only way to learn which test it was.
- **Node 20 has no `--test-timeout`** - wrap a hang-prone run in `timeout 600` instead. A timer test
  (`website/test/visible.test.mjs`) once hung a whole `node --test` run for 18 minutes.

- **From the repo root.** `pytest` in `website/` prints `no tests ran` and exits 5 — that is a
  failure, not a pass.
- **`npm test` is not optional.** It asserts on JSX *source text* that pytest never loads, so it
  is the only thing that catches a changed `AssistantView.jsx` line breaking
  `website/test/funnelPile.test.mjs`.
- **The Node on PATH is 20 and cannot run these.** `npm test`'s `test/**/*.test.mjs` glob and
  eslint 10 both need 22, and on 20 the glob failure reads like a missing suite rather than a
  wrong runtime. There is no `node_modules/.bin/eslint` either. Borrow a runtime per command:

```bash
cd website
npm exec --yes --package=node@22 -- npm run build      # and build:demo
npm exec --yes --package=node@22 -- node --test "test/**/*.test.mjs"
npm exec --yes --package=node@22 --package=eslint@10.10.0 -- eslint -c eslint.undef.mjs -f json src
npx --no-install esbuild --loader:.jsx=jsx --jsx=automatic --outfile=/dev/null src/FeedView.jsx
```

  The eslint run reports ~11 `react-hooks/exhaustive-deps` lines reading "Definition for rule ...
  was not found" — the plugin is not installed, that is pre-existing noise. What matters is
  **0 `no-undef`**. The esbuild line is the fastest syntax check on a single JSX file.
- Pass the whatsapp tests as a GLOB. `node --test taskuary/whatsapp/` resolves the directory as a
  *module* on Node 22 and dies with MODULE_NOT_FOUND, which reads exactly like a failing suite.
- The whatsapp tests are **not run by CI** (the workflow only runs `npm test` in `website/`), so
  run them by hand or they are unguarded.

Browser-only behaviour has its own checks, which no suite can replace — run them against a demo
server when the change touches the rail, the pipe or the stage:

```bash
TASKUARY_HOME=<a scratch dir> python -m taskuary.cli --demo --port 7911 --no-browser &
node website/pipe_geometry_check.mjs http://127.0.0.1:7911/   # pile rows on the Timeline's edges
```

Never point a demo or a test at the real `~/.taskuary`: `tests/conftest.py` forces a temp home,
but only for files **inside `tests/`**.

## 5. Push and tag together; publish waits for CI

```bash
git push origin master
git tag -a vX.Y.Z.W -m "taskuary X.Y.Z.W - <the release line>" <sha> && git push origin vX.Y.Z.W
# then watch ci.yml on THIS sha (filter by workflow: CodeQL/Scorecard runs share the sha and are not the gate)
gh run list --workflow ci.yml --commit <sha> --json databaseId,status,conclusion
```

If ci.yml goes red: the publish run stops at `ci-green`, nothing is uploaded. Delete the tag, fix, push,
re-tag the new sha.

Pushed and rejected because another session pushed first: `git fetch && git rebase origin/master`.
The committed bundle conflicts every time - do not merge it: take theirs, rebuild, fold it in:
`git rm -rq --cached taskuary/web; rm -rf taskuary/web; git checkout HEAD -- taskuary/web; git add -A taskuary/web;
GIT_EDITOR=true git rebase --continue`, then `npm run build` (and `build:demo`) and `git commit --amend --no-edit`.
A merged PR that touched `website/src` without rebuilding needs the same rebuild before you push.

Confirm the run's `headSha` is the commit you mean — an automated `Downloads:` commit (a daily
cron, `.github/workflows/downloads.yml`) can land between your push and your check. If it does and
your push is rejected, do **not** rebase the dirty shared tree: rebuild the commit off-index with
`git read-tree origin/master`, re-add your paths, and `commit-tree -p origin/master`.

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
  own JSON says the new number. **But do not leave it there.** Bumping `release=` at the start of a
  release is not enough on its own: GitHub proxies README images through camo, camo fetches the new
  URL immediately, and shields answers that first fetch from ITS own PyPI cache - which is still on
  the previous version for a few minutes after the upload. Camo then holds that stale render for
  hours. That is how the pill read v0.3.3.13 while PyPI, pyproject and the README all said 0.3.4.0
  (2026-09-10).
  So the LAST step of a release, after the publish workflow is green, is:
  ```
  curl -s "https://img.shields.io/pypi/v/taskuary.svg" | grep -o 'v0\.[0-9.]*' | head -1
  ```
  When that finally prints the new version, bump the badge's `asof=` to today's date and push. The
  changed URL is a new object to camo, so it re-fetches - now from a warm shields - and the pill is
  right. Bumping `release=` alone cannot do it: that value is already the new version.

The publish workflow already refuses to upload a wheel that does not contain `index.html`, the JS
and CSS bundles, the operator templates and the WhatsApp bridge, and it installs the wheel into a
clean venv and starts it. Do not re-verify that by hand; read its log if it fails.

## 7. Tell the owner the one thing a release does not do

Publishing does not touch their running app. It is an **editable install** off this checkout, so
Python changes need a **restart** — a browser refresh only picks up the rebuilt UI. A fix that is
live on PyPI and in `master` will keep misbehaving in their console until they restart, because the
process loaded the old module at launch.

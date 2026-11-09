#!/usr/bin/env bash
# ONE COMMAND FROM MASTER TO PYPI (the owner, 2026-10-27: "it's been literally all day to pass one fix .. we need a better system").
# Usage, from a clean checkout of master:  tools/release.sh 0.3.9.54
#   bump the seven places -> build the UI, demo and docs -> fast local gates -> commit, push
#   -> wait for ci.yml on THAT commit -> tag when green -> wait for publish.yml -> check PyPI and the GitHub release
#   -> fast-forward the main checkout.
# RED CI IS NOT A RESTART (the owner, 2026-11-09: "20 minute release max .. rerun just that test, everything else that passed is
# good"; .28 took four full CI rounds of ~15 min for a handful of tests). On a red run it prints the failed tests and the command
# below, and stops. Decide whether the test or the code is wrong, fix that, commit, then
#   tools/release.sh X.Y.Z.W --after <run-id> --fixed [--dry-run]
# pushes the fix, runs ONLY the failed tests (plus the test module of every file the fix touched) in ci-targeted.yml on the fix
# commit, and tags it when they pass - without waiting for the full ci.yml, which still runs on master. publish.yml takes that
# targeted run as the commit's gate. Nothing to fix (a flake)? `--fixed` with no new commit reruns them on the same commit.
# `--after <run-id>` alone prints what would be rerun. It never cancels a run and never tags red.
# Env: MAIN=<the owner's checkout to fast-forward> (default ../taskhub), SKIP_GATES=1 to skip the local gates (CI still gates).
set -euo pipefail
say() { printf '\n== %s\n' "$*"; }
die() { printf '\n!! %s\n' "$*" >&2; exit 1; }
V="${1:?usage: tools/release.sh X.Y.Z.W [--after <run-id> [--fixed] [--dry-run]]}"; shift
AFTER=""; FIXED=0; DRY=0
while [ $# -gt 0 ]; do case "$1" in
  --after) AFTER="${2:?--after needs a run id}"; shift 2;; --fixed) FIXED=1; shift;; --dry-run) DRY=1; shift;; *) die "unknown option $1";;
esac; done
ROOT="$(git rev-parse --show-toplevel)"; cd "$ROOT"
MAIN="${MAIN:-$ROOT/../taskhub}"
N=(npm exec --yes --package=node@22 --)

# A RED RUN, NAMED AND STOPPED: the failed tests, and the one command that carries on from here
stop_red() {
  "$ROOT/tools/ci-failures.sh" "$1" || true
  say "nothing was tagged. Is the TEST wrong or the CODE? Fix that, commit, then rerun just the failed tests:"
  echo "  tools/release.sh $V --after $1 --fixed"
  echo "  (nothing to fix - a flake? the same command with no new commit reruns them on this commit)"
  exit 1
}

# TAG, PUBLISH, VERIFY - the same for both roads
publish_tail() {
  local SHA="$1" P PR
  say "tag v$V and publish"
  git tag -a "v$V" -m "taskuary $V" "$SHA"; git push -q origin "v$V"
  for i in $(seq 1 60); do P=$(gh run list --workflow publish.yml --limit 1 --json status,conclusion,headBranch -q '.[0] | "\(.status) \(.conclusion) \(.headBranch)"'); case "$P" in completed*"v$V"*) break;; esac; sleep 30; done
  echo "publish: $P"
  if ! echo "$P" | grep -q success; then
    PR=$(gh run list --workflow publish.yml --limit 1 --json databaseId -q '.[0].databaseId')
    say "publish failed - rerunning its failed jobs once (the exe's signing download flakes)"; gh run rerun "$PR" --failed; sleep 60
    for i in $(seq 1 60); do P=$(gh run view "$PR" --json status,conclusion -q '"\(.status) \(.conclusion)"'); case "$P" in completed*) break;; esac; sleep 30; done
    echo "$P" | grep -q success || die "publish is red twice - read: gh run view $PR"
  fi

  say "verify"
  curl -s "https://pypi.org/pypi/taskuary/$V/json" | python -c "import sys,json; d=json.load(sys.stdin); print('PyPI', d['info']['version'], [u['filename'] for u in d['urls']])"
  curl -s https://api.github.com/repos/ldbumble/taskuary/releases/latest | python -c "import sys,json; d=json.load(sys.stdin); print('GitHub', d['tag_name'], [a['name'] for a in d['assets']])"
  [ -d "$MAIN/.git" ] || [ -f "$MAIN/.git" ] && (cd "$MAIN" && [ -z "$(git status --porcelain)" ] && git fetch -q origin && git merge --ff-only -q origin/master && echo "main checkout -> $(git rev-parse --short HEAD)") || true
  say "v$V is out. The owner's app runs from the main checkout: restart Taskuary to load it."
  # THE PILL, ONCE SHIELDS SEES IT (2026-10-29: the pill read .70 after .72 shipped): the bump's asof= went out before PyPI had the
  # version, camo fetched it from a cold shields and held the old number - so wait for shields, then move asof= once more and push.
  # After "is out": the release is done, this only tidies the README (up to 10 min of waiting on shields)
  say "refresh the README's PyPI pill"
  for i in $(seq 1 20); do curl -s "https://img.shields.io/pypi/v/taskuary.svg" | grep -q "v$V" && break; sleep 30; done
  python - "$V" <<'PY'
import re, sys
for p in ('README.md', 'README.zh-CN.md'):
    t = open(p, encoding='utf8', newline='').read(); open(p, 'w', encoding='utf8', newline='').write(re.sub(r'asof=[0-9a-z.-]+', f'asof={sys.argv[1]}-live', t))
PY
  # only the two READMEs: `commit -a` swept an agent's uncommitted edits in the owner's checkout into this commit (2026-11-09)
  git commit -q -m "Refresh the README's PyPI pill for $V" -- README.md README.zh-CN.md && git push -q origin HEAD:master || say "pill push skipped (master moved) - bump asof= by hand"

  # THE NUMBER THAT MATTERS (the owner, 2026-10-28: measure the agreement rate after each release): how often the lit button was the
  # one pressed, over the release this one replaces and the last week - read-only on the owner's home, never fatal
  local OH="${OWNER_HOME:-$HOME/.taskuary}" PREV
  if [ -f "$OH/taskuary.db" ]; then
    say "Advisor agreement ($OH, read-only)"
    PREV=$(git tag --sort=-creatordate | grep -v "^v$V$" | head -1 || true)
    [ -n "$PREV" ] && python tools/advisor_agreement.py --home "$OH" --line --since "$(git log -1 --format=%cd --date=format:'%Y-%m-%d %H:%M:%S' "$PREV")" || true
    python tools/advisor_agreement.py --home "$OH" --line --days 7 || true
  fi
}

# THE TARGETED ROAD: rerun only what failed in run $AFTER (plus what the fix touched) on the fix commit, then tag it
targeted() {
  say "what failed in run $AFTER"
  local BASE S PLAN
  S=$(gh run view "$AFTER" --json status,conclusion,headSha -q '"\(.status) \(.conclusion) \(.headSha)"')
  case "$S" in completed*) ;; *) die "run $AFTER is $S - wait for it to finish (tools/ci-failures.sh --wait $AFTER)";; esac
  case "$S" in *" success "*) die "run $AFTER is green - nothing to rerun";; esac
  BASE=${S##* }
  PLAN=$("$ROOT/tools/ci-failures.sh" --ids "$AFTER" | sort -u || true)
  [ -n "$PLAN" ] || die "run $AFTER failed but names no job this road can rerun - read: tools/ci-failures.sh $AFTER"
  echo "$PLAN" | sed 's/^/  /'
  grep -q '^stuck ' <<<"$PLAN" && die "a job failed outside the tests ($(grep '^stuck ' <<<"$PLAN" | cut -c7- | paste -sd, -)): this road cannot vouch for it - fix it and run tools/release.sh $V (the full road)"
  if [ "$FIXED" != 1 ] && [ "$DRY" != 1 ]; then
    say "decide: is the TEST wrong or the CODE? Fix that, commit, then:"; echo "  tools/release.sh $V --after $AFTER --fixed"; exit 1
  fi

  say "preflight"
  git fetch -q origin
  # a dry run names what would stop a real one and goes on to the plan
  chk() { [ "$DRY" = 1 ] && { echo "  (dry run - a real run stops here: $*)"; return 0; }; die "$*"; }
  [ -z "$(git status --porcelain)" ] || chk "the tree is not clean - commit the fix first"
  git ls-remote --tags origin "v$V" | grep -q . && chk "v$V is already tagged - PyPI numbers are never reused"
  git merge-base --is-ancestor "$BASE" HEAD || die "HEAD does not contain $BASE, the commit run $AFTER tested"
  git merge-base --is-ancestor origin/master HEAD || chk "HEAD is behind origin/master - rebase the fix onto it first"
  local HV; HV=$(python -c "import re;print(re.search(r'^version = \"([^\"]+)\"',open('pyproject.toml').read(),re.M)[1])")
  [ "$HV" = "$V" ] || chk "pyproject.toml says $HV, not $V - this road tags a commit that already carries the release's number"

  # WHAT THE FIX TOUCHED, each source file pulls in its own test module - a fix that breaks its neighbour is caught here, not by
  # waiting for the whole suite. A file with no test module is named: only the full ci.yml on master covers it.
  say "the fix: $BASE..HEAD"
  git diff --stat "$BASE" HEAD | tail -25
  local -a PY=() NODE=() LOOSE=(); local WEB=0 SMOKE=false f s m
  while read -r f; do [ -n "$f" ] && PY+=("$f"); done < <(sed -n 's/^py //p' <<<"$PLAN")
  grep -qx 'node all' <<<"$PLAN" && NODE=(all)
  grep -qx 'smoke' <<<"$PLAN" && SMOKE=true
  while read -r f; do
    [ -n "$f" ] && [ -e "$f" ] || continue
    s=$(basename "$f"); s=${s%.*}
    case "$f" in
      tests/*test_*.py) PY+=("$f");;
      tests/*) ;;
      taskuary/web/*|site/*|docs/site/*) WEB=1;;
      taskuary/*.py) m=$(find tests -name "test_$s.py" | head -1); [ -n "$m" ] && PY+=("$m") || LOOSE+=("$f");;
      website/test/*.test.mjs) NODE+=("${f#website/}");;
      website/src/*) WEB=1; [ -e "website/test/$s.test.mjs" ] && NODE+=("test/$s.test.mjs") || LOOSE+=("$f");;
      website/*) WEB=1;;
      *) LOOSE+=("$f");;
    esac
  done < <(git diff --name-only "$BASE" HEAD)
  [ ${#LOOSE[@]} = 0 ] || { say "no test module for these - only the full ci.yml on master covers them:"; printf '  %s\n' "${LOOSE[@]}"; }
  # a whole file named once covers its ids; `node all` covers any file
  local -a FILES=(); local T TESTS NT
  for f in "${PY[@]}"; do [[ "$f" == *::* ]] || FILES+=("$f"); done
  TESTS=$(for T in "${PY[@]}"; do [[ "$T" == *::* ]] && printf '%s\n' "${FILES[@]}" | grep -qxF "${T%%::*}" && continue; echo "$T"; done | sort -u | paste -sd' ' -)
  [ "${NODE[0]:-}" = all ] && NT=all || NT=$(printf '%s\n' "${NODE[@]}" | sed '/^$/d' | sort -u | paste -sd' ' -)
  [ -n "$TESTS$NT" ] || [ "$SMOKE" = true ] || [ "$WEB" = 1 ] || die "nothing to run - the plan above is empty"
  local WEBB=false; [ "$WEB" = 1 ] && WEBB=true

  local SHA BR="release-check/v$V"; SHA=$(git rev-parse HEAD)
  say "dispatch ci-targeted.yml on $SHA (windows + macos, py 3.12)"
  printf '  tests:      %s\n  node_tests: %s\n  web build:  %s\n  smoke:      %s\n' "${TESTS:-(none)}" "${NT:-(none)}" "$WEBB" "$SMOKE"
  echo "  gh workflow run ci-targeted.yml --ref $BR -f after=$AFTER -f smoke=$SMOKE -f web=$WEBB -f tests='$TESTS' -f node_tests='$NT'"
  [ "$DRY" = 1 ] && { say "dry run - nothing pushed, dispatched or tagged"; exit 0; }

  [ "$SHA" = "$BASE" ] && echo "(no new commit - rerunning the failed tests on $BASE)" || { git push -q origin HEAD:master || die "push refused - master moved; rebase and run again"; echo "pushed $SHA to master (its full ci.yml runs there, not waited on)"; }
  # a branch pinned to the sha: a dispatch on master would test whatever master is by then
  git push -q -f origin "$SHA:refs/heads/$BR"
  local T0 TRUN=""; T0=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  gh workflow run ci-targeted.yml --ref "$BR" -f after="$AFTER" -f smoke="$SMOKE" -f web="$WEBB" -f tests="$TESTS" -f node_tests="$NT"
  for i in $(seq 1 40); do TRUN=$(gh run list --workflow ci-targeted.yml --commit "$SHA" --json databaseId,createdAt -q "[.[] | select(.createdAt >= \"$T0\")][0].databaseId // empty"); [ -n "$TRUN" ] && break; sleep 5; done
  [ -n "$TRUN" ] || die "no ci-targeted.yml run appeared for $SHA"
  echo "targeted run $TRUN"
  "$ROOT/tools/ci-failures.sh" --wait "$TRUN" >/dev/null && R=0 || R=1
  git push -q --delete origin "$BR" || true
  [ "$R" = 0 ] || stop_red "$TRUN"
  publish_tail "$SHA"
}

[ -n "$AFTER" ] && { targeted; exit 0; }
[ "$DRY$FIXED" = 00 ] || die "--fixed and --dry-run go with --after <run-id>"

say "preflight"
git fetch -q origin
[ -z "$(git status --porcelain)" ] || die "the tree is not clean - commit or stash first"
git merge-base --is-ancestor origin/master HEAD || die "HEAD is behind origin/master - merge or rebase first"
git ls-remote --tags origin "v$V" | grep -q . && die "v$V is already tagged - PyPI numbers are never reused"
OLD=$(python -c "import re;print(re.search(r'^version = \"([^\"]+)\"',open('pyproject.toml').read(),re.M)[1])")
# ...already bumped (a release that stopped red, fixed on master since): no bump, just build, push, CI and tag
SAME=0; [ "$OLD" != "$V" ] || SAME=1

say "bump $OLD -> $V in the seven places"
[ "$SAME" = 1 ] && echo "(already $V - no bump)"
[ "$SAME" = 1 ] || python - "$OLD" "$V" <<'EOF'
import sys, re, json, datetime
old, new = sys.argv[1:]
def sub(p, n=None):
    t = open(p, encoding='utf8', newline='').read(); c = t.count(old)
    if not c or (n is not None and c != n): sys.exit(f'{p}: expected {n or "some"} of {old}, found {c}')
    open(p, 'w', encoding='utf8', newline='').write(t.replace(old, new))
for p in ('pyproject.toml', 'README.md', 'README.zh-CN.md', 'docs/roadmap.md'): sub(p)
sub('website/src/demoFixtures.json', 3)
m = 'docs/site/manifest.json'; raw = open(m, encoding='utf8', newline='').read(); d = json.loads(raw); nl = '\r\n' if '\r\n' in raw else '\n'
d['version'], d['updated'] = new, datetime.date.today().isoformat()
open(m, 'w', encoding='utf8', newline='').write((json.dumps(d, indent=2, ensure_ascii=False) + '\n').replace('\n', nl))
for p in ('README.md', 'README.zh-CN.md'):   # the badge's cache-buster: a new URL is a fresh fetch for camo
    t = open(p, encoding='utf8', newline='').read(); open(p, 'w', encoding='utf8', newline='').write(re.sub(r'asof=[0-9a-z.-]+', f'asof={new}', t))
EOF

# WHAT THIS RELEASE CHANGED, on the docs page the Assistant searches (tools/whatsnew.py, TQ-1251) - a section already there is kept
say "write what's new in $V"
python tools/whatsnew.py "$V" || die "whatsnew failed"

say "build the UI, the demo and the docs"
(cd website && "${N[@]}" npm run build >/dev/null && "${N[@]}" npm run build:demo >/dev/null && "${N[@]}" npm run build:docs >/dev/null) || die "a build failed"

if [ "${SKIP_GATES:-}" != 1 ]; then
  # ~40s together (2026-11-09: node 17s, pytest 22s) - kept, since a red release commit costs a CI round; the full suites run in CI
  say "fast gates (the full suites run in CI)"
  # ...once more on a failure: a few timer tests flake under load, and a real failure fails twice
  (cd website && { "${N[@]}" node --test "test/*.test.mjs" > /tmp/release-node.log 2>&1 || "${N[@]}" node --test "test/*.test.mjs" > /tmp/release-node.log 2>&1; }) || { grep -E "^not ok" /tmp/release-node.log | head; die "node unit tests failed twice"; }
  # (`|| true`: grep finds nothing in the good case and exits 1, which set -e + pipefail would take for a failure)
  U=$(cd website && { npm exec --yes --package=node@22 --package=eslint@10.10.0 -- eslint -c eslint.undef.mjs -f json src 2>/dev/null | grep -o '"ruleId":"no-undef"' || true; } | wc -l)
  [ "$U" = 0 ] || die "$U undefined names (eslint no-undef)"
  TASKUARY_HOME="$(mktemp -d)" python -m pytest -q -p no:cacheprovider tests/test_docs_manifest.py tests/test_promptmap_and_catalog.py \
    tests/test_stand_ins_stay_out_of_code.py tests/test_timewords.py tests/test_task_tools.py > /tmp/release-py.log 2>&1 || { grep -E "^FAILED" /tmp/release-py.log; die "version/docs pytest gates failed"; }
fi

say "commit and push"
git add -A
git commit -q --allow-empty -m "Release $V

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push -q origin HEAD:master
SHA=$(git rev-parse HEAD); echo "pushed $SHA"
[ -d "$MAIN/.git" ] || [ -f "$MAIN/.git" ] && (cd "$MAIN" && [ -z "$(git status --porcelain)" ] && git fetch -q origin && git merge --ff-only -q origin/master && echo "main checkout -> $(git rev-parse --short HEAD)") || true

say "wait for ci.yml on $SHA"
RUN=""; for i in $(seq 1 40); do RUN=$(gh run list --workflow ci.yml --commit "$SHA" --json databaseId -q '.[0].databaseId'); [ -n "$RUN" ] && break; sleep 15; done
[ -n "$RUN" ] || die "no ci.yml run appeared for $SHA"
# ...no automatic rerun of whole jobs (a test part is ~10 min): a red run stops here, and the targeted road reruns only what failed
"$ROOT/tools/ci-failures.sh" --wait "$RUN" >/dev/null || stop_red "$RUN"
publish_tail "$SHA"

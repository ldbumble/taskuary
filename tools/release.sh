#!/usr/bin/env bash
# ONE COMMAND FROM MASTER TO PYPI (the owner, 2026-10-27: "it's been literally all day to pass one fix .. we need a better system").
# Usage, from a clean checkout of master:  tools/release.sh 0.3.9.54
#   bump the seven places -> build the UI, demo and docs -> fast local gates -> commit, push
#   -> wait for ci.yml on THAT commit -> print the failing tests -> rerun failed jobs once (CI's slow machines flake)
#   -> tag when green -> wait for publish.yml -> check PyPI and the GitHub release -> fast-forward the main checkout.
# It stops, naming the failing tests, the moment something is red twice. It never cancels a run and never tags red.
# Env: MAIN=<the owner's checkout to fast-forward> (default ../taskhub), SKIP_GATES=1 to skip the local gates (CI still gates).
set -euo pipefail
V="${1:?usage: tools/release.sh X.Y.Z.W}"
ROOT="$(git rev-parse --show-toplevel)"; cd "$ROOT"
MAIN="${MAIN:-$ROOT/../taskhub}"
say() { printf '\n== %s\n' "$*"; }
die() { printf '\n!! %s\n' "$*" >&2; exit 1; }
N=(npm exec --yes --package=node@22 --)

say "preflight"
git fetch -q origin
[ -z "$(git status --porcelain)" ] || die "the tree is not clean - commit or stash first"
git merge-base --is-ancestor origin/master HEAD || die "HEAD is behind origin/master - merge or rebase first"
git ls-remote --tags origin "v$V" | grep -q . && die "v$V is already tagged - PyPI numbers are never reused"
OLD=$(python -c "import re;print(re.search(r'^version = \"([^\"]+)\"',open('pyproject.toml').read(),re.M)[1])")
[ "$OLD" != "$V" ] || die "pyproject already says $V"

say "bump $OLD -> $V in the seven places"
python - "$OLD" "$V" <<'EOF'
import sys, re, json, datetime
old, new = sys.argv[1:]
def sub(p, n=None):
    t = open(p, encoding='utf8').read(); c = t.count(old)
    if not c or (n is not None and c != n): sys.exit(f'{p}: expected {n or "some"} of {old}, found {c}')
    open(p, 'w', encoding='utf8').write(t.replace(old, new))
for p in ('pyproject.toml', 'README.md', 'README.zh-CN.md', 'docs/roadmap.md'): sub(p)
sub('website/src/demoFixtures.json', 3)
m = 'docs/site/manifest.json'; d = json.load(open(m, encoding='utf8'))
d['version'], d['updated'] = new, datetime.date.today().isoformat()
open(m, 'w', encoding='utf8').write(json.dumps(d, indent=2, ensure_ascii=False) + '\n')
for p in ('README.md', 'README.zh-CN.md'):   # the badge's cache-buster: a new URL is a fresh fetch for camo
    t = open(p, encoding='utf8').read(); open(p, 'w', encoding='utf8').write(re.sub(r'asof=[0-9a-z-]+', f'asof={new}', t))
EOF

say "build the UI, the demo and the docs"
(cd website && "${N[@]}" npm run build >/dev/null && "${N[@]}" npm run build:demo >/dev/null && "${N[@]}" npm run build:docs >/dev/null) || die "a build failed"

if [ "${SKIP_GATES:-}" != 1 ]; then
  say "fast gates (the full suites run in CI)"
  (cd website && "${N[@]}" node --test "test/*.test.mjs" > /tmp/release-node.log 2>&1) || { grep -E "^not ok" /tmp/release-node.log | head; die "node unit tests failed"; }
  U=$(cd website && npm exec --yes --package=node@22 --package=eslint@10.10.0 -- eslint -c eslint.undef.mjs -f json src 2>/dev/null | grep -o '"ruleId":"no-undef"' | wc -l)
  [ "$U" = 0 ] || die "$U undefined names (eslint no-undef)"
  TASKUARY_HOME="$(mktemp -d)" python -m pytest -q -p no:cacheprovider tests/test_docs_manifest.py tests/test_promptmap_and_catalog.py \
    tests/test_stand_ins_stay_out_of_code.py tests/test_timewords.py tests/test_task_tools.py > /tmp/release-py.log 2>&1 || { grep -E "^FAILED" /tmp/release-py.log; die "version/docs pytest gates failed"; }
fi

say "commit and push"
git add -A
git commit -qm "Release $V

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push -q origin HEAD:master
SHA=$(git rev-parse HEAD); echo "pushed $SHA"
[ -d "$MAIN/.git" ] || [ -f "$MAIN/.git" ] && (cd "$MAIN" && [ -z "$(git status --porcelain)" ] && git fetch -q origin && git merge --ff-only -q origin/master && echo "main checkout -> $(git rev-parse --short HEAD)") || true

say "wait for ci.yml on $SHA"
RUN=""; for i in $(seq 1 40); do RUN=$(gh run list --workflow ci.yml --commit "$SHA" --json databaseId -q '.[0].databaseId'); [ -n "$RUN" ] && break; sleep 15; done
[ -n "$RUN" ] || die "no ci.yml run appeared for $SHA"
"$ROOT/tools/ci-failures.sh" --wait "$RUN" && GREEN=1 || GREEN=0
if [ "$GREEN" != 1 ]; then
  say "rerunning the failed jobs once (CI's slower machines flake on timing tests)"
  gh run rerun "$RUN" --failed; sleep 30
  "$ROOT/tools/ci-failures.sh" --wait "$RUN" || die "CI is red twice on $SHA - nothing was tagged. Fix the tests above on master, then run tools/release.sh $V again (the number was never used)"
fi

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
say "v$V is out. The owner's app runs from the main checkout: restart Taskuary to load it."

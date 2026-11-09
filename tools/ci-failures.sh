#!/usr/bin/env bash
# WHICH TESTS FAILED in a CI run, by name - not "exit code 1" (2026-10-27: a day lost reading logs by hand).
# Usage: tools/ci-failures.sh [--wait] [--ids] <run-id | commit-sha>
#   --wait  poll until the run completes. Exit 0 when it is green, 1 when it is not (failing tests printed).
#   --ids   print what to rerun, one per line, for tools/release.sh --after (the owner, 2026-11-09: "rerun just that test"):
#           `py <pytest id>`, `node all`, `smoke`, or `stuck <job>` for a failure no test id can stand for (docker, a hang).
#           A test job that failed without naming a test (it ran out of time) gives its whole shard as `py <file>` lines.
# A job that ran past its time limit shows as CANCELLED, not failed: it is named as such here, since a cancelled job can also be
# a person's cancel. GitHub serves a run's logs only once the WHOLE run completes, so this waits for that before reading them.
set -uo pipefail
WAIT=0; IDS=0
while :; do case "${1:-}" in --wait) WAIT=1; shift;; --ids) IDS=1; shift;; *) break;; esac; done
REF="${1:?usage: tools/ci-failures.sh [--wait] <run-id | sha>}"
if [[ "$REF" =~ ^[0-9]+$ ]]; then RUN="$REF"; else RUN=$(gh run list --workflow ci.yml --commit "$(git rev-parse "$REF")" --json databaseId -q '.[0].databaseId'); fi
[ -n "$RUN" ] || { echo "no ci.yml run for $REF"; exit 2; }
while :; do
  S=$(gh run view "$RUN" --json status,conclusion -q '"\(.status) \(.conclusion)"')
  case "$S" in completed*) break;; esac
  [ "$WAIT" = 1 ] || { echo "run $RUN: $S (not finished)"; gh run view "$RUN" --json jobs -q '.jobs[] | select(.conclusion=="failure") | "  failed so far: \(.name)"'; exit 1; }
  sleep 30
done
# pytest's summary lines, a subtest's too: `FAILED tests/x.py::T::t - msg`, `ERROR tests/x.py`, `SUBFAILED(i=1) tests/x.py::t`
pyids() { gh run view "$RUN" --log --job "$1" 2>/dev/null | grep -oE "(FAILED|ERROR|SUBFAILED\([^)]*\)) tests/[^ ]+" | sed -E 's/^[^ ]+ //' | sort -u; }
if [ "$IDS" = 1 ]; then
  echo "$S" | grep -q " success" && exit 0
  JOBS=$(gh run view "$RUN" --json jobs -q '.jobs[] | select(.conclusion=="failure" or .conclusion=="cancelled" or .conclusion=="timed_out") | select(.name!="ci-required" and .name!="build-exe") | "\(.databaseId)	\(.name)"')
  while IFS=$'	' read -r J NAME; do
    [ -n "$J" ] || continue
    case "$NAME" in
      test*) I=$(pyids "$J")
        if [ -n "$I" ]; then sed 's/^/py /' <<<"$I"
        elif [[ "$NAME" =~ ^test\ \(([a-z-]+),\ [0-9.]+,\ ([0-9]+)\)$ ]]; then   # a sharded part that ran out of time: all of its files
          OF=$(gh run view "$RUN" --json jobs -q "[.jobs[] | select(.name | startswith(\"test (${BASH_REMATCH[1]},\"))] | length")
          python tools/test_shard.py "${BASH_REMATCH[2]}" "$OF" | sed 's/^/py /'
        else echo "stuck $NAME"; fi;;
      build-web) echo "node all";;
      "browser smoke"|smoke) echo "smoke";;
      *) echo "stuck $NAME";;
    esac
  done <<<"$JOBS"
  exit 1
fi
echo "run $RUN: $S"
echo "$S" | grep -q " success" && exit 0
gh run view "$RUN" --json jobs -q '.jobs[] | select(.conclusion=="cancelled") | "CANCELLED (ran past its time limit, or a cancel): \(.name)  \(.startedAt) -> \(.completedAt)"'
for J in $(gh run view "$RUN" --json jobs -q '.jobs[] | select(.conclusion=="failure" and .name!="ci-required") | .databaseId'); do
  echo "FAILED: $(gh run view "$RUN" --json jobs -q ".jobs[] | select(.databaseId==$J) | .name")"
  gh run view "$RUN" --log --job "$J" 2>/dev/null | cut -c60- \
    | grep -oE "FAILED tests/[^ ]+.{0,160}|SUBFAILED\([^)]*\) tests/[^ ]+.{0,160}|not ok [0-9]+ - .{0,160}|error: '.{0,160}|Verify committed.{0,80}|(WAYOUT|CRASH|SWAP|SEEN|NAMES|RING|SEARCH|REREAD|AGAIN|BASED) .{0,160}" \
    | sed 's/^[0-9TZ:.-]* *//' | sort -u | head -12 | cut -c1-260 | sed 's/^/  /'
done
exit 1

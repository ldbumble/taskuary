#!/usr/bin/env bash
# WHICH TESTS FAILED in a CI run, by name - not "exit code 1" (2026-10-27: a day lost reading logs by hand).
# Usage: tools/ci-failures.sh [--wait] <run-id | commit-sha>
#   --wait  poll until the run completes. Exit 0 when it is green, 1 when it is not (failing tests printed).
# A job that ran past its time limit shows as CANCELLED, not failed: it is named as such here, since a cancelled job can also be
# a person's cancel. GitHub serves a run's logs only once the WHOLE run completes, so this waits for that before reading them.
set -uo pipefail
WAIT=0; [ "${1:-}" = "--wait" ] && { WAIT=1; shift; }
REF="${1:?usage: tools/ci-failures.sh [--wait] <run-id | sha>}"
if [[ "$REF" =~ ^[0-9]+$ ]]; then RUN="$REF"; else RUN=$(gh run list --workflow ci.yml --commit "$(git rev-parse "$REF")" --json databaseId -q '.[0].databaseId'); fi
[ -n "$RUN" ] || { echo "no ci.yml run for $REF"; exit 2; }
while :; do
  S=$(gh run view "$RUN" --json status,conclusion -q '"\(.status) \(.conclusion)"')
  case "$S" in completed*) break;; esac
  [ "$WAIT" = 1 ] || { echo "run $RUN: $S (not finished)"; gh run view "$RUN" --json jobs -q '.jobs[] | select(.conclusion=="failure") | "  failed so far: \(.name)"'; exit 1; }
  sleep 30
done
echo "run $RUN: $S"
echo "$S" | grep -q " success" && exit 0
gh run view "$RUN" --json jobs -q '.jobs[] | select(.conclusion=="cancelled") | "CANCELLED (ran past its time limit, or a cancel): \(.name)  \(.startedAt) -> \(.completedAt)"'
for J in $(gh run view "$RUN" --json jobs -q '.jobs[] | select(.conclusion=="failure" and .name!="ci-required") | .databaseId'); do
  echo "FAILED: $(gh run view "$RUN" --json jobs -q ".jobs[] | select(.databaseId==$J) | .name")"
  gh run view "$RUN" --log --job "$J" 2>/dev/null | cut -c60- \
    | grep -oE "FAILED tests/[^ ]+.{0,160}|not ok [0-9]+ - .{0,160}|error: '.{0,160}|Verify committed.{0,80}|(WAYOUT|CRASH|SWAP|SEEN|NAMES|RING|SEARCH|REREAD|AGAIN|BASED) .{0,160}" \
    | sed 's/^[0-9TZ:.-]* *//' | sort -u | head -12 | cut -c1-260 | sed 's/^/  /'
done
exit 1

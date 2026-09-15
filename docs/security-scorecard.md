# OpenSSF Scorecard

The [published report](https://scorecard.dev/viewer/?uri=github.com/ldbumble/taskuary)
scored **3.5/10** on 2026-09-14 for commit
`ab7a50b632efd6027951957c9f8d2a068a77fc5b`.
Its [JSON results](https://api.scorecard.dev/projects/github.com/ldbumble/taskuary)
include the scanned commit and reasons for each check. The badge describes that scan,
not uncommitted changes or a guarantee that the application has no vulnerabilities.

## Repository changes

- Upgrade Vite to 6.4.3 and regenerate the website lockfile. This addresses the four
  reported Vite/esbuild advisories without moving to a different bundler. These concern
  development-server access, including Windows paths. Production serves built assets.
- Pin GitHub Actions to verified commit hashes and the Docker base image to its verified
  multi-platform manifest digest. Dependabot proposes updates to those pins, Python
  dependencies, and both npm projects each week.
- Give workflows read-only permissions by default. Only release publishing and the
  downloads-chart job retain the write permissions their operations require.
- Scan Python and JavaScript/TypeScript with CodeQL on pushes, pull requests, and weekly.
- Build the packaged UI and release UI with Node 22. Commit regenerated assets with
  source or build-tool changes so CI's existing source/bundle check stays useful.
- Run CI and CodeQL on pushes and pull requests. Branch protection is currently disabled so
  the daily generated download chart can commit directly to master.
- Publish signed provenance for future release artifacts and attach the Sigstore bundle.
  See [verification instructions](../RELEASING.md#verify-release-provenance).
- Commit daily chart changes directly to master with GitHub's short-lived repository token.
  The chart workflow runs the focused generator tests before committing because pushes made
  with that token do not start another workflow run.

CodeQL and Dependabot become active once their configuration reaches the default branch.
CodeQL findings need review after the first hosted run. Scorecard publishes on a push to
master and weekly; a new score cannot be promised before that scan completes.

## Remaining work

| Check | Published result | Next step |
| --- | --- | --- |
| Branch protection | 0/10 | Direct automated chart commits currently require an unprotected master branch. Revisit this if the update mechanism changes. |
| Code review | 0/10 | Use pull requests with independent human review; Scorecard did not find approvals on the last 30 changesets. AI reviews do not count for this check. |
| CI tests | Unscored | Scorecard found no pull requests. Keep the existing tests running and merge tested PRs; do not remove checks to obtain a green badge. |
| Signed releases | 0/10 | The next tagged release will generate signed provenance. Existing unsigned releases remain historical results. |
| Dependency pinning | 2/10 | Action/image pins address part of this. Reproducible Python build inputs with hashes require a separate lockfile/build design; flexible library dependency ranges alone do not provide it. |
| Fuzzing | 0/10 | Add meaningful fuzz coverage for parsers and boundaries, then integrate it into CI. |
| Best practices badge | 0/10 | Complete the OpenSSF self-assessment with evidence for its criteria. |
| Maintained | 0/10 | The report penalizes repositories younger than 90 days. Continue maintaining the project; this is not evidence that its current tests fail. |
| Contributors | 3/10 | Broader independent contributions improve this over time. |

The automated chart workflow uses GitHub's short-lived repository token and does not need
a personal access token.

The [OpenSSF check definitions](https://github.com/ossf/scorecard/blob/main/docs/checks.md)
explain the scoring rules and their limitations. Security policy, licensing, packaging,
binary artifacts, and dangerous-workflow checks already scored 10/10 in this report.

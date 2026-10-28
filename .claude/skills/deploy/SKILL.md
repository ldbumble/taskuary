---
name: deploy
description: >
  Ship Taskuary: land a fix on master, then release it to PyPI with one command (tools/release.sh). Use when asked to
  deploy, release, ship, publish, push, "push to PyPI", cut a version, bump or tag. Encodes the fast loop the owner asked
  for on 2026-10-27 ("it's been literally all day to pass one fix .. we need a better system").
---

# Shipping Taskuary

Two separate things, never mixed:

1. **A fix reaches the owner** when it is on `master` - the owner's app runs from the main checkout
   (the owner's own working copy of the repo, not a worktree), so a push + fast-forward + their restart is "shipped" for them.
2. **A release reaches PyPI** when `tools/release.sh X.Y.Z.W` finishes. That is the only way to tag.

## 1. Land a fix (minutes, not hours)

- One fix, one branch, merged to `master` as soon as **its own** tests pass: the test files for what it touched, plus
  `npm exec --yes --package=node@22 -- node --test "test/*.test.mjs"` (in `website/`) when `website/src` changed. Never the full
  suites locally - CI runs them on parallel machines. Never batch ten branches and integrate at the end: every merge re-runs
  everything, and a day goes.
- `website/src` changed -> rebuild the committed UI before pushing (`npm run build`, plus `build:demo`; `build:docs` when
  `docs/site/*.md` or the tool catalog changed - CI's build-web job rejects a stale `site/docs`).
- Push, then fast-forward the owner's checkout: `git -C <main> merge --ff-only origin/master` (only when it is clean). Tell them:
  restart Taskuary (Python changed) or refresh (UI only).
- Red CI on master -> **fix forward on master at once**. `tools/ci-failures.sh <run-id|sha>` names the failing tests.
- Agents in parallel: few, on disjoint files, targeted tests only. Five agents each running full suites on one machine made
  every run slow and every timing test flaky.

## 2. Release (one command)

From a clean, up-to-date checkout of master:

```bash
tools/release.sh 0.3.9.54
```

It bumps the seven version places (pyproject, both READMEs + their badge `asof=`, roadmap, docs manifest, the demo's three
fixture fields), builds UI/demo/docs, runs the fast gates (node unit, eslint no-undef, version/docs/catalog/timewords pytest),
commits, pushes, waits for `ci.yml` on **that exact commit**, prints failing tests, reruns failed jobs **once** (CI's slower
machines flake on timing), tags only when green, waits for `publish.yml` (reruns once - the exe's signing download flakes),
verifies PyPI + the GitHub release with `Taskuary.exe`, and fast-forwards the main checkout. Red twice -> it stops and names
the tests: fix them on master, run it again with the **same** number (it was never tagged).

Run it in the background and report when it ends; do not babysit runs by hand.

## Rules that each cost hours on 2026-10-27

- **Never cancel a run by looking it up by commit** (`gh run list --commit X ... | cancel`) right after a push: it cancelled the
  run that mattered. Cancel only by a run id you read for that exact sha - or don't cancel; let stale runs finish.
- **A browser job that runs past its time limit shows as CANCELLED, not failed.** Keep each part well under its limit: CI runs
  `browser/shard.mjs <part> 6` with 20 minutes each; a new browser test file goes in `website/package.json` `test:browser`, and
  if a part creeps past ~14 minutes, add parts.
- **Request-count and timing tests** must count what they mean on a slow machine: wait for the state, never for a fixed sleep;
  CI's macOS gets 1.25x time budgets (`CI` + darwin), local stays strict.
- **Merging branches by hand:** never `git checkout --ours <file>` on a conflicted file - it drops the other side's clean hunks
  too (lost three overnight fixes once). Resolve the conflicted hunks only; `website/package.json`'s `test:browser` is the union.
- **Version numbers on PyPI can never be reused.** The publish workflow gates on CI (`ci-green`), so a red commit never uploads;
  `tools/release.sh` refuses a number already tagged.
- **Never commit the owner's data** (CLAUDE.md). Commit messages and test names use the stand-ins.
- Release notes go in the tag message and the GitHub release; the README badge updates through its `asof=` cache-buster.

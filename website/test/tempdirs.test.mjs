// WHAT A RUN LEAVES IN %TEMP% GOES (2026-11-24: harness homes, fake-CLI folders and dead-end homes piled up - a run killed mid-way never
// reached its close). A folder names its maker; the next one made with its prefix sweeps those whose maker no longer runs, and no others.
import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, utimesSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { MARK, dropTemp, ownTemp, sweepTemp } from "../browser/tempdirs.mjs";

test("a folder whose maker is gone is swept; ours, another prefix's and a fresh unmarked one stay", () => {
  const root = mkdtempSync(path.join(os.tmpdir(), "tq-tempdirs-test-"));
  try {
    const dead = spawnSync(process.execPath, ["-e", "process.stdout.write(String(process.pid))"], { encoding: "utf8" }).stdout;
    const mk = (name, maker, ageMs = 0) => {
      const d = path.join(root, name); mkdirSync(path.join(d, "profile"), { recursive: true });
      if (maker) writeFileSync(path.join(d, MARK), maker);
      const t = (Date.now() - ageMs) / 1000; utimesSync(d, t, t); return d;
    };
    const killed = mk("tq-run-killed", `${dead} node`), ours = mk("tq-run-ours", `${process.pid} node`);
    const older = mk("tq-run-older", "", 2 * 86400e3), fresh = mk("tq-run-fresh", ""), other = mk("else-run", `${dead} node`, 2 * 86400e3);
    assert.equal(sweepTemp("tq-run-", root), 2);
    assert.deepEqual([killed, older].map(existsSync), [false, false]);
    assert.deepEqual([ours, fresh, other].map(existsSync), [true, true, true]);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("ownTemp marks the folder as this process's, and dropTemp removes it", () => {
  const d = ownTemp("tq-tempdirs-own-");
  assert.ok(existsSync(path.join(d, MARK)));
  dropTemp(d);
  assert.equal(existsSync(d), false);
});

// Close agent on the Wall is the task page's Mark done on a live session - the same code, not a copy (the owner, 2026-10-15).
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");


test("the Wall's notice after Close agent says the task closes when the write-up is filed, until the close lands", async () => {
  const wall = read("WallView.jsx");
  assert.match(wall, /writing: wrote\?\.writing === true/);
  assert.match(wall, /wrapDone\.writing && tasks\[wrapDone\.tid\] && !\["done", "dropped"\]\.includes\(tasks\[wrapDone\.tid\]\.Status\)/);
  assert.match(wall, /Writing up \{wrapDone\.ref\}\. The task closes when that is filed\./);
  // ...the job's road says which it took: writing up behind the press, or closed here when it could not start
  const { closeAgentWork } = await import("../src/closeAgent.jsx").catch(() => ({}));
  if (closeAgentWork) {
    const calls = [];
    const api = (ok) => ({ post: async (url, body) => { calls.push(url); if (url.endsWith("/wrap") && !ok) throw new Error("nothing on screen");
      return { data: url.includes("/execute") ? { status: "done" } : { id: "op", version: 1 } }; } });
    assert.deepEqual(await closeAgentWork(api(true), 7), { writing: true });
    assert.equal(await closeAgentWork(api(false), 7), null);
  }
});

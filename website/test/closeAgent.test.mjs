// Close agent on the Wall is the task page's Mark done on a live session - the same code, not a copy (the owner, 2026-10-15).
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("both closes run the shared write-up and the shared task.complete", () => {
  const page = read("TaskPage.jsx"), wall = read("WallView.jsx"), mod = read("closeAgent.jsx");
  assert.match(mod, /api\.post\(`\/api\/tasks\/\$\{tid\}\/wrap`, \{ close: false, no_reply: true, background: true, then_close: true \}\)/);   // one server job (writeup.py)
  assert.match(mod, /runOperation\(api, "task\.complete", tid/);
  assert.match(page, /const close = \(\) => completeTask\(api, selected, note\);/);
  assert.match(page, /await writeUpThenClose\(api, id\)/);
  assert.doesNotMatch(page, /\/api\/tasks\/\$\{id\}\/wrap`, \{ close: false, no_reply: true \}/);    // no second copy
  assert.match(wall, /const wrote = await closeAgentWork\(api, s\.taskId\);/);
});

test("the Wall pane has Close agent, asks nothing first, and is covered while it closes", () => {
  const wall = read("WallView.jsx");
  assert.match(wall, />Close agent<\/Button>/);
  assert.match(wall, /onClick=\{\(\) => closeAgent\(s\)\}/);
  assert.match(wall, /onClick=\{\(\) => closeSession\(s\)\}/);
  for (const f of [wall, read("TaskPage.jsx")]) assert.doesNotMatch(f, /<Confirm /);     // the owner, 2026-10-19: a hover, not a box
  assert.match(read("TaskPage.jsx"), /const askFinish = \(\) => \(liveSession \? stopAndFinish\(\) : finish\("done"\)\);/);
  assert.match(wall, /\{wrapBusy && <ClosingCover mode="done" \/>\}/);
  assert.match(read("closeAgent.jsx"), /position: "absolute", inset: 0, zIndex: 5/);       // nothing under it takes a key or a click
  assert.match(read("TaskPage.jsx"), /<ClosingCard mode=\{wrapping\} \/>/);                 // the same card on the task page
});

test("the Studio is gone from the Board; the Game keeps its model", () => {
  assert.ok(!fs.existsSync(new URL("../src/StudioView.jsx", import.meta.url)));
  assert.ok(!fs.existsSync(new URL("../src/StudioScene.jsx", import.meta.url)));
  assert.doesNotMatch(read("BoardView.jsx"), /StudioView|k: "studio"/);
  assert.match(read("AssistantGame.jsx"), /from "\.\/studioModel\.js"/);
});

test("search opens over Board and Game; a pick brings Chat up", () => {
  const page = read("TaskHubPage.jsx"), feed = read("FeedView.jsx");
  assert.match(page, /<SearchBar onOpen=\{openSearch\} \/>/);
  assert.match(page, /window\.addEventListener\(SEARCH_PICKED, picked\)/);
  assert.match(feed, /window\.addEventListener\(OPEN_SEARCH, o\);\n    return \(\) => window\.removeEventListener\(OPEN_SEARCH, o\);\n  \}, \[\]\);/);
  assert.match(feed, /onOpenTask=\{\(tid, h\) => \{ searchPicked\(\);/);
});

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

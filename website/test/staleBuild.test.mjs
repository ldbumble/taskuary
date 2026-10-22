import test from "node:test";
import assert from "node:assert/strict";
import { buildMove, isStale, staleWhat } from "../src/staleBuild.js";

test("a rebuilt bundle asks for a reload", () => {
  assert.equal(staleWhat("index-aaa.js", { asset: "index-bbb.js", version: "0.3.2.4", disk_version: "0.3.2.4" }), "A new version is running – Reload");
  assert.equal(staleWhat("index-aaa.js", { asset: "index-aaa.js", version: "0.3.2.4", disk_version: "0.3.2.4" }), "");
});

test("a version bump on disk asks for a restart, and outranks the reload", () => {
  // the server still reports the number it started with; reloading the page fixes nothing
  assert.equal(staleWhat("index-aaa.js", { asset: "index-bbb.js", version: "0.3.2.3", disk_version: "0.3.2.4" }), "v0.3.2.4 on disk — restart Taskuary");
});

test("unknown answers are never stale", () => {
  assert.equal(staleWhat("", { asset: "index-bbb.js" }), "");
  assert.equal(staleWhat("index-aaa.js", null), "");
  assert.equal(isStale("", "x"), false);
});

test("a restarted server on a new build reloads a page at rest, once, and only says so to someone typing", () => {
  const now = { asset: "index-new.js", version: "0.3.9.20", disk_version: "0.3.9.20" };
  assert.equal(buildMove("index-new.js", now), "");                                          // same build: nothing
  assert.equal(buildMove("index-old.js", now), "reload");                                    // different, at rest: reload
  assert.equal(buildMove("index-old.js", now, { busy: true }), "line");                      // different, typing: the line
  assert.equal(buildMove("index-old.js", now, { reloaded: "index-new.js" }), "");            // already reloaded for it: nothing
  assert.equal(buildMove("index-old.js", now, { reloaded: "index-older.js" }), "reload");    // ...a later build earns its own
});

test("no reload on an unknown answer or a restart still pending", () => {
  assert.equal(buildMove("", { asset: "index-new.js" }), "");
  assert.equal(buildMove("index-old.js", null), "");
  assert.equal(buildMove("index-old.js", { asset: "" }), "");
  assert.equal(buildMove("index-old.js", { asset: "index-new.js", version: "0.3.9.19", disk_version: "0.3.9.20" }), "");
});

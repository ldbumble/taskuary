import test from "node:test";
import assert from "node:assert/strict";
import { isStale, staleWhat } from "../src/staleBuild.js";

test("a rebuilt bundle asks for a reload", () => {
  assert.equal(staleWhat("index-aaa.js", { asset: "index-bbb.js", version: "0.3.2.4", disk_version: "0.3.2.4" }), "update ready — reload");
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

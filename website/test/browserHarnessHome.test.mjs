// The browser harness reads nothing of the person's own profile: their Claude settings (which once told a real-CLI walk their hook
// ports) are never opened - the ports are a fixed list, refused outright - and no file under website/browser names that file.
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const dir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../browser");
const files = readdirSync(dir).filter((f) => /\.(mjs|js|py)$/.test(f)).map((f) => [f, readFileSync(path.join(dir, f), "utf8")]);

test("no browser script opens the person's own Claude settings", () => {
  for (const [f, src] of files) assert.doesNotMatch(src, /settings\.json/, f);
});

test("the live ports are refused by the harness and by the fixture server", () => {
  const harness = files.find(([f]) => f === "harness.mjs")[1], server = files.find(([f]) => f === "fixture_server.py")[1];
  assert.match(harness, /liveHookPorts = \[7787, 7796, 7797\]/);
  for (const p of [7787, 7796, 7797]) assert.match(server.match(/if PORT in \(([^)]*)\)/)[1], new RegExp(`\\b${p}\\b`));
});

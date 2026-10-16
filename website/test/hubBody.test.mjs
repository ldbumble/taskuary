// A Hub entry's body is drawn as markdown when it is markdown (the owner, 2026-10-16: industry reference posted to the Hub ran
// together as one paragraph - "it's hard to read now"); a plain sentence stays a plain sentence.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const hub = readFileSync(new URL("../src/HubView.jsx", import.meta.url), "utf8");

test("a Hub entry's markdown body - a table, a list - is rendered, and plain text stays plain", () => {
  assert.match(hub, /import \{ Md \} from "\.\/md\.jsx";/);
  assert.match(hub, /\{looksMd\(p\.Body\) \? <Md text=\{p\.Body\} \/>/);
  assert.match(hub, /whiteSpace: "pre-line"/, "plain text keeps its lines");
  assert.match(hub, /\.\.\.\(open \? \{\} : \{ maxHeight: "9\.5em", overflow: "hidden"/, "the list shows the start; a click opens the whole");
  assert.match(hub, /<Md text=\{p\.Body\} \/>/);
});

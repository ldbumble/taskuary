import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");


// ...a task hit is no longer keyed here at all: it is a press of its rail row by number (searchOpensRow.test.mjs)
test("a pulled row is keyed by its message or its report", () => {
  const src = read("AssistantView.jsx").match(/export const keyForRow = [\s\S]*?;\r?\n/)[0].replace("export const keyForRow = ", "return ");
  const keyForRow = new Function(src)();
  assert.equal(keyForRow({ MessageId: 7, TaskId: 3 }), "msg:7");
  assert.equal(keyForRow({ MessageId: 9, Channel: "report" }), "report:9");
});

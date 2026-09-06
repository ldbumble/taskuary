import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { restorableCurrent } from "../src/funnelPile.js";

const source = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");

test("a historical finished-task card is never restored as current funnel work", () => {
  const live = { key: "msg:1", kind: "message" };
  assert.equal(restorableCurrent([
    { card: live },
    { card: { key: "agent:2", kind: "agentdone" } },
  ]), live);
  assert.equal(restorableCurrent([{ card: { key: "agent:2", kind: "agentdone" } }]), null);
  assert.match(source, /const last = restorableCurrent\(data\.messages\)/);
  const events = source.slice(source.indexOf("if (data.events?.length)"), source.indexOf("// the item on the table is live"));
  assert.doesNotMatch(events, /setCurrent|setCurrentItem|currentRef\.current\s*=/,
    "live watcher updates do not choose any historical card as Current");
});

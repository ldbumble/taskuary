import test from "node:test";
import assert from "node:assert/strict";
import { readNdjson, readTurn, toolTarget } from "../src/assistantStream.js";

// THE CARD FIRST, THE RAIL AFTER IT (2026-10-20): a Next's `done` is answered the moment it lands, and the rail that follows
// on the same stream arrives as `pileLater` - null when it never comes, so the page loads the rail itself as before.
const stream = (chunks) => {
  const encoder = new TextEncoder();
  let release;
  const gate = new Promise((r) => { release = r; });
  const body = new ReadableStream({ async start(c) {
    for (const x of chunks) { if (x === "WAIT") await gate; else c.enqueue(encoder.encode(x)); }
    c.close();
  } });
  return { body, release };
};

test("a done whose rail follows is returned before the rail arrives, and the rail comes after it", async () => {
  const { body, release } = stream(['{"type":"context_update","say":"moved"}\n{"type":"done","say":"hi","item":{"key":"k"},"pile_follows":true}\n', "WAIT", '{"type":"pile","pile":{"items":[1]}}\n']);
  const seen = [];
  const answer = await readTurn(body, (ev) => seen.push(ev.type));
  assert.deepEqual(seen, ["context_update"]);
  assert.equal(answer.say, "hi"); assert.equal("pile_follows" in answer, false); assert.equal("pile" in answer, false);
  let landed = false; answer.pileLater.then(() => { landed = true; });
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(landed, false, "the card did not wait on the rail");
  release();
  assert.deepEqual(await answer.pileLater, { items: [1] });
});

test("a rail that never comes is null, and a plain done is the done", async () => {
  for (const tail of ['{"type":"error","error":"x"}\n', ""]) {
    const { body } = stream(['{"type":"done","item":{"key":"k"},"pile_follows":true}\n', tail]);
    assert.equal(await (await readTurn(body)).pileLater, null);
  }
  const { body } = stream(['{"type":"done","item":{"key":"k"},"pile":{"items":[]}}\n']);
  assert.deepEqual(await readTurn(body), { type: "done", item: { key: "k" }, pile: { items: [] } });
  assert.equal(await readTurn(stream([]).body), null);
  await assert.rejects(readTurn(stream(['{"type":"error","error":"no"}\n']).body, (ev) => { if (ev.type === "error") throw new Error(ev.error); }), /no/);
});

test("assistant events survive arbitrary network chunk boundaries", async () => {
  const encoder = new TextEncoder();
  const body = new ReadableStream({ start(controller) {
    controller.enqueue(encoder.encode('{"type":"tool_call","name":"B'));
    controller.enqueue(encoder.encode('ash"}\n{"type":"done","reply":"ok"}\n'));
    controller.close();
  } });
  const got = [];
  for await (const event of readNdjson(body)) got.push(event);
  assert.deepEqual(got, [{ type: "tool_call", name: "Bash" }, { type: "done", reply: "ok" }]);
});

test("tool cards lead with the useful argument", () => {
  assert.equal(toolTarget({ command: "rg hospitals" }), "rg hospitals");
  assert.equal(toolTarget({ query: "medical facilities news" }), "medical facilities news");
});

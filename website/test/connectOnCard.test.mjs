// A SEND CARD WHOSE CHANNEL IS NOT CONNECTED SAYS SO (the owner, 2026-11-08): its one move is the server's Connect (outbound.connect_fix,
// `Connect` on a review, `connect` on a post's card), which opens that connection's card - never a Send or a Post that can only fail
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the reply and email card and the post card both lead with Connect when the server says it is not connected", () => {
  const rd = src("ReviewDecision.jsx"), ac = src("ActionCard.jsx");
  assert.match(rd, /const connect = !proposal && !delivery\.frozen \? r\.Connect : null;/);
  assert.match(rd, /\.\.\.\(connect \? \[\s*\{ id: no\("connect"\), label: connect\.label, tone: "p", disabled: off, run: \(\) => openAppLink\(connect\.href\)/);
  assert.match(rd, /data-tq-not-connected=""[^>]*>\{connect\.says\}/);
  assert.match(ac, /st\.live && row\?\.connect \? <>/);
  assert.match(ac, /data-tq-act-connect="" onClick=\{\(\) => openAppLink\(row\.connect\.href\)\}>\{row\.connect\.label\}/);
  assert.doesNotMatch(rd + ac, /step=1/, "it opens the connection's card, not a setup step");
  // ...and under the draft itself Connect is the one button - no lit Send and close beside "No mailbox is connected" (2026-11-08 render check)
  assert.match(rd, /\{connect && r\.Status === "pending" \? \(\s*<Button size="small" variant="contained" disableElevation data-tq-connect=""/);
});

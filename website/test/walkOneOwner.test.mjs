// THE WALK HAS ONE OWNER (railwalk, 2026-10-30): every walk move - start, next, back, open, a section, every close on the table - is one POST
// to /api/walk/* and its one Answer is drawn by one function. The page draws nothing ahead of it and keeps no rule of which row comes next;
// this pins that the machinery that did (a close's early draw, the prepared line, the grace before a walk on) cannot come back.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (n) => fs.readFileSync(new URL(`../src/${n}`, import.meta.url), "utf8");

test("the page keeps none of the walk's old drawing-ahead machinery", () => {
  const view = read("AssistantView.jsx");
  for (const name of ["drawNextEarly", "aheadRef", "carryRef", "earlyRef", "adoptRef", "movedOnRef", "drawAhead", "takeEarlyBack", "advancedAt",
    "preparedFor", "unshow", "unconfirmedRef", "adviceHeld", "leavingRef", "const advance ="])
    assert.ok(!view.includes(name), `${name} is back in AssistantView.jsx`);
  assert.ok(!read("funnelPile.js").includes("preparedFor"), "the prepared Answer's picker is back");
});

test("every walk move is one POST to /api/walk/*, never the stream or a settle of the page's own", () => {
  const view = read("AssistantView.jsx");
  const turn = view.slice(view.indexOf("const turnOnce = useCallback"), view.indexOf("const turn = useCallback"));
  const walk = turn.indexOf("api.post(`/api/walk/${walkRoute}`"), stream = turn.indexOf('fetch("/api/concierge/stream"');
  assert.ok(walk > 0 && walk < stream, "a walk move returns from /api/walk/* before the stream is ever opened");
  assert.match(turn, /const walkRoute = \{ next: body\.key \? "open" : "next", back: "back", start: "start", leave: "leave", section: "open" \}\[body\.mode\];/);
  for (const n of ["AssistantView.jsx", "CanvasItem.jsx", "TaskPage.jsx", "RemindMe.jsx"]) {
    const s = read(n);
    assert.doesNotMatch(s, /\/api\/funnel\/settle|\/api\/concierge\/next/, `${n} moves the walk off /api/walk/*`);
  }
  // ...and the one function that draws an Answer is landed: the press itself folds the row it leaves and puts up only the rail's own row
  // for the one the server's walk.below names (rule 7: the next item draws at once - Next and Mark done waited a round trip without it)
  const surface = view.slice(view.indexOf("const surface = useCallback"), view.indexOf("useEffect(() => { surfaceRef.current = surface; }"));
  assert.equal((surface.match(/setMsgs\(\(m\) => \[\.\.\.m, \{[^}]*role: "assistant"/g) || []).length, 1, "one line drawn ahead of the answer, no more");
  assert.match(surface, /const \{ onIt, below \} = pressOnto\(walkNow, railNow, /);
  assert.match(read("funnelPile.js"), /const onIt = !!putDown && sameKey\(rail, walk\?\.on, putDown, card\);\n\s+const below = onIt && walk\.below/);
  assert.match(surface, /card: belowItem, ahead: true/);
  assert.match(surface, /else landed\(data, off\(\)\);/);
});

test("a close on the table is railwalk.leave: Mark done, a note, Remove, Remind me and a Send that closes", () => {
  const page = read("TaskPage.jsx"), item = read("CanvasItem.jsx");
  assert.match(item, /walkLeave=\{async \(how, x\) => \{ const \{ error, data \} = await onWalkLeave\(how, x\); if \(error\) throw error; return data; \}\}/);
  assert.match(page, /walkLeave\(note \? "note" : "done", note \? \{ note \} : \{\}\)/);
  assert.match(page, /walkLeave\("not_task"\)/);
  assert.match(page, /walkLeave\("sent", liveWork \? \{ stays: true \} : \{\}\)/);
  assert.match(page, /walkLeave\("remind", \{ until \}\)/);
});

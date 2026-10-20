// PREPARED NEXT (the owner, 2026-10-20): the server prepares the answer Next will give for the selection it hands the page;
// the press draws it at once on the one road ahead of the answer (drawAhead, shared with the rail row's draw-ahead of G8), the
// committed answer fills that same line in place or replaces it, and a failed press takes it back.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { placeLine } from "../src/assistantTurns.js";

const src = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");
const line = (id, key, extra = {}) => ({ id, role: "assistant", text: id, card: key ? { key, kind: "asked" } : null, ...extra });

// the road as landed and unshow run it, on the chat alone: an `ahead` line appended, then filled in place, replaced or taken down
const draw = (m, l) => [...m, { ...l, ahead: true }];
const fill = (m, ahead, l) => placeLine(m.filter((x) => x.id !== ahead.id), { ...l, id: l.card?.key === ahead.card?.key ? ahead.id : l.id });
const takeBack = (m, ahead) => m.filter((x) => x.id !== ahead.id);

test("a line drawn ahead and filled, replaced or taken back leaves what the answer placed alone leaves", () => {
  const chats = [[], [line("a1", "k1"), line("a2", "k2")], [line("a1", "k1"), line("u", null), line("a3", "k3")]];
  for (const before of chats) for (const key of ["k1", "k2", "k9"]) {
    const ahead = line("p", key), drawn = draw(before, ahead);
    assert.deepEqual(takeBack(drawn, ahead), before, "a failure leaves the chat as it was");
    for (const ans of ["k2", key]) {
      const alone = placeLine(before, line("c", ans)), filled = fill(drawn, ahead, line("c", ans));
      // the same item keeps the drawn line's id (its view stays mounted); otherwise exactly what placing the answer alone gives
      const strip = (m) => m.map(({ id, alias, ...x }) => ({ ...x, alias: (alias || []).filter((v) => v !== "p" && v !== "c") }));
      assert.deepEqual(strip(filled), strip(alone));
      assert.equal(filled.at(-1).id, ans === key ? "p" : "c");
    }
  }
});

test("the press draws the prepared answer only for the selection it was prepared for, else the rail's row, on one road", () => {
  const surface = src.slice(src.indexOf("const surface = useCallback"), src.indexOf("useEffect(() => { surfaceRef.current = surface; }"));
  assert.match(surface, /preparedRef\.current\?\.selection_revision === capture\.selection_revision/);
  assert.match(surface, /else if \(prep\) aheadRef\.current = drawAhead\(\{ \.\.\.line, text: prep\.answer\.say[^;]*\}, prep\.answer_hash\);/);
  assert.match(surface, /const drawsNow = \(c\) => !!c && showsTask\(c, cardFor\(c\)\) && !!heldTask\(c\.tid\) && heldTerm\(c\.tid\) !== undefined;/);
  assert.match(surface, /else if \(aheadItem && \(drawsNow\(aheadItem\) \|\| \(key && showsTask\(aheadItem, cardFor\(aheadItem\)\)\)\)\)\s+aheadRef\.current = drawAhead\(/);
  assert.match(surface, /const aheadKey = prep \? null : /, "one line ahead, never two");
  assert.match(surface, /\} catch \(e\) \{\s+unshow\(aheadRef\.current\); aheadRef\.current = null;/);
  const landed = src.slice(src.indexOf("const landed = useCallback"), src.indexOf("const ensureNextSelection = useCallback"));
  assert.match(landed, /ahead\.hash === data\.answer_hash && !extra/);
  assert.match(landed, /const id = keep \? ahead\.id : `a\$\{Date\.now\(\)\}`;/, "the same id: the view stays mounted");
  // every rail the page holds brings its prepared answer, and only that rail's
  assert.match(src, /preparedRef\.current = data\.prepared_next \|\| null;\s*setPile/);
  assert.match(src, /selectionRef\.current = captured; preparedRef\.current = data\.prepared_next \|\| null;/);
});

test("a line drawn ahead asks the Advisor nothing, and holds a card that would write, until its press has answered (PW-118)", () => {
  // the Advisor reads the rail; asked at the press, it rebuilt the rail between the press's admission and its commit check, and
  // the press was refused as stale. The read is held for the key drawn ahead - on either road - and made once the answer lands.
  const read = src.slice(src.indexOf("const readAdvice = useCallback"), src.indexOf("useEffect(() => { readAdvice(onTable)"));
  assert.match(read, /if \(unconfirmedRef\.current === key\) \{ adviceHeld\.current = key; return; \}/);
  const draw = src.slice(src.indexOf("const drawAhead = useCallback"), src.indexOf("const landed = useCallback"));
  assert.ok(draw.indexOf("unconfirmedRef.current = line.card?.key") < draw.indexOf("putOnTable(line.card)"), "held before the table changes");
  assert.match(draw, /const unshow[^]*unconfirmedRef\.current = null; adviceHeld\.current = null;/);
  const landed = src.slice(src.indexOf("const landed = useCallback"), src.indexOf("const ensureNextSelection = useCallback"));
  assert.match(landed, /if \(heldAdvice\) readAdvice\(card\?\.key \|\| heldAdvice\);/);
  // ...and a prepared card whose task was never read is drawn once the answer has landed: its first read files the task's origin.
  // One whose read is held (prefetchTask) had that read already, and draws at once, as the rail's row does
  const surface = src.slice(src.indexOf("const surface = useCallback"), src.indexOf("useEffect(() => { surfaceRef.current = surface; }"));
  assert.match(surface, /\.\.\.\(drawsNow\(prep\.answer\.item\) \? \{\} : \{ held: true \}\)/);
  assert.match(src, /function Line\(\{[^\n]*\n[^]*?if \(m\.held\) m = \{ \.\.\.m, card: null \};/);
  // the answer's line is a fresh object: `held` and `ahead` go with the line they were on
  assert.match(landed, /placeLine\(ahead \? m\.filter\(\(x\) => x\.id !== ahead\.id\) : m, \{ id, role: "assistant", text: data\.say/);
});

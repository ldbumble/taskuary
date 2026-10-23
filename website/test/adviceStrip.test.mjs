// THE ADVISOR'S STRIP AFTER AN ACT (2026-10-19): after Send the line still said the sender was waiting, with Reply lit; the row
// reshuffled when the advice landed; "Thinking about this one…" went to nothing. These pin the contract: every press re-reads the
// advice, the advice only tints the row, and every reason for no line is a sentence that lights one move.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { acted, advisedAny, advisedIn, clustersOf, onPressed, press, put, rowOf } from "../src/actionRow.js";
import { ADVICE_NONE, adviceNone } from "../src/words.js";

const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
const read = (n) => fs.readFileSync(path.join(process.cwd(), "src", n), "utf8");
const layout = (r) => clustersOf(r).map((g) => [g.type, g.shown.map((x) => x.id), g.rest.map((x) => x.id)]);

test("a press is heard once it settles, so the advice is read again for the item as the act left it", async () => {
  const heard = [];
  const off = onPressed((id) => heard.push(id));
  let done;
  put("t", [{ ...v("send", "decide"), run: () => new Promise((r) => { done = r; }) }]);
  press("send");
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(heard, [], "not before the act has finished");
  done(); await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(heard, ["send"]);
  acted("12:approve"); assert.deepEqual(heard, ["send", "12:approve"], "a card's own button says so the same way");
  off(); put("t", null);
  // ...and the page and a phone's row both listen, as does the draft's own Send under the card
  assert.match(read("AssistantView.jsx"), /onPressed\(\(\) => \{ if \(onTableRef\.current\) readAdvice\(onTableRef\.current, true\); \}\)/);
  assert.match(read("CanvasItem.jsx"), /onPressed\(\(\) => read\(\)\)/);
  assert.equal((read("ReviewDecision.jsx").match(/finally \{ acted\(no\(/g) || []).length, 4, "decide, decideBoth, redraft and copy");
});

test("the advice only tints: the same buttons in the same places with and without it, whatever it picks", () => {
  const list = [v("reply", "decide", { label: "Reply" }), v("share", "decide", { label: "Send out results" }), v("attach", "more", { label: "Attach a file" }),
    v("12:approve", "decide", { label: "Send", card: true, tone: "p" }), v("start-agent", "agent"), v("done", "more", { label: "Mark done" }),
    v("close-note", "more"), v("nat", "more"), v("remind", "more", { label: "Remind me" }), v("next", "next")];
  const plain = layout(rowOf({ ref: "", list }));
  for (const pick of [{ verb: "approve", label: "Send" }, { verb: "reply", label: "Reply" }, { verb: "close", label: "Mark done" }, { verb: "next" }])
    assert.deepEqual(layout(rowOf({ ref: "", list }, pick)), plain, pick.verb);
  assert.equal(layout(rowOf({ ref: "", list })).find(([t]) => t === "reply")[1][0], "slot:12:approve", "the card's own Send keeps an empty slot from the first render - its button is under the draft (2026-10-22)");
});

// THE OBVIOUS MOVE IS SILENT (the owner, 2026-10-23: "No suggestion...", "Nothing to decide...", "Thinking..." and every sentence
// explaining a silence go): only no AI is said, with its way out; any other reason lights Next and says nothing
test("no line is still an answer: only no AI is a sentence, and every other silence lights Next - never nothing", () => {
  assert.deepEqual(Object.keys(ADVICE_NONE), ["no_ai"]);
  assert.equal(ADVICE_NONE.no_ai.move, "ai");
  for (const why of ["nothing", "quiet", "working", "off", "cap", "some-new-reason"]) assert.deepEqual(adviceNone(why), { line: "", move: "next" }, why);
  const r = rowOf({ ref: "", list: [v("done", "more"), v("next", "next")] }, { verb: adviceNone("nothing").move });
  assert.equal(r.next.tone, "p");
  assert.equal(rowOf({ ref: "", list: [v("next", "next", { disabled: true })] }, { verb: "next" }).next.tone, "s", "a greyed Next is never lit");
  const view = read("AssistantView.jsx");
  assert.doesNotMatch(view, /AdviceNone|Thinking about this one/);
  assert.doesNotMatch(read("ActionRow.jsx"), /export function AdviceNone/);
  // ...in one strip that holds its height from Thinking to the answer, so the row under it never jumps
  assert.match(view, /<div className="tq-strip" data-tq-strip=\{busy( \|\| \(reading && reading === onTable\))? \? "busy" : ""\}>/);
  // ...and the dead-end walk holds the page to all of it (STILL, STRIP, REREAD, LIT)
  const walk = fs.readFileSync(path.join(process.cwd(), "deadend_check.mjs"), "utf8");
  for (const rule of ["STILL", "STRIP", "REREAD", "LIT"]) assert.ok(walk.includes(`note("${rule}"`), rule);
  assert.match(read("assistantView.css"), /\.tq-dock \.tq-strip \{ min-height: 40px;/);
});

// THE ADVISOR MATRIX (2026-10-19): every moment the Advisor speaks must match the screen. Two it caught: the draft's text cleared, Send
// greyed, and the strip went blank with nothing lit; after a refused send the lit Redraft stood a scroll below the card's edge.
test("an advised move the row has greyed says why it is off, and a move lit on the card is brought into view", () => {
  const list = [v("12:approve", "decide", { label: "Send", card: true, tone: "p", disabled: true, why: "write the reply first" }), v("next", "next")];
  const pick = { verb: "approve", label: "Send" };
  assert.equal(advisedIn(list, pick), null, "a greyed button is never lit");
  assert.equal(advisedAny(list, pick)?.why, "write the reply first", "...but the row still has it, and says why it is off");
  const src = read("ActionRow.jsx");
  assert.match(src, /const off = advisedAny\(theirs, advice\);\s*if \(!off\?\.disabled\) return null;/);
  assert.match(src, /data-tq-advice="off"[\s\S]{0,120}\$\{off\.label\} is off - \$\{off\.why/);
  // ...and held clear of what stands over it (inView.js), marked so the conversation's pin keeps it clear too (the phone pass, 2026-10-20)
  const rd = read("ReviewDecision.jsx");
  assert.match(rd, /if \(!lit\.startsWith\(`\$\{r\.ReviewId\}:`\)\) return undefined;\s*const el = movesRef\.current\?\.querySelector\("\.MuiButton-contained"\);/);
  assert.match(rd, /el\?\.setAttribute\("data-tq-lit", ""\);\s*const stop = holdInView\(el\);/);
  assert.match(read("AssistantView.jsx"), /el\.querySelector\("\[data-tq-lit\]"\)[\s\S]{0,200}floorOf\(body, el\)/);
});

// THE MATRIX'S VERIFY (2026-10-20): a chat's Mark done copies the draft - with the box emptied the line still said "copy it to where the
// question came from"; the move stays the advised one, and says what it does now (`blank`)
test("a move whose text is gone says what it does now, still lit", () => {
  const list = [v("12:approve", "decide", { label: "Mark done", card: true, tone: "p", blank: "The draft box is empty - Mark done closes it with nothing copied" }), v("next", "next")];
  assert.equal(advisedIn(list, { verb: "close", label: "Mark done" })?.id, "12:approve", "still the advised move");
  assert.match(read("actionRow.js"), /\.\.\.\(v\.blank \? \{ blank: v\.blank \} : \{\}\)/, "the row carries it to the strip");
  assert.match(read("ActionRow.jsx"), /if \(onRow\.blank\) return <div className="tq-next" role="status" data-tq-advice=""><div className="tq-next-txt">\{`\$\{onRow\.blank\}\.`\}/);
});

// THE ROW IS ONE LINE AT EVERY WIDTH (the owner, 2026-10-23: "even on my desktop i saw a time where the buttons turned into 2 rows.
// make sure that never happens ... it was when after closing agent and it was drafting a whatsapp response"). Every row state the app
// can produce, at seven widths: the layout fitRow picks fits its width, Next and the lit (or leading) move stay in view, and every other
// verb is one press away in a ▾ - once. The browser test (browser/row-one-line.test.mjs) checks the drawn row the same way.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { fitRow, foldsOf, leadOf, phoneRow, rowOf, rowWidth } from "../src/actionRow.js";
import { barFolds } from "../src/foldBar.js";
import { labelOfRow } from "../src/buttons.js";

const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: labelOfRow(id) || id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
const next = v("next", "next", { label: "Next" });
const task = (live = false) => [v("done", "more", { promote: !live, beside: live }), v("nat", "more"), v("remind", "more"), v("hand", "more"), v("reshape", "more"),
  v("kind", "more"), v("priority", "more"), v("assign", "more")];
const draft = (rid, extra = {}) => [v(`${rid}:approve`, "decide", { tone: "p", label: "Send", card: true, ...extra }), v(`${rid}:redraft`, "decide", { label: "Redraft", card: true })];

// what each surface registers, read off TaskPage's rowVerbs, ReviewDecision and the cards (invented items; labels from buttons.json)
const STATES = {
  "new task": [v("reply", "decide", { tone: "p" }), v("start-agent", "agent", { lead: true }), v("email", "agent"), v("close-note", "more"), ...task(), next],
  "reply drafted, sendable": [...draft(41), v("start-agent", "agent"), v("email", "agent"), v("close-note", "more"),
    ...task().map((x) => (x.id === "done" ? { ...x, promote: false, onCard: true } : x)), next],
  "reply drafted, unsendable chat": [v("41:copy", "decide", { label: "Copy", card: true }), v("41:redraft", "decide", { label: "Redraft", card: true }),
    v("start-agent", "agent"), v("close-note", "more"), ...task(), next],
  drafting: [v("reply", "decide", { tone: "p", label: "Drafting…", disabled: true }), v("start-agent", "agent", { lead: true }), v("email", "agent"), ...task(), next],
  "agent working": [v("save-end", "agent", { lead: true, fill: true }), v("diff", "agent"), v("run-another", "agent"), ...task(true), next],
  "agent asking": [v("save-end", "agent", { lead: true }), v("diff", "agent"), v("run-another", "agent"), ...task(true), next],
  "agent stopped and saved": [v("continue", "agent", { lead: true }), v("run-another", "agent"), v("email", "agent"), v("close-note", "more"), ...task(), next],
  "agent failed": [v("fix", "decide", { tone: "p", label: "Connect Claude again" }), v("continue", "agent", { label: "Try again" }), v("run-another", "agent"), v("email", "agent"), ...task(), next],
  "agent finished": [v("continue", "agent", { lead: true }), v("run-another", "agent"), v("email", "agent"), v("close-note", "more"), ...task(), next],
  // THE OWNER'S CASE: the agent stopped and saved on a WhatsApp task while its reply drafted - the chat's draft cannot be sent from
  // here (Copy, and "Drafting…" on its Redraft), the session's Continue / Run another agent, the reply's own Reply, Close and Task
  "stopped while drafting a WhatsApp reply": [v("reply", "decide", { tone: "p", label: "Drafting…", disabled: true }), v("41:copy", "decide", { label: "Copy", card: true, disabled: true }),
    v("41:redraft", "decide", { label: "Drafting…", card: true, disabled: true }), v("continue", "agent", { lead: true }), v("run-another", "agent"),
    v("close-note", "more"), ...task(), next],
  report: [v("r:open", "decide", { label: "Open the report" }), v("r:task", "decide", { label: "Make it a task" }), v("r:notreport", "decide", { label: "Not a report" }), next],
  dashboard: [v("d:refresh", "decide", { label: "Refresh" }), v("d:open", "decide", { label: "Open the dashboard" }), v("d:share", "decide", { label: "Share" }), next],
  "FYI batch": [v("f:read", "decide", { label: "Mark all read" }), v("f:each", "decide", { label: "Open each one" }), v("f:task", "decide", { label: "Make a task" }), next],
  invite: [v("accept_invite", "decide", { label: "Accept" }), v("decline_invite", "decide", { label: "Decline" }), v("propose_time", "decide", { label: "Propose a new time" }),
    v("start-agent", "agent", { lead: true }), v("email", "agent"), ...task(), next],
  goal: [v("start-agent", "agent", { lead: true, label: "Start the next step" }), v("email", "agent"), v("close-note", "more"), ...task(), next],
  closed: [v("reopen", "decide"), next],
  "end of walk": [...[412, 418, 433, 451].map((n) => v(`open:${n}`, "decide", { label: `Open TQ-0${n} · Census sync fails when a site has no manager` })), next],
  "no AI": [v("fix", "decide", { tone: "p", label: "Connect an AI" }), v("start-agent", "agent", { disabled: true, why: "connect an AI first" }), ...task(), next],
};
const PICKS = { "new task": { verb: "reply", label: "Reply" }, "agent stopped and saved": { verb: "continue", label: "Continue" }, "stopped while drafting a WhatsApp reply": { verb: "defer", label: "Remind me" },
  invite: { verb: "accept_invite", label: "Accept" }, "no AI": null, goal: { verb: "close", label: "Mark done" } };

// THE ROW'S CSS AS NUMBERS (assistantView.css): IBM Plex Sans 600 12.5px - 7.3px a character, generously; 14px sides and a 78px floor
// from 1100px, 11px and none under it; a group pads 5px, 5px after its label and between its pills, 10px between groups (6px narrow)
const WIDTHS = [1920, 1440, 1280, 1024, 800, 600, 390];
const model = (vw, row) => {
  const wide = vw >= 1100, text = (s) => Math.ceil(String(s).length * 7.3);
  const btn = Object.fromEntries([...row.decide, ...row.agent, ...row.more].map((x) => [x.id, Math.max(wide ? 78 : 0, text(x.label) + (wide ? 28 : 22) + 2)]));
  return { btn, label: { reply: 53, agent: 53, close: 53, task: 53 }, more: 30, next: text(row.next?.label || "") + 18 + 24 + 2, pad: 10, clGap: 5, bGap: 5, rowGap: wide ? 10 : 6 };
};
// the row's own box: the canvas beside a rail on a desktop, the whole view on a phone (minus the dock's 12px sides)
const avail = (vw) => (vw <= 600 ? vw - 24 : vw >= 1100 ? Math.min(vw - 360, 1400) : vw - 300);

for (const [name, list] of Object.entries(STATES)) {
  test(`one line at every width: ${name}`, () => {
    const row = rowOf({ ref: "TQ-1", list }, PICKS[name] ?? null), ids = (xs) => xs.filter((x) => !x.slot).map((x) => x.id).sort();
    const every = ids([...row.decide, ...row.agent, ...row.more]), held = leadOf(row, false), pressable = leadOf(row);
    for (const vw of WIDTHS) {
      // ...the lead the folds keep in view, and on a phone its one move, never a greyed one (2026-10-28)
      const m = model(vw, row), fit = fitRow(row, m, avail(vw), vw <= 600), lead = vw <= 600 ? pressable : held;
      // ...only a move whose own label is longer than the box (the walk's end "Open TQ-... · <title>") is shortened, with an ellipsis -
      // still one line, still in view, its whole label on its hover
      // ...or a lit move too long to stand beside Mark done (a failed run's "Connect Claude again" on a phone)
      const pinW = lead && lead.id !== "done" && every.includes("done") ? m.btn.done + m.bGap : 0;
      if (fit.tight) assert.ok(lead && (lead.label.length > 40 || pinW) && m.btn[lead.id] + pinW + m.next + 2 * m.pad + m.more > avail(vw) - 3 * m.rowGap,
        `${name} @${vw}: squeezed though it fits`);
      else assert.ok(rowWidth(fit.groups, row.next, m) <= avail(vw), `${name} @${vw}: ${rowWidth(fit.groups, row.next, m)}px in ${avail(vw)}px`);
      assert.ok(row.next, "Next is on the row"); assert.ok(!fit.groups.some((g) => [...g.shown, ...g.rest].some((x) => x.group === "next")), "Next never folds");
      const shown = fit.groups.flatMap((g) => g.shown), menus = fit.groups.flatMap((g) => g.rest);
      if (lead) assert.ok(shown.includes(lead), `${name} @${vw}: the lit or leading move "${lead.label}" stays in view`);
      const lit = [...row.decide, ...row.agent, ...row.more].find((x) => x.tone === "p");
      if (lit) assert.ok(shown.includes(lit), `${name} @${vw}: the one filled button is never folded`);
      assert.deepEqual(ids([...shown, ...menus]), every, `${name} @${vw}: every verb is reachable, once`);
      if (fit.groups.at(-1)?.type === "more") assert.equal(fit.groups.at(-2)?.rest.length || 0, 0, `${name} @${vw}: one ▾ at the row's end, never two side by side`);
      // ...Mark done never folds (the owner, 2026-10-28: "You should not have Mark done ever hidden")
      const done = every.includes("done") && [...row.decide, ...row.agent, ...row.more].find((x) => x.id === "done");
      if (done) assert.ok(shown.includes(done), `${name} @${vw}: Mark done is in view`);
      // ...the Change pill gives up its moves before the move pill does (all but a lit one)
      const mv = fit.groups.find((g) => g.type === "move"), ch = fit.groups.find((g) => g.type === "change");
      if (mv?.rest.length && ch) assert.ok(ch.shown.every((x) => x.tone === "p"), `${name} @${vw}: a move folded while Change kept ${ch.shown.map((x) => x.label)}`);
      if (vw <= 600) assert.ok(fit.groups.length <= 1, `${name} @${vw}: a phone is Next, its moves and one ▾`);
    }
  });
}

// THE ROW IN THREE (the owner, 2026-10-28): Nav, the moves that finish or advance the item in one pill, the moves that change the task in another
test("three pills: Mark done, the agent's move and the reply's lead the move pill; Change holds the task's shape", () => {
  const row = rowOf({ ref: "TQ-1", list: STATES["new task"] }, PICKS["new task"]), all = foldsOf(row);
  assert.deepEqual(all[0].map((g) => [g.type, g.label]), [["move", ""], ["change", "Change"]], "no REPLY / AGENT / CLOSE words");
  assert.deepEqual(all[0][0].shown.slice(0, 3).map((x) => x.id), ["done", "start-agent", "reply"]);
  assert.deepEqual(all[0][1].shown.map((x) => x.id).slice(0, 3), ["remind", "reshape", "nat"], "Remind me first");
  // ...folding: Change first, to its ▾ alone, then the move pill from its end, then one ▾ for both
  const shape = (l) => l.map((g) => `${g.type}:${g.shown.length}+${g.rest.length}`).join(" ");
  const ch = all.findIndex((l) => l.find((g) => g.type === "change")?.shown.length === 0);
  assert.ok(ch > 0 && all.slice(0, ch).every((l) => !l[0].rest.length), `the move pill folds nothing while Change has moves in view: ${all.map(shape)}`);
  assert.equal(all.at(-1).length, 1, "the narrowest is one pill and one ▾");
  assert.deepEqual(all.at(-1)[0].shown.map((x) => x.id), ["done", "reply"], "Mark done and the lit Reply");
  assert.deepEqual(all.at(-1), [phoneRow(row)]);
});

test("the owner's case folds instead of wrapping on a desktop: Change first, every move reachable", () => {
  const row = rowOf({ ref: "TQ-1", list: STATES["stopped while drafting a WhatsApp reply"] }), all = foldsOf(row);
  const m = model(1024, row), w0 = rowWidth(all[0], row.next, m);
  assert.ok(w0 > avail(1024), `every move needs ${w0}px - the width that wrapped`);
  const fit = fitRow(row, m, avail(1024));
  assert.ok(fit.level > 0);
  assert.ok(fit.groups.find((g) => g.type === "change")?.shown.length === 0, "Change is its ▾");
  assert.equal(fitRow(row, m, 5000).level, 0, "with room, nothing folds");
});

// THE OWNER'S BUG (0.3.9.58): the reply went, and the row lit Reply with Hand it to a person beside it and Mark done behind the ▾
test("a sent reply: Mark done lit and in view at every width, Reply unlit beside it, Hand it to a person behind the ▾", () => {
  const list = [v("reply", "decide"), v("close-note", "more"), ...task().map((x) => (x.id === "hand" ? { ...x, tucked: true } : x)), v("run-another", "agent"), next];
  const row = rowOf({ ref: "TQ-1", list }, { verb: "close", label: "Mark done" });
  assert.equal([...row.decide, ...row.agent, ...row.more].find((x) => x.tone === "p")?.id, "done");
  for (const vw of [...WIDTHS, 1366]) {
    const fit = fitRow(row, model(vw, row), avail(vw), vw <= 600), shown = fit.groups.flatMap((g) => g.shown);
    assert.ok(shown.some((x) => x.id === "done" && x.tone === "p"), `@${vw}: Mark done lit, in view`);
    assert.ok(!shown.some((x) => x.id === "reply" && x.tone === "p"), `@${vw}: Reply is not lit`);
    assert.ok(!shown.some((x) => x.id === "hand"), `@${vw}: Hand it to a person waits in the ▾`);
    assert.ok(fit.groups.some((g) => g.rest.some((x) => x.id === "hand")));
  }
  assert.ok(foldsOf(row)[0][0].shown.some((x) => x.id === "reply"), "with room, Reply stands beside Mark done");
});

test("Mark done never folds, at any width, even with no room at all", () => {
  for (const [name, list] of Object.entries(STATES)) {
    const row = rowOf({ ref: "TQ-1", list }, PICKS[name] ?? null), done = [...row.decide, ...row.agent, ...row.more].find((x) => x.id === "done");
    if (!done) continue;
    for (const lvl of foldsOf(row)) assert.ok(lvl.some((g) => g.shown.includes(done)), `${name}: a layout hid Mark done`);
    for (const w of [390, 1366, 40]) assert.ok(fitRow(row, model(w, row), w === 40 ? 40 : avail(w), w <= 600).groups.some((g) => g.shown.includes(done)), `${name} @${w}`);
  }
});

test("the lit move in the Change pill stands while the others fold, and the phone keeps it", () => {
  const row = rowOf({ ref: "TQ-1", list: STATES["new task"] }, { verb: "defer", label: "Remind me" });
  const all = foldsOf(row), lit = [...row.decide, ...row.agent, ...row.more].find((x) => x.tone === "p");
  assert.equal(lit.id, "remind");
  all.forEach((l) => assert.ok(l.some((g) => g.shown.includes(lit)), "the lit Remind me stays in view"));
  assert.deepEqual(all.at(-1)[0].shown.map((x) => x.id), ["done", "remind"]);
});

test("nothing measured is the widest layout; a phone starts at its one-▾ layouts; an overflow the parts missed steps one fold further", () => {
  const row = rowOf({ ref: "", list: STATES["agent finished"] }), all = foldsOf(row);
  assert.equal(fitRow(row, null, 0).level, 0);
  assert.equal(fitRow(row, null, 0, true).level, all.phone);
  assert.ok(all.slice(all.phone).every((l) => l.length === 1), "one pill, one ▾");
  assert.equal(fitRow(row, model(1920, row), 5000, false, 1).level, 1);
  assert.equal(fitRow(row, model(1920, row), 5000, false, 99).level, all.length - 1, "never past the narrowest");
  // ...too narrow for even that: an unlit move goes into the ▾ (a squeezed label read as a stray letter, the 2026-10-27 sweep) - Mark done stays
  assert.deepEqual(fitRow(row, model(390, row), 40).groups.map((g) => [g.type, g.shown.map((x) => x.id)]), [["move", ["done"]]]);
  const none = rowOf({ ref: "", list: [v("continue", "agent", { lead: true }), v("run-another", "agent"), v("nat", "more"), next] });
  assert.deepEqual(fitRow(none, model(390, none), 40).groups.map((g) => [g.type, g.shown.length]), [["more", 0]]);
});

test("a draft's Send leaves no empty slot, on the bar or the phone's row (2026-10-25)", () => {
  const row = rowOf({ ref: "", list: [...draft(7), v("remind", "more"), next] });
  assert.ok(!row.decide.some((x) => x.slot));
  const ph = phoneRow(row);
  assert.ok(![...ph.shown, ...ph.rest].some((x) => x.slot));
  assert.deepEqual(ph.shown, [], "no decision, no session verb: Next and the ▾");
  assert.deepEqual(ph.rest.map((x) => x.id), ["remind"]);
});

// NEVER A GREYED ONE MOVE (the owner, 2026-10-28): a phone's row showed a disabled "Send to agent" as its only move
test("a phone's one move is never a disabled one: the next pressable move, else the ▾ alone", () => {
  const row = rowOf({ ref: "", list: [v("41:copy", "decide", { label: "Copy", card: true, disabled: true }), v("start-agent", "agent", { disabled: true, why: "connect an AI" }),
    v("continue", "agent"), next] });
  assert.deepEqual(phoneRow(row).shown.map((x) => x.id), ["continue"]);
  const none = rowOf({ ref: "", list: [v("start-agent", "agent", { disabled: true }), v("nat", "more"), next] }), ph = phoneRow(none);
  assert.deepEqual(ph.shown, []);
  assert.ok(ph.rest.some((x) => x.id === "start-agent"), "the greyed move is still in the ▾, its why on hover");
});

// NAV HOLDS THE ROW'S START (the owner, 2026-10-28): centred with the rest, Next moved between items; the types centre in what is left
test("Nav is pinned at the row's start and the rest centres in the room left", () => {
  const css = fs.readFileSync(new URL("../src/assistantView.css", import.meta.url), "utf8");
  assert.match(css, /^\.tq-arow-verbs > \.tq-cl-next \{ margin-right: auto; \}$/m);
  assert.match(css, /^\.tq-arow-verbs > \.tq-cl-next ~ \.tq-cl:last-child \{ margin-right: auto; \}$/m);
});

test("the CSS never wraps the row or a group, and a label never breaks inside its pill", () => {
  const css = fs.readFileSync(new URL("../src/assistantView.css", import.meta.url), "utf8");
  const rule = (sel) => css.match(new RegExp(`^${sel.replace(/\./g, "\\.")} \\{([^}]*)\\}`, "m"))?.[1] || "";
  assert.match(rule(".tq-arow-verbs"), /flex-wrap: nowrap/); assert.doesNotMatch(rule(".tq-arow-verbs"), /flex-wrap: wrap/);
  assert.match(rule(".tq-cl-b"), /flex-wrap: nowrap/);
  assert.match(rule(".tq-ab"), /white-space: nowrap/); assert.match(rule(".tq-cl-b .tq-ab"), /white-space: nowrap;/);
  assert.match(rule(".tq-arow-verbs > .tq-cl"), /flex: 0 0 auto/, "a group keeps its width, so an overflow folds instead of squeezing");
  const row = fs.readFileSync(new URL("../src/ActionRow.jsx", import.meta.url), "utf8");
  assert.match(row, /const fit = fitRow\(row, m, avail, phone, extra\);/);
  assert.match(row, /new ResizeObserver\(f\)/, "a resize re-fits the row");
  assert.match(row, /\{fit\.groups\.map\(\(g\) => <Cluster key=\{g\.type\} g=\{g\} btn=\{btn\} act=\{act\} \/>\)\}/);
});

// ...A MOVE SQUEEZED TO A LETTER FOLDS (the 2026-10-27 sweep): a phone's report put Back, Next and the chat pill beside "Put it on my list",
// and the row drew "Pu". With too little room for its words the move joins the ▾ - unless it is the lit one; with room it is shortened
test("on a phone, an unlit move with no room for its words goes into the ▾; a lit one, or one with room, is shortened instead", () => {
  const list = [v("r:task", "decide", { label: "Put it on my list" }), v("r:agent", "agent", { label: "Send to agent" }), v("r:pause", "more", { label: "Pause this report" }), next];
  const row = rowOf({ ref: "", list }), m = model(390, row), tiny = m.next + m.btn["r:task"] / 4;
  const fit = fitRow(row, m, tiny, true);
  assert.deepEqual(fit.groups.map((g) => [g.type, g.shown.length]), [["more", 0]], "Nav and one ▾");
  assert.deepEqual(fit.groups[0].rest.map((x) => x.id).sort(), ["r:agent", "r:pause", "r:task"], "every verb one press away, once");
  assert.ok(!fit.tight);
  const lit = { ...row, decide: row.decide.map((x) => (x.id === "r:task" ? { ...x, tone: "p" } : x)) };
  const kept = fitRow(lit, m, tiny, true);
  assert.equal(kept.tight, true, "the lit move stays, shortened");
  assert.deepEqual(kept.groups[0].shown.map((x) => x.id), ["r:task"]);
  const roomy = fitRow(row, m, rowWidth(foldsOf(row).at(-1), row.next, m) - 20, true);
  assert.equal(roomy.tight, true, "room for most of its words: shortened, still on the row");
  assert.deepEqual(roomy.groups[0].shown.map((x) => x.id), ["r:task"]);
});

test("the Tasks tab's bar folds the same way: Change first, Mark done and Remind me never", () => {
  const items = [{ id: "#0", w: 120, rank: 0 }, { id: "nat", w: 160, rank: 4 }, { id: "#2", w: 110, rank: 0 }, { id: "sep", w: 8, rank: 3 },
    { id: "hand", w: 170, rank: 3 }, { id: "reshape", w: 130, rank: 2 }, { id: "change", w: 100, rank: 1 }];
  assert.deepEqual(barFolds(items, 2000, 6, 34), []);
  assert.deepEqual(barFolds(items, 780, 6, 34), ["change"]);
  assert.deepEqual(barFolds(items, 640, 6, 34), ["reshape", "change"]);
  assert.deepEqual(barFolds(items, 450, 6, 34), ["sep", "hand", "reshape", "change"]);
  assert.deepEqual(barFolds(items, 200, 6, 34), ["nat", "sep", "hand", "reshape", "change"], "never Mark done or Remind me");
  const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /<Box data-tq-task-bar="" ref=\{bar\.ref\} sx=\{\{ display: "flex", alignItems: "center", gap: 0\.8, flexWrap: "nowrap"/);
});

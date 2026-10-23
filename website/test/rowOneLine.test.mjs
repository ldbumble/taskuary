// THE ROW IS ONE LINE AT EVERY WIDTH (the owner, 2026-10-23: "even on my desktop i saw a time where the buttons turned into 2 rows.
// make sure that never happens ... it was when after closing agent and it was drafting a whatsapp response"). Every row state the app
// can produce, at seven widths: the layout fitRow picks fits its width, Next and the lit (or leading) move stay in view, and every other
// verb is one press away in a ▾ - once. The browser test (browser/row-one-line.test.mjs) checks the drawn row the same way.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { fitRow, foldsOf, phoneRow, rowOf, rowWidth } from "../src/actionRow.js";
import { barFolds } from "../src/foldBar.js";
import { labelOfRow } from "../src/buttons.js";

const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: labelOfRow(id) || id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
const next = v("next", "next", { label: "Next" });
const task = (live = false) => [v("done", "more", { promote: !live, beside: live }), v("nat", "more"), v("remind", "more"), v("hand", "more"), v("reshape", "more"),
  v("kind", "more"), v("priority", "more"), v("assign", "more")];
const draft = (rid, extra = {}) => [v(`${rid}:approve`, "decide", { tone: "p", label: "Send", card: true, ...extra }), v(`${rid}:redraft`, "decide", { label: "Redraft", card: true })];

// what each surface registers, read off TaskPage's rowVerbs, ReviewDecision and the cards (invented items; labels from buttons.json)
const STATES = {
  "new task": [v("reply", "decide", { tone: "p" }), v("start-agent", "agent", { lead: true }), v("email", "agent"), v("ask-sender", "more"), v("close-note", "more"), ...task(), next],
  "reply drafted, sendable": [...draft(41), v("start-agent", "agent"), v("email", "agent"), v("ask-sender", "more"), v("close-note", "more"),
    ...task().map((x) => (x.id === "done" ? { ...x, promote: false, onCard: true } : x)), next],
  "reply drafted, unsendable chat": [v("41:copy", "decide", { label: "Copy", card: true }), v("41:redraft", "decide", { label: "Redraft", card: true }),
    v("start-agent", "agent"), v("close-note", "more"), ...task(), next],
  drafting: [v("reply", "decide", { tone: "p", label: "Drafting…", disabled: true }), v("start-agent", "agent", { lead: true }), v("email", "agent"), v("ask-sender", "more"), ...task(), next],
  "agent working": [v("save-end", "agent", { lead: true, fill: true }), v("diff", "agent"), v("run-another", "agent"), ...task(true), next],
  "agent asking": [v("save-end", "agent", { lead: true }), v("diff", "agent"), v("run-another", "agent"), ...task(true), next],
  "agent stopped and saved": [v("continue", "agent", { lead: true }), v("run-another", "agent"), v("email", "agent"), v("close-note", "more"), ...task(), next],
  "agent failed": [v("fix", "decide", { tone: "p", label: "Connect Claude again" }), v("continue", "agent", { label: "Try again" }), v("run-another", "agent"), v("email", "agent"), ...task(), next],
  "agent finished": [v("continue", "agent", { lead: true }), v("run-another", "agent"), v("email", "agent"), v("ask-sender", "more"), v("close-note", "more"), ...task(), next],
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
    const every = ids([...row.decide, ...row.agent, ...row.more]), lead = phoneRow(row).shown[0];
    for (const vw of WIDTHS) {
      const m = model(vw, row), fit = fitRow(row, m, avail(vw), vw <= 600);
      // ...only a move whose own label is longer than the box (the walk's end "Open TQ-... · <title>") is shortened, with an ellipsis -
      // still one line, still in view, its whole label on its hover
      if (fit.tight) assert.ok(lead && lead.label.length > 40 && m.btn[lead.id] + m.next + 2 * m.pad + m.more > avail(vw) - 3 * m.rowGap, `${name} @${vw}: squeezed though it fits`);
      else assert.ok(rowWidth(fit.groups, row.next, m) <= avail(vw), `${name} @${vw}: ${rowWidth(fit.groups, row.next, m)}px in ${avail(vw)}px`);
      assert.ok(row.next, "Next is on the row"); assert.ok(!fit.groups.some((g) => [...g.shown, ...g.rest].some((x) => x.group === "next")), "Next never folds");
      const shown = fit.groups.flatMap((g) => g.shown), menus = fit.groups.flatMap((g) => g.rest);
      if (lead) assert.ok(shown.includes(lead), `${name} @${vw}: the lit or leading move "${lead.label}" stays in view`);
      const lit = [...row.decide, ...row.agent, ...row.more].find((x) => x.tone === "p");
      if (lit) assert.ok(shown.includes(lit), `${name} @${vw}: the one filled button is never folded`);
      assert.deepEqual(ids([...shown, ...menus]), every, `${name} @${vw}: every verb is reachable, once`);
      if (fit.groups.at(-1)?.type === "more") assert.equal(fit.groups.at(-2)?.rest.length || 0, 0, `${name} @${vw}: one ▾ at the row's end, never two side by side`);
      if (vw <= 600) assert.equal(fit.groups.length <= 1 && (fit.groups[0]?.shown.length || 0) <= 1, true, `${name} @${vw}: a phone is Next, the one move and one ▾`);
    }
  });
}

test("the owner's case folded on a desktop instead of wrapping: five groups do not fit 1024, so Task and Close fold first", () => {
  const row = rowOf({ ref: "TQ-1", list: STATES["stopped while drafting a WhatsApp reply"] }), all = foldsOf(row);
  assert.deepEqual(all[0].map((g) => g.type), ["reply", "agent", "close", "task"]);
  assert.deepEqual(all[1].map((g) => g.type), ["reply", "agent", "close", "more"], "Task folds first");
  assert.deepEqual(all[2].map((g) => g.type), ["reply", "agent", "more"], "then Close");
  assert.deepEqual(all.at(-1), [phoneRow(row)], "the narrowest is the phone's");
  const m = model(1024, row), w0 = rowWidth(all[0], row.next, m);
  assert.ok(w0 > avail(1024), `the typed groups need ${w0}px - the width that wrapped`);
  assert.ok(fitRow(row, m, avail(1024)).level > 0);
  assert.equal(fitRow(row, m, 5000).level, 0, "with room, nothing folds");
});

test("a group beside the shared ▾ hands its own ▾'s buttons to it: one ▾, first in its menu", () => {
  const row = rowOf({ ref: "TQ-1", list: STATES["stopped while drafting a WhatsApp reply"] }), all = foldsOf(row), cs = all[0];
  all.slice(1, -1).forEach((l) => {
    const before = l.at(-2), was = cs.find((g) => g.type === before.type);
    assert.deepEqual(before.rest, [], `${before.type} keeps no ▾ of its own beside the shared one`);
    assert.deepEqual(l.at(-1).rest.slice(0, was.rest.length).map((x) => x.id), was.rest.map((x) => x.id), "its buttons lead the shared ▾");
  });
});

test("the group holding the lit move folds last, and the phone keeps that move", () => {
  const row = rowOf({ ref: "TQ-1", list: STATES["new task"] }, { verb: "defer", label: "Remind me" });
  const all = foldsOf(row), lit = row.more.find((x) => x.tone === "p") || [...row.decide, ...row.agent].find((x) => x.tone === "p");
  assert.equal(lit.id, "remind");
  all.slice(0, -1).forEach((l) => assert.ok(l.some((g) => g.type === "task" && g.shown.includes(lit)), "Task, holding the lit Remind me, stands while others fold"));
  assert.deepEqual(all.at(-1)[0].shown.map((x) => x.id), ["remind"]);
});

test("nothing measured is the widest layout; a phone starts at the phone's; an overflow the parts missed steps one fold further", () => {
  const row = rowOf({ ref: "", list: STATES["agent finished"] });
  assert.equal(fitRow(row, null, 0).level, 0);
  assert.equal(fitRow(row, null, 0, true).level, foldsOf(row).length - 1);
  assert.equal(fitRow(row, model(1920, row), 5000, false, 1).level, 1);
  assert.equal(fitRow(row, model(1920, row), 5000, false, 99).level, foldsOf(row).length - 1, "never past the phone's");
  assert.equal(fitRow(row, model(390, row), 40).tight, true, "too narrow for even that: the one move's label shortens, the line stays one");
});

test("an empty slot never becomes the phone's one move or a menu item", () => {
  const row = rowOf({ ref: "", list: [...draft(7), v("remind", "more"), next] });
  assert.equal(row.decide[0].slot, true);
  const ph = phoneRow(row);
  assert.ok(![...ph.shown, ...ph.rest].some((x) => x.slot));
  assert.deepEqual(ph.shown, [], "no decision, no session verb: Next and the ▾");
  assert.deepEqual(ph.rest.map((x) => x.id), ["remind"]);
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
  assert.match(row, /\{fit\.groups\.map\(\(g\) => <Cluster key=\{g\.type\} g=\{g\} btn=\{btn\} \/>\)\}/);
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

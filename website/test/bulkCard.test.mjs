import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { countOf, listCap, pressOf, progress, rowOf, rowOpens, rowState, running, tabsOf } from "../src/bulkCard.js";

// ONE CARD FOR A BULK JOB (taskuary/bulkcard.py; the owner, 2026-11-16). Invented people and a stand-in repository.
const mail = (id, to, extra = {}) => ({ ReviewId: id, Kind: "slot", Status: "pending", Batch: "b1", DraftText: "Hello - about Market St.",
  Deliver: JSON.stringify({ to: [to], subject: `Interest in ${id} Market St`, ...extra }) });
const close = (id) => ({ ReviewId: id, Kind: "action", Status: "pending", Batch: "b2", Reason: "the agent proposes to close it",
  DraftText: JSON.stringify({ action: "run_tool", type: "github_close", repo: "northwind/ledger", number: id, comment: "Stale - closing." }) });

test("a row says whom or what it goes to, its one line, and what to check", () => {
  assert.deepEqual(rowOf(mail(1, "owner1@cedar.example")), { id: 1, target: "owner1@cedar.example", line: "Interest in 1 Market St", flags: [] });
  assert.deepEqual(rowOf(mail(2, "owner2@cedar.example", { guessed: ["owner2@cedar.example"] })).flags, ["address guessed"]);
  assert.deepEqual(rowOf(close(7)), { id: 7, target: "northwind/ledger#7", line: "Stale - closing.", flags: [] });
});

test("the press says what it does, by the act's own words", () => {
  assert.equal(pressOf([mail(1, "a@cedar.example")], 24), "Send 24 emails");
  assert.equal(pressOf([close(1)], 37), "Close 37 issues");
  assert.equal(countOf([close(1), close(2)]), "2 issues"); assert.equal(countOf([mail(1, "a@cedar.example")]), "1 email");
  // ...and posts are posts to their network, by its name (the card gallery, 2026-11-25: six LinkedIn posts read "6 steps", each row "linkedin_post")
  const post = (id) => ({ ReviewId: id, Kind: "action", Status: "pending", Batch: "b3", Reason: "the post", DraftText: JSON.stringify({ action: "run_tool", type: "linkedin_post", text: `Tip ${id}: invoices in one place.` }) });
  assert.equal(countOf([post(1), post(2)]), "2 posts"); assert.equal(pressOf([post(1), post(2)], 2), "Post to LinkedIn - all 2");
  assert.deepEqual(rowOf(post(3)), { id: 3, target: "LinkedIn", line: "Tip 3: invoices in one place.", flags: [] });
});

test("each row stands where its run left it, and the bar counts what is over", () => {
  const run = { state: "running", total: 4, done: 1, failed: 1, left: 0, rows: { 1: "ok", 2: "issue was deleted" } };
  assert.deepEqual([1, 2, 3].map((id) => rowState(close(id), run)), [{ done: true }, { failed: "issue was deleted" }, { waiting: true }]);
  assert.equal(progress(run), 50); assert.ok(running(run)); assert.ok(!running({ state: "finished" }));
  assert.deepEqual(rowState({ ...close(4), Status: "superseded", DecideNote: "set aside when you moved on" }, null), { aside: true });
});

// A SEND THAT DID NOT GO STILL WAITS ON THE CARD (taskuary/bulkcard.summary): its row was drawn failed, with no tick box, and with every other
// row done the press was gone - the card stood in front of the line with nothing to press, the card behind it held for good.
test("a row whose send did not go still waits for the press, its error said beside it", () => {
  const run = { state: "finished", total: 3, done: 2, failed: 1, left: 0, rows: { 1: "ok", 2: "ok", 3: "mailbox refused: over quota" } };
  const rows = [{ ...mail(1, "a@cedar.example"), Status: "approved" }, { ...mail(2, "b@cedar.example"), Status: "approved" }, mail(3, "c@cedar.example")];
  assert.deepEqual(rows.map((r) => rowState(r, run)), [{ done: true }, { done: true }, { waiting: true, failed: "mailbox refused: over quota" }]);
  assert.deepEqual(rowState({ ...close(4), Status: "superseded", ActError: "issue was deleted" }, { rows: { 4: "issue was deleted" } }), { failed: "issue was deleted" },
    "an act that failed is off the card");
});

// THE CARD READS ITS RUN WHILE THE PAGE AROUND IT REDRAWS (2026-11-17: the bar read "0 of 25" until the run ended and Stop the rest stayed lit).
// Each row the run does pokes task-changed, the task page redraws and hands the card a fresh onChanged - and the poll, keyed on it, was torn
// down before its one second came. Rendered here with a stand-in React (hooks with their deps, no DOM) so the effect's deps are what is tested.
const R = (() => {
  let slots = [], at = 0, props = null, Comp = null, effects = [], tree = null;
  const same = (a, b) => !!a && !!b && a.length === b.length && a.every((x, i) => Object.is(x, b[i]));
  const slot = (make) => { const i = at++; if (!(i in slots)) slots[i] = make(); return slots[i]; };
  const draw = () => {
    at = 0; effects = []; tree = Comp(props);
    for (const e of effects) { e.s.undo?.(); e.s.undo = e.f(); }
  };
  const el = (type, p) => ({ type, props: p || {} });
  return {
    useState: (init) => { const s = slot(() => ({ v: typeof init === "function" ? init() : init }));
      return [s.v, (v) => { s.v = typeof v === "function" ? v(s.v) : v; queueMicrotask(draw); }]; },
    useRef: (v) => slot(() => ({ current: v })),
    useCallback: (f, deps) => { const s = slot(() => ({})); if (!same(s.deps, deps)) Object.assign(s, { f, deps }); return s.f; },
    useMemo: (f, deps) => { const s = slot(() => ({})); if (!same(s.deps, deps)) Object.assign(s, { v: f(), deps }); return s.v; },
    useEffect: (f, deps) => { const s = slot(() => ({})); if (!deps || !same(s.deps, deps)) { s.deps = deps; effects.push({ s, f }); } },
    jsx: el, jsxs: el, Fragment: "Fragment",
    render: (C, p) => { Comp = C; props = p; draw(); },
    root: () => tree,
    reset: () => { slots = []; },          // ...a test of its own: no hook state left by the one before
    // ...the one card's own words are its props (Artifact ReviewCard): its label, what stands over its rows, its press and what is beside it
    text: () => { const out = []; const walk = (n) => { if (n == null || typeof n === "boolean") return; if (Array.isArray(n)) return n.forEach(walk);
      if (typeof n !== "object") return void out.push(String(n));
      if (n.type === "ReviewCard") [n.props.label, n.props.before, (n.props.press || []).map((v) => v.label), n.props.tail].forEach(walk);
      walk(n.props.children); }; walk(tree); return out.join(" "); },
  };
})();

const build = async () => {
  const { build: esb } = await import("esbuild");
  const stub = { "react": "export const { useState, useRef, useCallback, useMemo, useEffect } = globalThis.__R; export default globalThis.__R;",
    "react/jsx-runtime": "export const { jsx, jsxs, Fragment } = globalThis.__R;",
    "@mui/material": "const C = (n) => n; export const Box = C('Box'), LinearProgress = C('LinearProgress'), Typography = C('Typography');",
    "./api": "export default globalThis.__api;", "./theme.jsx": "export const DIM = '', FAINT = '';",
    "./ReviewDecision.jsx": "export default 'ReviewDecision'; export const ActReview = 'ActReview';", "./Artifact.jsx": "export const ReviewCard = 'ReviewCard', CardLine = 'CardLine';",
    "./PassedCard.jsx": "export const MovedPast = ({ children }) => children;" };
  const out = await esb({ entryPoints: [fileURLToPath(new URL("../src/BulkCard.jsx", import.meta.url))], bundle: true, write: false, format: "esm",
    jsx: "automatic", logLevel: "silent", plugins: [{ name: "stubs", setup(b) {
      b.onResolve({ filter: /.*/ }, (a) => (a.path in stub ? { path: a.path, namespace: "stub" } : undefined));
      b.onLoad({ filter: /.*/, namespace: "stub" }, (a) => ({ contents: stub[a.path], loader: "js" })); } }] });
  return (await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString("base64")}`)).default;
};

test("the bar follows the run while every row it does redraws the page with a fresh onChanged", async (t) => {
  // ...node 22 takes {apis}; its array form mocks every timer, setImmediate too, and the flush below never resolves (node 20 takes the array)
  try { t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] }); } catch { t.mock.timers.enable(["setInterval", "setTimeout"]); }
  const flush = async () => { for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); };
  const rows = Array.from({ length: 25 }, (_, i) => mail(i + 1, `owner${i + 1}@cedar.example`));
  let reads = 0, run = { key: "b1", state: "running", total: 25, done: 0, failed: 0, left: 0, rows: {} };
  globalThis.__R = R;
  globalThis.__api = { get: async () => { reads += 1; run = { ...run, done: Math.min(run.done + 3, 25) }; return { data: run }; }, post: async () => ({ data: run }) };
  const BulkCard = await build();
  const page = () => R.render(BulkCard, { rows, tid: 7, onChanged: () => {} });     // the task page: a new arrow on every render
  page(); await flush();
  const first = reads;
  for (let ms = 0; ms < 3000; ms += 300) { t.mock.timers.tick(300); page(); await flush(); }
  assert.ok(reads >= first + 2, `read ${reads - first} more times in 3 s while the page redrew`);
  assert.doesNotMatch(R.text(), /\b3 of 25\b/, "the bar moved past its first read");
  assert.match(R.text(), /(\d+) of 25/);
});

// THE BAR COUNTS WHAT THE ROWS SHOW (recorded, browser/bulk-card-queue): every row stood ✓ while the bar still read "0 of 30 · 0 done" and
// Stop the rest stood lit - the rows come with the page's redraw on each row done, the bar only with its own poll a second later.
test("the bar is read again as the rows it counts change, never a second behind them", async () => {
  const flush = async () => { for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); };
  const rows = Array.from({ length: 3 }, (_, i) => mail(i + 1, `owner${i + 1}@cedar.example`));
  let reads = 0, run = { key: "b1", state: "running", total: 3, done: 0, failed: 0, left: 0, rows: {} };
  globalThis.__R = R; R.reset();
  // ...the card is built once per run (its bundle is cached), holding the api it was built with: its calls are swapped in place
  Object.assign(globalThis.__api ||= {}, { get: async () => { reads += 1; return { data: run }; }, post: async () => ({ data: run }) });
  const BulkCard = await build();
  R.render(BulkCard, { rows, tid: 7, onChanged: () => {} }); await flush();
  const first = reads;
  run = { ...run, state: "finished", done: 3, rows: { 1: "ok", 2: "ok", 3: "ok" } };
  R.render(BulkCard, { rows: rows.map((r) => ({ ...r, Status: "approved" })), tid: 7, onChanged: () => {} }); await flush();
  assert.ok(reads > first, "the rows changed and the bar was not read again");
  assert.match(R.text(), /3 of 3 · 3 done/);
});

// A STOPPED RUN HE THEN WROTE PAST: the rest was set aside, greyed, and the bar still said "stopped - the rest still waits"
test("a stopped run whose rest the chat moved past never says the rest still waits", async () => {
  const flush = async () => { for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); };
  const aside = { Status: "superseded", DecideNote: "set aside when you moved on" };
  const rows = [1, 2, 3, 4].map((i) => ({ ...mail(i, `owner${i}@cedar.example`), ...(i <= 2 ? { Status: "approved" } : aside) }));
  const run = { key: "b1", state: "stopped", total: 4, done: 2, failed: 0, left: 0, rows: { 1: "ok", 2: "ok" } };
  globalThis.__R = R; R.reset();
  Object.assign(globalThis.__api ||= {}, { get: async () => ({ data: run }), post: async () => ({ data: run }) });
  const BulkCard = await build();
  R.render(BulkCard, { rows, tid: 7, onChanged: () => {} }); await flush();
  assert.match(R.text(), /2 of 4 · 2 done/);
  assert.doesNotMatch(R.text(), /the rest still waits/);
});

// A BULK CARD THE CHAT MOVED PAST IS THE SAME CARD, ITS BUTTONS GREYED (the owner, 2026-11-18: "don't need reason. just keep it with buttons but
// the buttons grayed out once you moved on"): its rows with their tick boxes, its one press - all under MovedPast - and no line saying why
test("a bulk card the chat moved past is the same card with its press, greyed, and no reason line", async () => {
  const flush = async () => { for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); };
  const aside = { Status: "superseded", DecideNote: "set aside when you moved on" };
  const rows = [1, 2].map((i) => ({ ...mail(i, `owner${i}@cedar.example`), ...aside }));
  globalThis.__R = R; R.reset();
  Object.assign(globalThis.__api ||= {}, { get: async () => ({ data: {} }), post: async () => ({ data: {} }) });
  const BulkCard = await build();
  R.render(BulkCard, { rows, tid: 7, onChanged: () => {} }); await flush();
  assert.deepEqual([R.root().type.name, R.root().props.on], ["MovedPast", true]);
  assert.match(R.text(), /Send 2 emails/); assert.doesNotMatch(R.text(), /Not done|moved on/);
  // ...and greyed from the frame his line is drawn, before the server sets it aside: the chat hands it `past`
  R.reset(); R.render(BulkCard, { rows: rows.map((r) => ({ ...r, Status: "pending", DecideNote: null })), tid: 7, onChanged: () => {}, past: true }); await flush();
  assert.deepEqual([R.root().type.name, R.root().props.on], ["MovedPast", true]);
  R.reset(); R.render(BulkCard, { rows: rows.map((r) => ({ ...r, Status: "pending", DecideNote: null })), tid: 7, onChanged: () => {} }); await flush();
  assert.equal(R.root().props.on, false);
});

test("rows open to review are given most of the window, a list of lines stays short", () => {
  assert.equal(listCap([{ id: 1 }, { id: 2 }]), 420);
  assert.equal(listCap([{ id: 1, open: true }, { id: 2 }]), "min(80vh, 900px)");
});

// The owner, 2026-11-26: "cards or anything generated on chat never go away" - a row's own card, open to review, folded to a line the moment
// he pressed or dismissed it
test("a row open in its own card stays open once it is settled, and the page gives a settled row its card", async () => {
  const open = new Set(), src0 = (await import("node:fs")).readFileSync(fileURLToPath(new URL("../src/BulkCard.jsx", import.meta.url)), "utf8");
  assert.equal(rowOpens(11, 0, { open }), true, "the first few stand open to review");
  assert.equal(rowOpens(13, 2, { open }), false);
  assert.equal(rowOpens(13, 2, { open: new Set([13]) }), true, "one he opened");
  assert.equal(rowOpens(11, 0, { open: new Set([-11]) }), false, "one he shut stays shut");
  assert.equal(rowOpens(11, 0, { open, live: true }), true, "and through the run: nothing folds at his press");
  assert.match(src0, /body: <div \{\.\.\.\(live \? \{ inert: "" \} : \{\}\)\}>\{own\(r\)\}<\/div>/, "looked at while the run does it, never pressed");
  const src = (await import("node:fs")).readFileSync(fileURLToPath(new URL("../src/BulkCard.jsx", import.meta.url)), "utf8");
  assert.match(src, /onCheck: \(\) => flip\(setSkip, r\.ReviewId\) \} : \{\}\),\s*open: shownRow\(r, i\)/, "open, and its card, whether the row waits or is settled");
});

// The owner, 2026-11-26: the same post for three networks is ONE card with a tab each; one act to many is the list card, never tabs - which
// it is, the server says (each row's `Tab`, taskuary/cardqueue.py sets), never a count
test("a set under tabs is read off its rows' own tab names; a list card has none", () => {
  const row = (id, Tab, Status = "pending") => ({ ReviewId: id, Kind: "action", Status, Batch: "k1", ...(Tab ? { Tab } : {}), DraftText: "{}" });
  assert.equal(tabsOf([row(1), row(2), row(3)], null), null, "one act to many: the list");
  assert.deepEqual(tabsOf([row(1, "LinkedIn", "approved"), row(2, "X", "rejected"), row(3, "Bluesky")], null),
    [{ key: "1", name: "LinkedIn", done: true, front: false }, { key: "2", name: "X", done: true, front: false, no: true }, { key: "3", name: "Bluesky", done: false, front: true }]);
  assert.equal(tabsOf([row(1, "LinkedIn"), row(2, "X")], null)[0].front, true, "the first that waits is in front");
  // ...walk 25, 2026-11-26: a sign-in handed over on the X tab he had pressed was drawn nowhere - the tab its step is on waits again, in front
  assert.deepEqual(tabsOf([row(1, "X", "approved"), row(2, "LinkedIn", "approved")], null, { review: 9, card: 1 }).map((t) => [t.name, t.done, t.front]),
    [["X", false, true], ["LinkedIn", true, false]]);
});

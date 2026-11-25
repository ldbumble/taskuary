// WHAT TASKUARY MADE IS A TASK IN THE ONE TASK PAGE (the owner, 2026-11-24: "reports/dashboards/ideas and tasks are the SAME CODE, not just
// consistent - the one task page, the same cards, the prompt as the input into the agent, the same box. Made-item special pages get deleted;
// only the data mapping differs"). A report, a dashboard and an Advisor idea on the table, server-rendered through the real cards: each is
// TaskPage - its Came from the item's source, its Agent the prompt line, Taskuary's run as the turn and the one box - its moves the one
// builder's (taskMoves), and no made-item page of its own is left. Invented people only.
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { taskMoves } from "../src/taskMoves.js";

// ...no network under a server render: the one client the page talks through, answering nothing
const AXIOS = { name: "axios", setup(b) { b.onResolve({ filter: /^axios$/ }, () => ({ path: "axios", namespace: "stub" }));
  b.onLoad({ filter: /.*/, namespace: "stub" }, () => ({ loader: "js", contents: "const a = { get: async () => ({ data: {} }), post: async () => ({ data: {} }), put: async () => ({ data: {} }), patch: async () => ({ data: {} }), delete: async () => ({ data: {} }), interceptors: { request: { use() {} }, response: { use() {} } }, defaults: { headers: { common: {} } } }; export default { ...a, create: () => a };" })); } };
const page = async () => {
  if (typeof navigator === "undefined") globalThis.navigator = { userAgent: "node", platform: "", language: "en-US" };   // ...Node 20 has none
  const hold = setInterval(() => {}, 1000);      // ...the loop held open while esbuild works (Node 22 saw an empty loop)
  try {
    const { build } = await import("esbuild");
    const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: `
      import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser";
      import { CardNav, DashboardCard, IdeaCard, ReportCard } from "./src/assistantCards.jsx";
      import { loadGeneral } from "./src/lazyGeneral.js";
      export const ready = () => loadGeneral();
      const Card = { report: ReportCard, dashboard: DashboardCard, idea: IdeaCard };
      export const draw = (kind, card, also = []) => { const C = Card[kind];
        return renderToStaticMarkup(<CardNav.Provider value={{ row: true, table: true, also, onNext: () => {}, ref: "" }}><C card={card} table={600} /></CardNav.Provider>); };` },
      bundle: true, write: false, format: "esm", jsx: "automatic", platform: "node", logLevel: "silent", plugins: [AXIOS], define: { "process.env.NODE_ENV": '"production"', "import.meta.env.BASE_URL": '"/"' },
      loader: { ".css": "empty", ".png": "empty", ".svg": "empty", ".jpg": "empty", ".woff2": "empty", ".json": "json" } });
    const { writeFileSync } = await import("node:fs"), { join } = await import("node:path"), { pathToFileURL } = await import("node:url");
    const f = join((await import("../browser/tempdirs.mjs")).ownTemp("tq-onepage-"), "page.mjs"); writeFileSync(f, out.outputFiles[0].text);
    const m = await import(pathToFileURL(f).href);
    await m.ready(); await new Promise((r) => setTimeout(r, 400));     // ...the chat's chunk in, as the page's first idle moment brings it
    return m;
  } finally { clearInterval(hold); }
};
let P_; const P = { then: (a, b) => (P_ ||= page()).then(a, b) };

const report = { key: "report:4", kind: "report", title: "Headcount by site", who: "Headcount by site", when: "2026-11-24 07:00:00", source_id: 4, mid: 51, channel: "report" };
const dash = { key: "dash:9", kind: "dashboard", title: "Spend this month", who: "Spend this month", when: "2026-11-24 07:00:00", source_id: 9, channel: "report" };
const idea = { key: "idea:3", kind: "idea", idea: 3, idea_kind: "money", title: "Payworth charged the October run twice", who: "Advisor", when: "2026-11-24 08:00:00",
  asked: "Look through the last week of mail for money left on the table.", action: { type: "lookout", next_step: "Ask Payworth to refund the second charge.",
    pitch: "Caught a duplicate charge before close.", mid: 12, who: "Erin Blake", why: "the same amount twice", evidence: [{ ref: "msg12", label: "the invoice" }, { ref: "task7", label: "the close" }] } };
const chips = (vs) => vs.map((verb) => ({ verb, label: verb, title: "", onClick: () => {} }));
const one = (html, attr) => (html.match(new RegExp(`${attr}=`, "g")) || []).length;

const theTaskPage = (html, kind) => {
  assert.match(html, /data-tq-task-page="/, "the task page itself");
  assert.equal(one(html, "data-tq-task-page"), 1);
  assert.match(html, new RegExp(`data-tq-made-page="${kind}"`));
  assert.match(html, /data-tq-sections=""/, "its sections in a row: Came from | Agent");
  assert.match(html, /data-tq-slot="from"/); assert.match(html, /data-tq-slot="agent"/);
  // ...the chat: the automated line, the run as Taskuary's turn holding its artifact, and the one box
  assert.match(html, /data-tq-auto-line=""/, "the prompt that asked, as the chat's input line");
  assert.match(html, /tq-aui-message tq-aui-agent[^"]*" data-tq-item="[^"]*:run"/, "the run as the turn that answered");
  assert.match(html, /data-tq-turn-cards=""/, "its content the turn's artifact");
  assert.equal(one(html, "data-tq-send"), 1, "the one box, its one Send");
  assert.doesNotMatch(html, /data-tq-item-sections=|data-tq-made=""/, "no made-item page of its own");
};

test("a report on the table is TaskPage: Came from its routine, Agent its prompt line, its run and the box", async () => {
  const { draw } = await P, html = draw("report", report, chips(["regular_agent", "report_off", "next"]));
  theTaskPage(html, "report");
  assert.match(html, /data-tq-made-source="report"/); assert.match(html, /The report/);
  assert.match(html, /data-tq-source-row="Name"[^]*Headcount by site/);
  assert.match(html, /data-tq-made-edit=""[^>]*>Edit this report/, "the way to change it, in its source");
  assert.match(html, /Automated · Headcount by site/);
});

test("a dashboard on the table is TaskPage too, its dashboard the turn's frame at the chat's whole width", async () => {
  const { draw } = await P, html = draw("dashboard", dash, chips(["report_off", "next"]));
  theTaskPage(html, "dashboard");
  assert.match(html, /data-tq-made-source="dashboard"/); assert.match(html, /The dashboard/);
  assert.match(html, /class="tq-dash-canvas tq-turn-frame tq-turn-wide( tq-dash-wait)?"/);    // ...holding its room while its rows load
});

test("an Advisor idea on the table is TaskPage: Came from the evidence it rests on, Agent the look's prompt and what it noticed", async () => {
  const { draw } = await P, html = draw("idea", idea, chips(["mine", "regular_agent", "not_ours", "defer", "next"]));
  theTaskPage(html, "idea");
  assert.match(html, /What it rests on/);
  for (const h of ["#msg=12", "#task=7"]) assert.match(html, new RegExp(`data-tq-cite="${h}"`));
  assert.match(html, /Look through the last week of mail for money left on the table\./, "the look's prompt is the input line");
  assert.match(html, /Ask Payworth to refund the second charge\./, "what to do, in the turn");
  assert.match(html, /Automated · Advisor · money left on the table/);
});

test("an item's moves come from the one builder: its own move lit, Pause, Make it a task, Remind me, Not for me - no agent start, no Next", () => {
  const word = (verb) => ({ verb, label: verb, title: `${verb} hint`, onClick: () => {} });
  const vs = taskMoves({ made: [word("next"), word("not_ours"), word("regular_agent"), word("defer"), word("mine"), word("report_off"), { ...word("connect"), own: true }] }, {}, {});
  assert.deepEqual(vs.map((v) => v.id), ["w:connect", "w:report_off", "w:mine", "w:defer", "w:not_ours"]);
  assert.equal(vs[0].tone, "p"); assert.ok(vs.slice(1).every((v) => v.tone === "s"));
  assert.deepEqual(vs.map((v) => v.group), ["decide", "decide", "decide", "more", "more"]);
  // ...a task's own moves are untouched by it
  const task = taskMoves({ closed: false }, {}, { label: (k) => k, hint: () => "" });
  assert.equal(task[0].id, "done");
});

test("no made-item page remains: no MadeTurn, no madeView, no item sections for what Taskuary made", () => {
  const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
  assert.equal(existsSync(new URL("../src/madeView.js", import.meta.url)), false);
  assert.doesNotMatch(src("ItemSections.jsx"), /MadeTurn/);
  const cards = src("assistantCards.jsx");
  assert.doesNotMatch(cards, /MadeTurn|madeSection|kind="(report|dashboard|idea)"/);
});

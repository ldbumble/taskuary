import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");


test("From's last line says what triage made of it in one plain sentence, and the kind hints carry no coding words", async () => {
  const page = src("TaskPage.jsx");
  assert.match(page, /<Box data-tq-sorted="" title=/);
  assert.match(page, /\{triageSays\(facts, t\?\.Kind \|\| "task", triaged\.why\)\}/);
  for (const jargon of ["without a repository", "the configured CLI", "the model triage uses", "harness"]) assert.ok(!page.includes(jargon), jargon);
  const { sortedLine, triageSays } = await import("../src/taskSources.js");
  const pills = (o) => Object.entries(o).map(([key, value]) => ({ key, value }));
  assert.equal(sortedLine({ triaged: true, pills: pills({ intent: "task", who: "an agent · general", priority: "normal" }) }, "general"),
    "Sorted as: a task for an assistant · normal priority");
  assert.equal(sortedLine({ triaged: true, pills: pills({ intent: "reply", priority: "high" }) }, "reply"), "Sorted as: a reply to send · high priority");
  assert.equal(sortedLine({ triaged: false, pills: pills({ priority: "normal" }) }, "task"), "A task for you · normal priority");
  // ...and under the card's own head it reads one way, sorted by triage or made by hand
  const { madeOf } = await import("../src/taskSources.js");
  assert.equal(madeOf({ triaged: true, pills: pills({ intent: "task", priority: "normal" }) }, "task"), madeOf({ triaged: false, pills: pills({ priority: "normal" }) }, "task"));
  assert.equal(madeOf({ triaged: true, pills: pills({ intent: "reply", priority: "high" }) }, "reply"), "A reply to send · high priority");
  assert.match(page, /\{madeOf\(facts, t\?\.Kind \|\| "task"\)\}/);
  // ...and the why triage recorded rides at its end: "Sorted as: <what> · <priority> · <why>"
  assert.equal(triageSays({ triaged: true, pills: pills({ intent: "reply", priority: "normal" }) }, "reply", "  she asks for half an hour\n on a named day "),
    "Sorted as: a reply to send · normal priority · she asks for half an hour on a named day");
  assert.equal(triageSays({ triaged: true, pills: pills({ intent: "task", priority: "high" }) }, "coding", ""), "Sorted as: a task for your coding tool · high priority");
});


// NOTHING DARKENS ITSELF: a running agent's Stop and save did (the owner, 2026-10-20), the one exception the dead-end walk excused - it is
// gone (the owner, 2026-11-10: "no need for stop and save button"), and so is the exception
test("no verb on the row darkens itself; only the Advisor's pick is dark", async () => {
  const { rowOf } = await import("../src/actionRow.js");
  const v = (id, group, extra = {}) => ({ id, group, label: id, tone: "s", promote: true, ...extra });
  const list = [v("continue", "agent", { lead: true, fill: true }), v("diff", "agent"), v("done", "more"), v("next", "next")];
  const dark = (r) => [...r.decide, ...r.agent, ...r.more].filter((x) => x.tone === "p");
  assert.deepEqual(dark(rowOf({ ref: "", list })), [], "nothing said: nothing dark");
  assert.deepEqual(dark(rowOf({ ref: "", list }, { verb: "review_changes", label: "diff" })).map((x) => x.id), ["diff"], "the Advisor's pick");
  assert.doesNotMatch(src("ActionRow.jsx"), /data-tq-own/);
  assert.doesNotMatch(readFileSync(new URL("../deadend_check.mjs", import.meta.url), "utf8"), /darkOwn|data-tq-own/);
});

test("the row puts a leading agent verb first and Mark done beside it (actionRow.rowOf)", async () => {
  const { rowOf, clustersOf } = await import("../src/actionRow.js");
  const v = (id, group, extra = {}) => ({ id, group, label: id, tone: "s", promote: true, ...extra });
  // nothing waiting on approval: the agent's lead (Continue) leads, Mark done does not take the lead from it
  const live = rowOf({ ref: "", list: [v("continue", "agent", { lead: true }), v("diff", "agent"), v("done", "more"), v("next", "next")] });
  assert.deepEqual(live.agent.map((x) => x.id), ["continue", "diff", "done"]);
  assert.equal(live.decide.length, 0);
  assert.deepEqual(clustersOf(live).find((c) => c.type === "move").shown.map((x) => x.id), ["done", "continue", "diff"], "Mark done, then the agent's lead");
  // ...a reply waiting: its Send leads (a decision), and the agent's moves wait after it
  const waiting = rowOf({ ref: "", list: [v("r1:approve", "decide", { tone: "p" }), v("diff", "agent"), v("run-another", "agent"), v("done", "more", { promote: false }), v("next", "next")] });
  assert.equal(waiting.decide[0].id, "r1:approve");
  assert.deepEqual(waiting.agent.slice(0, 2).map((x) => x.id), ["diff", "run-another"]);
});

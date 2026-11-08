// THE AGENT SETS IT UP LIKE AN EMAIL (the owner, 2026-11-08): the demo's invite (TQ-0013) ends in its answer as a card - a new time with its
// Propose this time - not "No draft yet - hit Draft with AI"; the dashboard turn (TQ-0032) ends in a Share with Gail card over the dashboard,
// not "Share the dashboard with Gail, or say..." as prose. Pressing either in the demo says it is the demo.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const fx = JSON.parse(readFileSync(new URL("../src/demoFixtures.json", import.meta.url), "utf8"));
const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const env = (r) => JSON.parse(r.Deliver || "{}");
const last = (tid) => fx["/api/tasks/detail"][`${tid}:assistant`].messages.filter((m) => m.role === "assistant").at(-1);

test("the invite's turn says the clash and leaves a new time waiting on its press", () => {
  const d = fx["/api/tasks/detail"]["13"], rv = d.reviews.find((r) => r.Status === "pending");
  assert.equal(d.task.Kind, "general");
  assert.deepEqual([env(rv).kind, env(rv).act], ["calendar", "propose"]);
  assert.ok(env(rv).new_start && env(rv).was);
  const t = last(13);
  assert.match(t.summary.did, /clashes with Quarter-end planning/);
  assert.deepEqual(t.summary.drafted, [{ review: rv.ReviewId }]);
  assert.ok(fx["/api/reviews"].data.some((r) => r.ReviewId === rv.ReviewId), "the press finds it among the reviews");
});

test("the dashboard's turn ends in its share card, not a step for the owner", () => {
  const d = fx["/api/tasks/detail"]["32"], rv = d.reviews.find((r) => r.Status === "pending");
  assert.deepEqual(env(rv).share, { report: 8, title: "Vendor spend, weekly", to: "Gail Moreno" });
  assert.ok(fx["/api/dashboards/8"], "the dashboard it draws is in the recording");
  assert.equal(d.checklist.length, 0);
  assert.ok(!last(32).summary.on_you, "no prose step left on the owner");
});

test("the card presses as its act, and the demo says so at the press", () => {
  const rd = src("ReviewDecision.jsx");
  assert.match(rd, /propose: "Propose this time", schedule: "Send invite"/);
  assert.match(rd, /`Share with \$\{shareTo\}`/);
  assert.match(rd, /data-tq-cal-instead/);
  assert.match(src("demoApi.js"), /env\.kind === "calendar" \|\| env\.share/);
  assert.match(src("TaskPage.jsx"), /const replyEmpty = !!replyMessage && !detail\?\.calendar\?\.invite/);
});

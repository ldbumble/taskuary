// ANYTHING FOR HIS REVIEW IS ONE CARD (the owner, 2026-11-24: "merge the cards into one too"): an email, a reply, a post, a GitHub comment, a Jira
// comment, a bulk job, one that went, one that failed and one moved past - each drawn through the real components, server-rendered, is the one
// ReviewCard (Artifact.jsx) with its kind's fields, its press named by what it does, and its state drawn on itself.
import test from "node:test";
import assert from "node:assert/strict";

// ...no network under a server render: the one client the page talks through, answering nothing
const AXIOS = { name: "axios", setup(b) { b.onResolve({ filter: /^axios$/ }, () => ({ path: "axios", namespace: "stub" }));
  b.onLoad({ filter: /.*/, namespace: "stub" }, () => ({ loader: "js", contents: "const a = { get: async () => ({ data: {} }), post: async () => ({ data: {} }), put: async () => ({ data: {} }), interceptors: { request: { use() {} }, response: { use() {} } }, defaults: { headers: { common: {} } } }; export default { ...a, create: () => a };" })); } };
const page = async () => {
  const hold = setInterval(() => {}, 1000);      // ...the loop held open while esbuild works (Node 22 saw an empty loop)
  try {
    const { build } = await import("esbuild");
    const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: `
      import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser";
      import ReviewDecision, { SentReview } from "./src/ReviewDecision.jsx"; import BulkReview from "./src/BulkCard.jsx";
      export const card = (review, more = {}) => renderToStaticMarkup(<ReviewDecision review={review} onChanged={() => {}} {...more} />);
      export const bulk = (rows) => renderToStaticMarkup(<BulkReview rows={rows} tid={7} onChanged={() => {}} />);
      export const sent = (p) => renderToStaticMarkup(<SentReview {...p} />);` },
      bundle: true, write: false, format: "esm", jsx: "automatic", platform: "node", logLevel: "silent", plugins: [AXIOS], define: { "process.env.NODE_ENV": '"production"' },
      loader: { ".css": "empty", ".png": "empty", ".svg": "empty", ".jpg": "empty", ".woff2": "empty", ".json": "json" } });
    const { writeFileSync } = await import("node:fs"), { join } = await import("node:path"), { pathToFileURL } = await import("node:url");
    const f = join((await import("../browser/tempdirs.mjs")).ownTemp("tq-card-"), "page.mjs"); writeFileSync(f, out.outputFiles[0].text);
    return import(pathToFileURL(f).href);
  } finally { clearInterval(hold); }
};
let P_; const P = { then: (a, b) => (P_ ||= page()).then(a, b) };

const act = (p, more = {}) => ({ ReviewId: 41, TaskId: 7, Kind: "action", Status: "pending", DraftText: JSON.stringify(p), CreatedAt: "2026-11-24 09:00:00", ...more });
const reply = (more = {}) => ({ ReviewId: 31, TaskId: 7, Kind: "reply", Status: "pending", Channel: "email", MessageId: 5, FromName: "Erin Blake", FromEmail: "erin@northwind.example",
  DraftText: "Thanks Erin - the plans are attached.", CanSend: 1, Deliver: JSON.stringify({ channel: "email", to: ["erin@northwind.example"], subject: "Re: Plans" }), ...more });
const one = (html) => (html.match(/data-tq-review-card=/g) || []).length;
const press = (html) => [...html.matchAll(/<button[^>]*data-tq-press="[^"]*"[^>]*>(?:<span[^>]*>.*?<\/span>)?([^<]*)</g)].map((m) => m[1]);

test("an email is the one card: To, Subject and its words editable, its press Send", async () => {
  const { card } = await P, html = card(reply());
  assert.equal(one(html), 1);
  assert.match(html, /data-tq-review-kind="email"/); assert.match(html, /data-tq-act-state="waiting"/);
  assert.match(html, /data-tq-to-line=""/); assert.match(html, /data-tq-subject="" [^>]*value="Re: Plans"/);
  assert.match(html, /<textarea[^>]*data-tq-draft=""[^>]*>Thanks Erin/);
  assert.ok(press(html).some((w) => /^Send/.test(w)), press(html).join("|"));
});

test("a chat reply is the same card, labelled by its channel, its press Send", async () => {
  const { card } = await P, html = card(reply({ Channel: "whatsapp", Deliver: JSON.stringify({ channel: "whatsapp" }) }));
  assert.equal(one(html), 1); assert.match(html, /data-tq-review-label="">Reply on WhatsApp</);
  assert.doesNotMatch(html, /data-tq-subject/, "a chat has no subject");
  assert.ok(press(html).some((w) => /^Send/.test(w)));
});

test("a LinkedIn post is the same card: its words editable, its picks under the label, its press Post to LinkedIn", async () => {
  const { card } = await P, html = card(act({ action: "run_tool", type: "linkedin_post", text: "Three tools, compared." }));
  assert.equal(one(html), 1); assert.match(html, /data-tq-review-kind="post"/);
  assert.match(html, /<textarea[^>]*>Three tools, compared\.<\/textarea>/);
  assert.match(html, /data-tq-act-choice="visibility"/);
  assert.deepEqual(press(html), ["Post to LinkedIn", "Dismiss"]);
});

test("a post on a network not connected is the same card: Post via the browser, its final Post held for him", async () => {
  const { card } = await P, html = card(act({ action: "run_tool", type: "x_post", text: "We shipped." }, { Connect: { label: "Connect X", href: "#connector=x", says: "X is not connected" } }));
  assert.equal(one(html), 1); assert.equal(press(html)[0], "Post via the browser");
  assert.match(html, /its last Post waits for you/);
});

test("a GitHub comment is the same card: where it goes, its words his to change, its press Comment", async () => {
  const { card } = await P, html = card(act({ action: "comment_issue", repo: "northwind/ledger", number: 12, body: "Fixed in the next build." }));
  assert.equal(one(html), 1); assert.match(html, /northwind\/ledger#12/);
  assert.match(html, /<textarea(?![^>]*readonly)[^>]*>Fixed in the next build\.<\/textarea>/, "editable");
  assert.equal(press(html)[0], "Comment");
});

test("a Jira comment is the same card, its press Post comment", async () => {
  const { card } = await P, html = card(act({ action: "run_tool", type: "jira_comment", item: "OPS-4", body: "Done on our side." }));
  assert.equal(one(html), 1); assert.match(html, /data-tq-review-kind="tracker"/); assert.equal(press(html)[0], "Post comment");
});

test("a bulk job is the same card with its rows, its press doing them all", async () => {
  const { bulk } = await P, rows = [1, 2, 3].map((i) => reply({ ReviewId: 50 + i, Kind: "slot", MessageId: null, Batch: "b1",
    Deliver: JSON.stringify({ channel: "email", to: [`p${i}@vendor.example`], subject: `Renewal ${i}` }) }));
  const html = bulk(rows);
  assert.match(html, /data-tq-review-kind="bulk"/); assert.equal((html.match(/data-tq-bulk-row=/g) || []).length, 3);
  assert.ok(press(html).includes("Send 3 emails"), press(html).join("|"));
});

test("a reply that went is the same card, its press row turned to what the press did - in place, no second card", async () => {
  const { card, sent } = await P, html = card(reply({ Status: "approved", FinalText: "Thanks Erin - the plans are attached.", DecidedAt: "2026-11-24 09:05:00" }));
  assert.equal(one(html), 1); assert.match(html, /data-tq-act-state="sent"/); assert.match(html, /data-tq-pressed="sent"/);
  assert.doesNotMatch(html, /<textarea/, "its words stand as they went"); assert.equal(press(html).length, 0);
  assert.equal(one(sent({ id: 31, text: "Thanks", channel: "email", to: "Erin Blake", subject: "Re: Plans" })), 1, "the record of a send is the same card");
});

test("a post whose press failed keeps its error on the same card", async () => {
  const { card } = await P, html = card(act({ action: "run_tool", type: "linkedin_post", text: "Hi" }, { Status: "superseded", ActError: "LinkedIn refused the token" }));
  assert.equal(one(html), 1); assert.match(html, /data-tq-review-failed=""[^>]*>[\s\S]*LinkedIn refused the token/);
});

test("a card moved past is the same card, greyed, every press off", async () => {
  const { card } = await P, html = card(reply(), { past: true });
  assert.equal(one(html), 1); assert.match(html, /^<fieldset disabled=""/);
});

// THE PRESS ROAD IS THE ONE IMPORTED (recorded, 2026-11-24: Send and Comment on the one card said "That didn't go through - nothing was sent"
// and no request left the page - the card's list of buttons was named `press`, over the press.js road every send takes)
test("nothing in the cards' files takes the press road's name", async () => {
  const { readFileSync } = await import("node:fs");
  for (const f of ["ReviewDecision.jsx", "BulkCard.jsx"]) assert.doesNotMatch(readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8"), /\b(const|let|var)\s+press\b/, f);
});

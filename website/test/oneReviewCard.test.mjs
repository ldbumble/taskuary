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
      import PassedCard from "./src/PassedCard.jsx"; import HeldSteps from "./src/HeldSteps.jsx";
      export const passed = (reviews) => renderToStaticMarkup(<PassedCard reviews={reviews} />);
      export const held = (reviews) => renderToStaticMarkup(<HeldSteps reviews={reviews} />);
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
  assert.match(html, /data-tq-to-line=""/); assert.match(html, /<textarea[^>]*rows="1"[^>]*data-tq-subject=""[^>]*>Re: Plans<\/textarea>/, "one line that wraps where it is long - never an input cut at its start");
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

// The card gallery, 2026-11-25: Comment stood outlined on the GitHub comment card, Approve on a proposal at phone width - the card deferred to
// the task's bar (`toRow`), which draws no card's press. The press named by what it does is the filled one on every card; the rest are not
test("the primary press is the filled button on every card, with the task's bar or without", async () => {
  const { card, held } = await P, filled = (html) => [...html.matchAll(/<button[^>]*class="[^"]*MuiButton-contained[^"]*"[^>]*>(?:<span[^>]*>.*?<\/span>)?([^<]*)</g)].map((m) => m[1]);
  for (const more of [{}, { toRow: true }]) {
    assert.deepEqual(filled(card(act({ action: "comment_issue", repo: "northwind/ledger", number: 12, body: "Fixed." }), more)), ["Comment"]);
    assert.deepEqual(filled(card(act({ action: "settings", changes: [{ name: "poll_minutes", value: 10 }] }), more)), ["Approve"]);
    assert.deepEqual(filled(card(reply(), more)), ["Send"]);
  }
  assert.deepEqual(filled(card(act({ action: "run_tool", type: "jira_comment", item: "OPS-4", body: "Done." }))), ["Post comment"]);
  assert.deepEqual(filled(held([act({ action: "shell_act", sid: "s", command: "git push", about: "Push the fix" })])), ["Approve"]);
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

// A CHANGE TO SOMETHING STORED IS THE SAME ONE CARD (the owner, 2026-11-24, over "prompt: <whole old> -> <whole new>" in the box: "to edit text it
// should show the edited text?" ... "show also where it changed in the full text" ... "it says on top it changes 3 times"): its label once, why in
// one line, the new words whole and his to change, marked in place where they change - never the old -> new dump, never a line saying it again
const routineChange = () => act({ action: "repair_workflow", source_id: 3, title: "Social post drafts", why: "Make future posts short",
  flow: [{ id: "s1", kind: "agent", label: "Agent works it", prompt: "Write three short posts." }], was: [{ id: "s1", kind: "agent", label: "Agent works it", prompt: "Write three long posts." }],
  texts: [{ key: "flow.s1.prompt", label: "The routine will say", was: "Write three long posts.", now: "Write three short posts." }], rows: [],
  changes: "The routine will say: Write three short posts." }, { Reason: 'the agent proposes to change the routine "Social post drafts" - Make future posts short' });
test("a routine's change is the one card: its new words marked where they change, nothing said twice", async () => {
  const { card } = await P, html = card(routineChange());
  assert.equal(one(html), 1);
  assert.match(html, /data-tq-review-label="">Change routine: Social post drafts</);
  assert.match(html, /data-tq-held-lead="[^"]*"[^>]*>Make future posts short\.</, "why, once");
  assert.match(html, /data-tq-change="flow.s1.prompt" data-tq-marks="on"/);
  assert.match(html, /Write three <del data-tq-removed="">long <\/del><ins data-tq-added="">short <\/ins>posts\./, "where it changed, in the full text");
  assert.match(html, /data-tq-change-label="">The routine will say</);
  assert.match(html, /Hide what changed/);
  assert.doesNotMatch(html, /-&gt;|→/, "no old -> new dump");
  assert.doesNotMatch(html, /only if you approve|saved steps|Agent works it/, "no line that says it again");
  assert.ok(press(html).includes("Approve"), press(html).join("|"));
});

// THE CARD IS THE DOCUMENT, AND THE ROUTINE AS THE PRESS LEAVES IT (the owner, 2026-11-26: an agent grew his post routine's instructions to
// ~3,000 characters and left its goal "for manual posting" and its browser on - "the card that shows the changes should bring up the skill card
// or the instructions and show what the agent is editing"): how long the words were and are, and each key field after the press - a stale one
// said plainly, a changed one beside what it was, never said twice as a row
test("a routine's change says how long its words are and shows the routine as the press leaves it", async () => {
  const { card } = await P, base = JSON.parse(routineChange().DraftText);
  const html = card(act({ ...base, rows: [{ label: "Browser", was: "on", now: "off" }], after: [{ label: "Goal", now: "Drafts for manual posting." },
    { label: "Runs", now: "daily at 09:00" }, { label: "Browser", now: "off", was: "on" }, { label: "Connections", now: "none" }, { label: "Skill", now: "social-posts" }] }));
  assert.equal(one(html), 1);
  assert.match(html, /data-tq-change-length="">24 characters · was 23</);
  assert.match(html, /data-tq-facts="after"/);
  assert.match(html, /data-tq-fact="Goal"[^>]*>Drafts for manual posting\.</, "a stale field is there to see");
  assert.match(html, /data-tq-fact="Browser" data-tq-fact-changed=""[^>]*><ins data-tq-added="">off<\/ins> <del data-tq-removed="">on<\/del>/);
  assert.match(html, /data-tq-fact="Skill"[^>]*>social-posts</);
  assert.equal((html.match(/>Browser</g) || []).length, 1, "what the facts say is not a row above them too");
  assert.ok(html.indexOf('data-tq-facts="after"') < html.indexOf('data-tq-change="flow.s1.prompt"'), "the facts stand over the long words");
});

const PAGE = "---\nname: social-posts\ndescription: Write the social posts. Use when a post is due.\n---\n# Social posts\n\nOne idea a post. Plain words.\n";
test("a skill's change is its page with the edits marked; a new skill is all added", async () => {
  const { card } = await P;
  const edit = card(act({ action: "save_skill", slug: "social-posts", text: PAGE.replace("Plain words.", "Short, plain words."), was_text: PAGE, used_by: ["Social posts"], why: "punchier" }));
  assert.equal(one(edit), 1);
  assert.match(edit, /data-tq-review-label="">Change skill: Social posts</);
  assert.match(edit, /data-tq-change="draft" data-tq-marks="on"/);
  assert.match(edit, /One idea a post\. <del data-tq-removed="">Plain <\/del><ins data-tq-added="">Short, plain <\/ins>words\./, "the page whole, the edit in place");
  assert.match(edit, /data-tq-change-length="">\d+ characters · was \d+</);
  assert.match(edit, />Used by</); assert.match(edit, />Social posts</);
  const fresh = card(act({ action: "save_skill", slug: "social-posts", text: PAGE }));
  assert.match(fresh, /data-tq-change="draft" data-tq-marks="on"/);
  assert.equal((fresh.match(/<ins data-tq-added/g) || []).length, 1, "one run, the page whole"); assert.doesNotMatch(fresh, /<del /);
  assert.match(fresh, /characters · new</);
});

test("a setting's change reads each switch as it is and as it will be, said once", async () => {
  const { card } = await P, html = card(act({ action: "settings", why: "fewer polls", changes: [{ name: "poll_minutes", value: "15", was: "5" }] }));
  assert.match(html, /data-tq-review-label="">Change a setting</);
  assert.match(html, />5 → 15</);
  assert.doesNotMatch(html, /until you approve|>Settings</);
});

test("a held browser step names its site once - in its title where the title says it, else on its On row (walk 19)", async () => {
  const { card } = await P;
  const held = (about) => card(act({ action: "browser_act", about, what: "click @e12", name: "127.0.0.1", command: "agent-browser click @e12" }));
  const named = held('Click the "Sign in" button on 127.0.0.1');
  assert.equal(one(named), 1); assert.match(named, /Sign in&quot; button on 127\.0\.0\.1|Sign in" button on 127\.0\.0\.1/);
  assert.equal((named.match(/127\.0\.0\.1/g) || []).length, 1, "the site said once");
  const bare = held('Click the "Sign in" button');
  assert.match(bare, />On</); assert.equal((bare.match(/127\.0\.0\.1/g) || []).length, 1, "the On row names it");
});

// ...AND A CARD HE PRESSED AND A HELD STEP STAND IN THE ONE FRAME every card of a turn does (the card gallery, 2026-11-25: each drew a flat box of
// its own, the chat's whole width, beside raised cards a column wide - "consistent look, all through the one Artifact frame")
test("a pressed card and a held step are drawn in the one frame", async () => {
  const { passed, held } = await P;
  const said = { action: "comment_issue", repo: "northwind/ledger", number: 12, body: "Fixed.", result: { commented: "northwind/ledger#12" } };
  const went = passed([act(said, { ReviewId: 1, Status: "approved", FinalText: JSON.stringify(said) })]);
  assert.match(went, /<div class="tq-turn-frame[^"]*"[^>]*data-tq-passed="1"/); assert.match(went, /✓ Commented/, "what its press did, in its own word (outcomeOf)");
  const waits = held([act({ action: "shell_act", sid: "run1", turn: 1, command: "curl -X POST https://api.vendor.example/orders", what: "send data to api.vendor.example",
    why: "it leaves this computer", cwd: "C:/work" }, { ReviewId: 2 })]);
  assert.match(waits, /<div class="tq-turn-frame[^"]*"[^>]*data-tq-held-steps="1"/); assert.match(waits, /data-tq-held-approve=""/);
});

// ...A CARD THAT WENT OFFERS NO PRESS (the card gallery, 2026-11-25: a greyed "Attach another" stood beside the files of every sent email): its
// files stay to open, the press to add one is gone with its Send
test("a sent email keeps its files and no Attach", async () => {
  const { card } = await P, files = { channel: "email", to: ["erin@northwind.example"], subject: "Re: Plans", attachments: [{ name: "plans.pdf", size: 2048 }] };
  const waits = card(reply({ Deliver: JSON.stringify(files) }));
  assert.match(waits, /data-tq-reply-file="plans\.pdf"/); assert.match(waits, /Attach another/);
  const went = card(reply({ Status: "approved", FinalText: "Thanks Erin - the plans are attached.", DecidedAt: "2026-11-24 09:05:00", Deliver: JSON.stringify(files) }));
  assert.match(went, /data-tq-reply-file="plans\.pdf"/); assert.doesNotMatch(went, /Attach (another|a file)/);
});

// ...AND A PRESS THAT OPENS SOMETHING UNDER ITS CARD SAYS SO (data-tq-opens-under), so the chat keeps the card where it stood (GeneralWorkspace's
// fold) - Connect on a network not set up drew its setup under the card, and the chat jumped to the setup's foot
test("Connect and a bulk row's Open are presses that open under what was pressed", async () => {
  const { card, bulk } = await P;
  const post = act({ action: "run_tool", type: "linkedin_post", network: "LinkedIn", text: "Three tools, compared." }, { connect: { label: "Connect LinkedIn", href: "#connector=linkedin", says: "LinkedIn isn't connected" },
    Connect: { label: "Connect LinkedIn", href: "#connector=linkedin", says: "LinkedIn isn't connected" } });
  assert.match(card(post), /<button[^>]*data-tq-opens-under=""[^>]*>(?:<span[^>]*>.*?<\/span>)?Connect LinkedIn/);
  const letter = (id) => reply({ ReviewId: id, Kind: "slot", Batch: "b1", MessageId: null, Deliver: JSON.stringify({ channel: "email", to: [`owner${id}@vendor.example`], subject: "Renewal" }) });
  assert.match(bulk([letter(1), letter(2), letter(3)]), /<button[^>]*data-tq-opens-under=""[^>]*aria-expanded="true"[^>]*>Hide/);
});

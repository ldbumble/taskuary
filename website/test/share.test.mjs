// SHARE A RESULT (the owner, 2026-10-23: "button on report on bottom named share"): one Share on the row, in a band of its own; its ways
// greyed with the server's reason; a result the store holds is named, never re-sent; and the cards that carry a result register it.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { SHARE_ID, SETTING_HREF, WAYS, offersSetting, shareBody, shareVerb, shareable, sharedNote, waysOf } from "../src/share.js";
import { clustersOf, rowOf, typeOf } from "../src/actionRow.js";
import { VERBS, label, verbOfRow } from "../src/buttons.js";

const src = (f) => fs.readFileSync(path.join(import.meta.dirname, "../src", f), "utf8");

test("one button, one name: Share, from buttons.json, the row id `share`", () => {
  assert.equal(label("share_result"), "Share");
  assert.equal(verbOfRow(SHARE_ID), "share_result");
  const v = shareVerb(() => {});
  assert.deepEqual([v.id, v.label, v.group, v.tone], ["share", "Share", "more", "s"]);
  assert.ok(v.title.length > 10);
  assert.ok(VERBS.share.label !== "Share", "Send out results keeps its own name");
});

test("Share stands in a band of its own at the row's end, never hidden in another type's ▾", () => {
  const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
  const row = rowOf({ ref: "", list: [v("w:mine", "decide"), v("w:regular_agent", "decide"), v("w:x", "decide"), shareVerb(() => {}), v("next", "next")] });
  const g = clustersOf(row);
  assert.equal(typeOf({ id: "share" }), "share");
  assert.deepEqual(g.at(-1).shown.map((x) => x.id), ["share"]);
  assert.equal(g.at(-1).label, "");
});

test("the four ways, in order, each greyed with the server's sentence", () => {
  assert.deepEqual(WAYS.map((w) => w.key), ["email", "link", "onedrive", "gdrive"]);
  const rows = waysOf({ email: { ok: true, why: "" }, link: { ok: false, why: "share links are off" }, onedrive: { ok: false, why: "needs Files.ReadWrite" },
    gdrive: { ok: true, why: "" }, setting: false });
  assert.deepEqual(rows.map((r) => [r.key, r.ok, r.why]), [["email", true, ""], ["link", false, "share links are off"], ["onedrive", false, "needs Files.ReadWrite"], ["gdrive", true, ""]]);
  assert.ok(waysOf(null).every((r) => !r.ok && r.why === "Checking…"));
  assert.ok(waysOf(null, true).every((r) => !r.ok && /did not answer/.test(r.why)));
});

test("a greyed link because the switch is off points at the switch - and only then", () => {
  assert.equal(offersSetting({ setting: false, link: { ok: false } }), true);
  assert.equal(offersSetting({ setting: true, link: { ok: false, why: "listens only on this computer" } }), false);
  assert.equal(offersSetting(null), false);
  assert.match(SETTING_HREF, /group=Sharing&key=share_links_lan$/);
});

test("a result the store holds is named, not re-sent; a page's own result brings its words", () => {
  assert.deepEqual(shareBody({ kind: "report", title: "Weekly spend", message: 7, text: "ignored" }, "link"), { how: "link", kind: "report", title: "Weekly spend", message: 7 });
  assert.deepEqual(shareBody({ kind: "agent", task: 3 }, "email", { to: ["erin@northwind.example"] }), { how: "email", kind: "agent", task: 3, to: ["erin@northwind.example"] });
  assert.deepEqual(shareBody({ kind: "dashboard", title: "Spend", html: "<b>x</b>", data: [{ a: 1 }] }, "gdrive"),
    { how: "gdrive", kind: "dashboard", title: "Spend", html: "<b>x</b>", data: [{ a: 1 }] });
  assert.equal(shareable({ kind: "dashboard", title: "Empty" }), false);
  assert.equal(shareable({ message: 1 }), true);
  assert.equal(shareable(null), false);
});

test("the badge's hover says where it went; an email says nothing is sent before Send", () => {
  assert.match(sharedNote("email", { to: ["erin@northwind.example"], ref: "TQ-0001" }), /nothing is sent until you press Send/);
  assert.match(sharedNote("link", { url: "http://192.168.1.20:7787/share/x", expires: "2026-10-30 10:00:00" }, true), /link copied/);
  assert.match(sharedNote("link", { url: "http://192.168.1.20:7787/share/x" }, false), /copy it: http/);
});

test("the cards that carry a result register Share; the hook is documented for a dashboard", () => {
  assert.match(src("assistantCards.jsx"), /useShare\(`report:[^)]*kind: "report"[^)]*message: card\.mid/);
  assert.match(src("TaskPage.jsx"), /useShare\(`task:\$\{t\?\.TaskId\}`/);
  assert.match(src("TaskPage.jsx"), /resultShown \|\| codeRun/);
  const share = src("Share.jsx");
  assert.match(share, /useShare\("dashboard"/, "the hook's comment shows a dashboard how to register");
  assert.match(share, /useVerbs\(`share:\$\{owner\}`/);
  assert.match(share, /title=\{w\.why \|\| undefined\}/, "a greyed way says why on its hover");
  assert.match(share, /navigator\.clipboard\.writeText\(data\.url\)/);
  assert.doesNotMatch(share, /dangerouslySetInnerHTML/);
});

test("Settings lists the open links under the switch, each with Revoke", () => {
  const s = src("SettingsView.jsx");
  assert.match(s, /Sharing: <SharedLinks \/>/);
  assert.match(src("SharedLinks.jsx"), /api\.delete\(`\/api\/shares\/\$\{id\}`\)/);
});

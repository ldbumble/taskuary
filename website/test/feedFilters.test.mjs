import test from "node:test";
import assert from "node:assert/strict";
import { availablePickerChannels, channelsForCategory } from "../src/feedFilters.js";

test("the compact categories keep email, chats, code, and reports distinct", () => {
  assert.deepEqual(channelsForCategory("email"), ["email"]);
  assert.deepEqual(channelsForCategory("messages"), ["teams", "slack", "telegram", "whatsapp", "imessage", "discord"]);
  assert.deepEqual(channelsForCategory("code"), ["github", "gitlab"]);
  assert.deepEqual(channelsForCategory("reports"), ["report", "assistant"]);
});

test("other contains the secondary systems and any future connected channel", () => {
  const other = channelsForCategory("other", ["email", "github", "assistant", "caldav"]);
  assert.ok(other.includes("jira"));
  assert.ok(other.includes("sentry"));
  assert.ok(other.includes("aws"));
  assert.ok(other.includes("caldav"));
  assert.ok(!other.includes("email"));
  assert.ok(!other.includes("github"));
  assert.ok(!other.includes("assistant"));
});

test("the detailed picker offers only channels that are actually available", () => {
  const available = ["email", "github", "assistant", "jira", "caldav"];
  assert.deepEqual(availablePickerChannels("reports", available), ["assistant"]);
  assert.deepEqual(availablePickerChannels("other", available), ["jira", "caldav"]);
  assert.deepEqual(availablePickerChannels("", available), available);
});


test("the rail's filter panel closes on a second press and when the page changes (2026-11-18 walk)", async () => {
  const { filterPanel } = await import("../src/feedFilters.js");
  const btn = { id: "filter" };
  let st = filterPanel({ at: null, on: "" }, { type: "press", target: btn, page: "" });
  assert.equal(st.at, btn, "the first press opens it");
  assert.equal(filterPanel(st, { type: "page", page: "" }), st, "the same page keeps it open");
  assert.equal(filterPanel(st, { type: "press", target: btn, page: "" }).at, null, "a second press on All items closes it");
  assert.equal(filterPanel(st, { type: "page", page: "reports" }).at, null, "going to Reports closes it");
  assert.equal(filterPanel(st, { type: "close" }).at, null, "a click outside or Esc closes it");
  const src = (await import("node:fs")).readFileSync(new URL("../src/FeedView.jsx", import.meta.url), "utf8");
  assert.match(src, /<FilterButton[^>]*page=\{navOn\}/, "the rail's filter is told which page is up");
});

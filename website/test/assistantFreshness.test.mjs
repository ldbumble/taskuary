import { test } from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("Assistant consumes full display and presentation revisions without patch-merging Current", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /\[displayRevision\(pile\)\]/);
  assert.match(view, /setPile\(\(p\) => refreshPilePresentation\(p, data\)\)/);
  assert.match(view, /const requestedCurrentKey = currentRef\.current\?\.key \|\| null/);
  assert.match(view, /if \(\(cur\?\.key \|\| null\) !== requestedCurrentKey\) return/);
  assert.match(view, /const refreshed = refreshCurrentPresentation\(cur, fresh\)/);
  assert.match(view, /currentRef\.current = refreshed/);
  assert.match(view, /const c = follows \? fresh : m\.card/);
  assert.doesNotMatch(view, /\{ \.\.\.cur, \.\.\.fresh \}/);
  assert.doesNotMatch(view, /\{ \.\.\.m\.card, \.\.\.fresh \}/);
});

test("selection freshness preserves explicit action advancement while background events never advance", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /landed\(await turn\(\{ mode: "next", key, \.\.\.navigation \}\)\)/);
  const events = view.slice(view.indexOf("if (data.events?.length)"), view.indexOf("// the item on the table is live"));
  assert.doesNotMatch(events, /setCurrent|setCurrentItem|surfaceRef|deferInChat/);
  assert.match(view, /deferInChat\(\(\) => surfaceRef\.current\?\.\(\), 500\)/);
  // explicit advancement after a confirmed proposal: only a success that settles the item on the table moves the walk (PW-125)
  assert.match(view, /if \(out\.settle && p\.key && p\.key === current\) \{ if \(p\.kind === "item\.settle"\) advance\(\); else await done\(null\); \}/);
});

test("lazy card reads are revision-bound and discard superseded responses", () => {
  const cards = read("assistantCards.jsx");
  assert.match(cards, /function FullText\(\{ mid, revision \}\)/);
  assert.match(cards, /\[mid, revision\]/);
  assert.match(cards, /\[card\?\.tid, card\?\.mid, card\?\.presentation_revision\]/);
  assert.match(cards, /\[card\.rid, card\.mid, card\.presentation_revision\]/);
  assert.match(cards, /\[open, card\.tid, card\.presentation_revision\]/);
  assert.ok((cards.match(/return \(\) => \{ live = false; \}/g) || []).length >= 4);
  assert.match(cards, /if \(!live\) return;/);
});

test("a refreshed backend draft does not overwrite text being edited locally", () => {
  const cards = read("assistantCards.jsx");
  assert.match(cards, /const value = text \?\? draft\(\)/);
  const replyStart = cards.indexOf("export function ReplyCard");
  const replyEnd = cards.indexOf("export function AgentCard", replyStart);
  const reply = cards.slice(replyStart, replyEnd);
  const refreshEffect = reply.slice(reply.indexOf("useEffect"), reply.indexOf("const action"));
  assert.match(reply, /setRv\(\(data\.data \|\| \[\]\)\.find/);
  assert.doesNotMatch(refreshEffect, /setText\(/);
});

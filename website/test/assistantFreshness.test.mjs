import { test } from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("Assistant consumes full display and presentation revisions without patch-merging Current", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /\[displayRevision\(pile\)\]/);
  assert.match(view, /setPile\(\(p\) => refreshPilePresentation\(p, data\)\)/);
  assert.match(view, /const requestedCurrentKey = currentRef\.current\?\.key \|\| null, requestedMoves = tableMoves\.current/);
  assert.match(view, /if \(\(cur\?\.key \|\| null\) !== requestedCurrentKey \|\| requestedMoves !== tableMoves\.current\) return/);
  // ...and every move of the table made here counts, so a read sent before one never takes it back (the latest click wins)
  assert.match(view, /if \(how !== "sync"\) tableMoves\.current \+= 1;/);
  assert.match(view, /const refreshed = refreshCurrentPresentation\(cur, fresh\)/);
  assert.match(view, /if \(newer \|\| refreshed !== cur\) putOnTable\(refreshed, "sync"\)/);
  assert.match(view, /const c = follows \? fresh : m\.card/);
  assert.doesNotMatch(view, /\{ \.\.\.cur, \.\.\.fresh \}/);
  assert.doesNotMatch(view, /\{ \.\.\.m\.card, \.\.\.fresh \}/);
});

test("selection freshness preserves explicit action advancement while background events never advance", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /try \{ data = await turn\(\{ mode: "next", key, leaving, \.\.\.navigation \}\); break; \}/);
  assert.match(view, /\n\s*landed\(data\);/);
  const events = view.slice(view.indexOf("if (data.events?.length)"), view.indexOf("// the item on the table is live"));
  assert.doesNotMatch(events, /setCurrent|setCurrentItem|putOnTable|surfaceRef|deferInChat/);
  // the grace is 500 ms unless the settle brought the rail back with it (pileAlong.test.mjs)
  assert.match(view, /deferInChat\(\(\) => surfaceRef\.current\?\.\(\), pile \|\| settled \? 120 : 500\)/);
  // explicit advancement after a confirmed proposal: only a success that settles the item on the table moves the walk (PW-125)
  assert.match(view, /const step = afterConfirm\(p, out, current\);/);
  assert.match(view, /if \(step === "advance"\) advance\(\);/);
  assert.match(view, /else if \(step === "settle"\) await done\(null\);/);
  assert.match(view, /else \{ if \(step === "offer"\) clearTable\(\); loadPile\(\); \}/);
});

test("lazy card reads are revision-bound and discard superseded responses", () => {
  const cards = read("assistantCards.jsx");
  assert.match(cards, /function FullText\(\{ mid, revision, report = null \}\)/);
  // one cached loader (useFetched): a newer revision refreshes quietly, a superseded answer is dropped by
  // `live`, and a grouped task is keyed on the TASK - a moved mid neither blanks nor refetches (2026-09-23)
  assert.match(cards, /\}, \[url, revision\]\);/);
  assert.match(cards, /useFetched\(none \? null : `\/api\/messages\/\$\{mid\}`, revision\)/);
  assert.match(cards, /useFetched\(card\?\.tid \? `\/api\/tasks\/\$\{card\.tid\}` : null, card\?\.presentation_revision\)/);
  // shared only within one revision, and only the url's newest read may land - joining any in-flight read
  // for the url let an older, slower answer draw over a newer revision (PW-106)
  assert.match(cards, /const key = `\$\{url\}\|\$\{revision \?\? ""\}`;/);
  assert.match(cards, /flight\.then\(\(\{ seq, d \}\) => \{ if \(live && seq === newest\.get\(url\) && d !== undefined\) setData\(d\); \}\)/);
  assert.match(cards, /\[card\.rid, card\.mid, card\.presentation_revision\]/);
  assert.ok((cards.match(/return \(\) => \{ live = false; \}/g) || []).length >= 4);
  assert.match(cards, /if \(!live\) return;/);
});

test("a refreshed backend draft does not overwrite text being edited locally", () => {
  const cards = read("assistantCards.jsx");
  assert.match(cards, /const value = text \?\? draft\(\)/);
  const replyStart = cards.indexOf("export function ReplyCard");
  const replyEnd = cards.indexOf("export function MeetingCard", replyStart);
  const reply = cards.slice(replyStart, replyEnd);
  const refreshEffect = reply.slice(reply.indexOf("useEffect"), reply.indexOf("const action"));
  assert.match(reply, /setRv\(\(data\.data \|\| \[\]\)\.find/);
  assert.doesNotMatch(refreshEffect, /setText\(/);
});

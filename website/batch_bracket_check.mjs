// Is a BATCH on the table readable where it is drawn?
//
//   node website/batch_bracket_check.mjs <url>     # against a `taskuary --demo --port N` server
//
// The bracket spans its members where they already sit: it adds no height and moves no row, which is
// exactly what makes it easy to break. Two things measured in a real browser, because nothing in
// pytest or node --test draws anything:
//
//   1. the "on the table · N fyi" pill is INSIDE the rail, not clipped by its edge;
//   2. the first member's card is not covered at the top - by the bracket's own edge, or by the band
//      heading above it, which is sticky and opaque (z-index 3).
//
// Exits 1 with the offending boxes, 2 when no batch could be put on the table.
import { launch } from "./browser.mjs";

const url = process.argv[2] || "http://127.0.0.1:7913/";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const boxes = (page) => page.evaluate(() => {
  const rect = (el) => { const b = el.getBoundingClientRect(); return { top: +b.top.toFixed(1), left: +b.left.toFixed(1), right: +b.right.toFixed(1), bottom: +b.bottom.toFixed(1), width: +b.width.toFixed(1), height: +b.height.toFixed(1) }; };
  const bracket = document.querySelector(".tq-pile-batch");
  if (!bracket) return null;
  const pill = bracket.querySelector("b");
  const members = [...document.querySelectorAll(".tq-pile-row.inbatch .card")];
  // the scrolling column the rail lives in - whatever actually clips
  let clip = bracket.parentElement;
  while (clip && clip !== document.body && getComputedStyle(clip).overflow === "visible") clip = clip.parentElement;
  const head = bracket.closest(".tq-pile-band")?.querySelector(".tq-pile-head");
  return {
    bracket: rect(bracket), pill: pill ? { ...rect(pill), text: pill.textContent } : null,
    clip: { ...rect(clip), overflow: getComputedStyle(clip).overflow, tag: clip.className || clip.tagName },
    head: head ? { ...rect(head), z: getComputedStyle(head).zIndex } : null,
    members: members.map((m) => ({ ...rect(m), title: m.querySelector("b")?.textContent?.slice(0, 36) || "" })),
  };
});

// walk the pipe until the assistant puts a batch up, pressing whatever the card offers
const nextTurn = (page) => page.evaluate(() => {
  const labels = ["All read, next", "Next", "Read it and move on"];
  const b = [...document.querySelectorAll("button")].find((x) => labels.includes(x.textContent.trim()));
  if (b) { b.click(); return b.textContent.trim(); }
  return null;
});

const browser = await launch();
const page = await browser.newPage(); await page.setViewport({ width: 1440, height: 980 });
try {
  await page.goto(url, { waitUntil: "networkidle2" });
  await wait(2500);
  // the rail lives on the Assistant tab; a fresh page lands on the Timeline
  await page.evaluate(() => {
    const tab = [...document.querySelectorAll("button, a, [role=tab]")].find((x) => x.textContent.trim() === "Assistant");
    if (tab) tab.click();
  });
  await wait(2500);
  let m = await boxes(page);
  for (let i = 0; !m && i < 12; i++) {
    const pressed = await nextTurn(page);
    if (!pressed) break;
    await wait(1400);
    m = await boxes(page);
  }
  if (!m) { console.error("no batch on the table after walking the pipe - nothing to measure"); process.exit(2); }

  const bad = [];
  const first = m.members[0], last = m.members[m.members.length - 1];
  if (m.pill) {
    if (m.pill.right > m.clip.right) bad.push(`the pill is clipped on the right: it ends at ${m.pill.right}, the column at ${m.clip.right}`);
    if (m.pill.left < m.clip.left) bad.push(`the pill starts left of the column (${m.pill.left} < ${m.clip.left})`);
    if (m.pill.bottom > m.clip.bottom) bad.push(`the pill hangs below the column (${m.pill.bottom} > ${m.clip.bottom})`);
  } else bad.push("the bracket has no pill at all - nothing says what is on the table");
  if (first && first.top < m.bracket.top) bad.push(`the first member's card starts ABOVE the bracket (${first.top} < ${m.bracket.top}): its top edge is covered`);
  if (first && m.head && first.top < m.head.bottom) bad.push(`the band heading covers the first member (heading ends ${m.head.bottom}, card starts ${first.top})`);
  if (last && last.bottom > m.bracket.bottom) bad.push(`the last member hangs out of the bracket (${last.bottom} > ${m.bracket.bottom})`);

  console.log(JSON.stringify(m, null, 1));
  if (bad.length) { console.error("\n" + bad.map((b) => "  x " + b).join("\n")); process.exit(1); }
  console.log(`\n  ok - ${m.members.length} members bracketed, pill "${m.pill.text}" inside the column`);
  process.exit(0);
} finally { await browser.close(); }

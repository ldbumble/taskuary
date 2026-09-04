// Does the PIPE still sit on the Timeline's own lines? Its rows are the top of the same rail, ranked
// instead of dated, so a pile row's card must share a Timeline row's left and right edges exactly (the
// owner, 2026-09-03: "the same exact size as the timeline"). Nothing in pytest or node --test can see
// that: the two are drawn by different code (AssistantView's Pile, FeedView's rows) against one CSS.
//
//   node website/pipe_geometry_check.mjs <url>          # against a `taskuary --demo --port N` server
//
// Exits non-zero and prints the offending rows when any pile card is off the Timeline's edges.
import { launch } from "./browser.mjs";

const url = process.argv[2] || "http://127.0.0.1:7899/";
const SLACK = 1;             // px: subpixel rounding
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const measure = (page) => page.evaluate(() => {
  const ref = document.querySelector(".tqRow [data-tq-keep]");
  if (!ref) return { error: "no Timeline row on the page" };
  const rb = ref.getBoundingClientRect();
  return {
    ref: { left: rb.left, right: rb.right },
    rows: [...document.querySelectorAll(".tq-pile-row .card")].map((c) => {
      const b = c.getBoundingClientRect();
      return { title: c.querySelector("b")?.textContent?.slice(0, 40) || "", left: b.left, right: b.right, height: b.height };
    }),
  };
});

const browser = await launch();
const page = await browser.newPage(); await page.setViewport({ width: 1440, height: 900 });
try {
  await page.goto(url, { waitUntil: "networkidle2" });
  await wait(2500);                                       // the pile lands and slides into place
  const m = await measure(page);
  if (m.error) { console.error(m.error); process.exit(2); }
  if (!m.rows.length) { console.log("pile is empty - nothing to measure"); process.exit(0); }
  const off = m.rows.filter((r) => Math.abs(r.left - m.ref.left) > SLACK || Math.abs(r.right - m.ref.right) > SLACK);
  for (const r of off) console.error(`off the Timeline's edges: "${r.title}" left ${r.left.toFixed(1)} (want ${m.ref.left.toFixed(1)}) right ${r.right.toFixed(1)} (want ${m.ref.right.toFixed(1)})`);
  console.log(`${m.rows.length} pile rows, ${off.length} off the Timeline's edges`);
  process.exit(off.length ? 1 : 0);
} finally { await browser.close(); }

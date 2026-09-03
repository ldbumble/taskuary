// Does the PIPE still look like a funnel emptying? The rows are supposed to sit ON the walls - the
// whole point of the shape (the owner, 2026-09-03: "the outside edges of the timeline items shoud
// match the width to the edge of the funnel... that's the whole idea so it looks like it's emptying").
// Nothing in pytest or node --test can see that: the inset is computed from the DOM's own boxes, and
// the bug it replaced (measuring the visible height of a SCROLLING column instead of the wall's own
// height) only showed once the pile was long enough to scroll.
//
//   node website/pipe_geometry_check.mjs <url>          # against a `taskuary --demo --port N` server
//
// Exits non-zero and prints the offending rows when any row is off its wall, so it can gate a change.
import { launch } from "./browser.mjs";

const url = process.argv[2] || "http://127.0.0.1:7899/";
const TAPER = 0.07;          // must match .tq-pipe-walls' clip-path and AssistantView's WALL
const SLACK = 4;             // px: rounding on the taper, and the row's own border
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// each row's left edge against the wall's taper at that row's own height, in the wall's own space
const measure = (page, taper) => page.evaluate((t) => {
  const body = document.querySelector(".tq-pipe-body"), wall = document.querySelector(".tq-pipe-walls");
  if (!body || !wall) return { error: "no pipe on the page" };
  const wb = wall.getBoundingClientRect();
  return {
    scrolled: body.scrollHeight - body.clientHeight,
    rows: [...document.querySelectorAll(".tq-pipe-row")].map((r) => {
      const rb = r.getBoundingClientRect();
      const y = Math.min(1, Math.max(0, (rb.top + rb.height / 2 - wb.top) / wb.height));
      const ring = 0;      // the highlight is an INSET ring now: every row is exactly the same width
      // ...and the task's number must survive the narrowing: it was the first thing clipped off
      const ref = r.querySelector(".tq-pipe-ref");
      const clipped = ref ? Math.round(rb.right - 6 - ref.getBoundingClientRect().right) < 0 : false;
      return { text: r.innerText.replace(/\s+/g, " ").slice(0, 30), clipped,
               off: Math.round(rb.left - (wb.left + t * wb.width * y)) - ring,
               right: Math.round((wb.right - t * wb.width * y) - rb.right) - ring };
    }),
  };
}, taper);

const bad = (m) => m.rows.filter((r) => Math.abs(r.off) > SLACK || Math.abs(r.right) > SLACK || r.clipped);

const browser = await launch();
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error" && !/403|404/.test(m.text())) errors.push(`console: ${m.text().slice(0, 140)}`); });

let failed = 0;
// twice: a tall column (the pile fits) and a short one (it has to scroll, which is where it broke)
for (const view of [{ width: 1440, height: 900 }, { width: 1440, height: 420 }]) {
  await page.setViewport(view);
  await page.goto(url, { waitUntil: "networkidle0" });
  await wait(7000);
  const at = `${view.width}x${view.height}`;
  const m = await measure(page, TAPER);
  if (m.error) { console.log(`FAIL ${at}: ${m.error}`); failed += 1; continue; }
  if (!m.rows.length) { console.log(`FAIL ${at}: the pipe drew no rows - is the demo seeded?`); failed += 1; continue; }
  // ...and again at the bottom of the scroll, where the taper is tightest
  await page.evaluate(() => { const b = document.querySelector(".tq-pipe-body"); b.scrollTop = b.scrollHeight; });
  await wait(600);
  const low = await measure(page, TAPER);
  for (const [where, got] of [["as it opens", m], ["scrolled to the mouth", low]]) {
    const off = bad(got);
    console.log(`${off.length ? "FAIL" : "ok  "} ${at} ${where}: ${got.rows.length} rows, `
      + `${got.scrolled ? `${got.scrolled}px of overflow` : "no overflow"}`
      + (off.length ? `\n     ${off.map((r) => `${r.off > 0 ? "+" : ""}${r.off}/${r.right}${r.clipped ? " TQ CLIPPED" : ""} ${r.text}`).join("\n     ")}` : ""));
    failed += off.length ? 1 : 0;
  }
}
if (errors.length) { console.log(`FAIL page errors:\n  ${errors.join("\n  ")}`); failed += 1; }
await browser.close();
console.log(failed ? `\n${failed} check(s) failed` : "\nthe pipe's rows sit on its walls");
process.exit(failed ? 1 : 0);

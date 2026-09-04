// Does the PIPE still sit on the Timeline's own lines? Its rows are the top of the same rail, ranked
// instead of dated, so a pile row's card must share a Timeline row's left edge and width exactly (the
// owner, 2026-09-03: "the same exact size as the timeline"). Nothing in pytest or node --test can see
// that: the two are drawn by different code (AssistantView's Pile, FeedView's rows) against one CSS.
//
//   node website/pipe_geometry_check.mjs <url>          # against a `taskuary --demo --port N` server
//
// The two are no longer on screen together. Unread IS the pile now and draws no `.tqRow` at all;
// All and Needs me are the chronological lists and draw no pile (FeedView: "Unread alone owns the
// conversational walk"). So this measures the pile on unread, switches the rail to all, and measures
// a Timeline row there - same rail, same viewport, so the edges must still line up. Reading only the
// landing view is what made this check exit 2 on "no Timeline row" and stop testing anything.
//
// Exits 1 and prints the offending rows when any pile card is off the Timeline's edges, 2 when there
// was nothing to measure against.
import { launch } from "./browser.mjs";

const url = process.argv[2] || "http://127.0.0.1:7899/";
const SLACK = 1;             // px: subpixel rounding
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// the pile, as the unread rail draws it
const pileCards = (page) => page.evaluate(() =>
  [...document.querySelectorAll(".tq-pile-row .card")].map((c) => {
    const b = c.getBoundingClientRect();
    return { title: c.querySelector("b")?.textContent?.slice(0, 40) || "", left: b.left, width: b.width };
  }));

// FilterPills renders plain Boxes with no class of their own, so the strip is found by the pills it
// holds: exactly three children reading unread / all / needs me. Matching a child by prefix instead
// finds the WRAPPER around every filter group - whose second child is the "all kinds" source picker,
// so the click landed there and the view never changed.
const switchView = (page, want) => page.evaluate((label) => {
  const labels = (el) => [...el.children].map((c) => c.textContent.trim());
  const strip = [...document.querySelectorAll("div")].find((el) => {
    const t = labels(el);
    return t.length === 3 && t.includes("all") && t.includes("needs me") && t.some((x) => x.startsWith("unread"));
  });
  if (!strip) return "no unread/all/needs me view switcher on the page";
  const pill = [...strip.children].find((c) => c.textContent.trim() === label);
  if (!pill) return `the view switcher has no "${label}" pill`;
  pill.click();
  return "";
}, want);

// ...and one Timeline row on the all view, which is what the pile has to match
const timelineCard = (page) => page.evaluate(() => {
  const ref = document.querySelector(".tqRow [data-tq-keep]");
  if (!ref) return null;
  const b = ref.getBoundingClientRect();
  return { left: b.left, width: b.width };
});

const browser = await launch();
const page = await browser.newPage(); await page.setViewport({ width: 1440, height: 900 });
try {
  await page.goto(url, { waitUntil: "networkidle2" });
  await wait(2500);                                       // the pile lands and slides into place
  const rows = await pileCards(page);
  if (!rows.length) { console.log("pile is empty - nothing to measure"); process.exit(0); }

  const failed = await switchView(page, "all");
  if (failed) { console.error(failed); process.exit(2); }
  try { await page.waitForSelector(".tqRow [data-tq-keep]", { timeout: 8000 }); }
  catch { console.error("switched to all, but it drew no Timeline row to measure against"); process.exit(2); }
  await wait(600);                                        // the rows settle after the view swap
  const ref = await timelineCard(page);
  if (!ref) { console.error("no Timeline row on the all view"); process.exit(2); }

  const off = rows.filter((r) => Math.abs(r.left - ref.left) > SLACK || Math.abs(r.width - ref.width) > SLACK);
  for (const r of off) console.error(`off the Timeline's edges: "${r.title}" left ${r.left.toFixed(1)} (want ${ref.left.toFixed(1)}) width ${r.width.toFixed(1)} (want ${ref.width.toFixed(1)})`);
  console.log(`${rows.length} pile rows measured against the Timeline (left ${ref.left.toFixed(1)}, width ${ref.width.toFixed(1)}), ${off.length} off`);
  process.exit(off.length ? 1 : 0);
} finally { await browser.close(); }

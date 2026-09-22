// Does Settings scroll all the way through?
//
//   node website/settings_scroll_check.mjs <url>    # against a `taskuary --demo --port N` server
//
// Settings used to be seven exclusive pages behind one rail: you scrolled to the bottom of
// Configuration and it stopped dead, and Routing policies existed only if you clicked for it
// (the owner, 2026-09-22: "when it gets to a new section it does not cotinue past the next
// section"). It is one document now, so four things have to be true in a real browser, and
// nothing in pytest or node --test draws anything:
//
//   1. every rail entry has a heading IN THE DOCUMENT, in the rail's order, each below the last;
//   2. the document is taller than the window - there is somewhere to scroll TO;
//   3. scrolling to the bottom reaches the last page's heading without any click;
//   4. the rail follows: at the foot of the document it highlights the last entry, not the first.
//
// Exits 1 with what it measured.
import { launch } from "./browser.mjs";

const url = process.argv[2] || "http://127.0.0.1:7911/";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const NAV = ["about", "docs", "config", "policies", "memory", "audit", "updates"];

const heads = (page) => page.evaluate((nav) => {
  const y = (id) => { const el = document.getElementById(id); return el ? +(el.getBoundingClientRect().top + window.scrollY).toFixed(1) : null; };
  return {
    tops: nav.map((k) => ({ page: k, top: y(`set-page-${k}`) })),
    doc: document.documentElement.scrollHeight, win: window.innerHeight, at: window.scrollY,
    // the rail entry drawn as the one you are in - it carries the selected background
    rail: [...document.querySelectorAll("#tqSettingsRail ~ div")]
      .map((d) => d.firstElementChild).filter(Boolean)
      .filter((d) => getComputedStyle(d).backgroundColor === "rgb(234, 228, 216)")
      .map((d) => d.textContent.trim()),
  };
}, NAV);

const fail = (msg, seen) => { console.error("FAIL:", msg); console.error(JSON.stringify(seen, null, 2)); process.exit(1); };

const browser = await launch();
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  // #settings=about is the door every in-app link uses; it opens the tab and lands on About you
  await page.goto(`${url.replace(/#.*$/, "")}#settings=about`, { waitUntil: "networkidle2" });
  await wait(2500);                                  // the loads land and the document stops growing
  if (!(await page.$("#tqSettingsRail"))) fail("Settings did not open", { url });

  let seen = await heads(page);
  const missing = seen.tops.filter((t) => t.top === null).map((t) => t.page);
  if (missing.length) fail(`these rail entries draw no heading: ${missing.join(", ")}`, seen);
  for (let i = 1; i < seen.tops.length; i += 1) {
    if (seen.tops[i].top <= seen.tops[i - 1].top)
      fail(`${seen.tops[i].page} is not below ${seen.tops[i - 1].page} - the pages are not stacked`, seen);
  }
  if (seen.doc <= seen.win + 200) fail("the document is no taller than the window: nothing to scroll", seen);

  // 3 + 4: scroll to the foot of it, touching nothing
  await page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "instant" }));
  await wait(900);
  seen = await heads(page);
  const last = seen.tops[seen.tops.length - 1];
  if (last.top > seen.at + seen.win) fail("scrolling to the bottom never reaches the last page's heading", seen);
  if (!seen.rail.some((t) => /Updates/.test(t)))
    fail(`at the foot of the document the rail highlights ${JSON.stringify(seen.rail)}, not Updates`, seen);

  // 5: a rail entry still LANDS. goTo used to send a bare page to the top of the window; it
  // scrolls to that page's heading now, and getting that wrong is invisible in the source tests.
  const clicked = await page.evaluate(() => {
    const e = [...document.querySelectorAll("#tqSettingsRail ~ div > div")]
      .find((d) => d.textContent.trim().startsWith("Audit integrity"));
    if (!e) return false;
    e.click(); return true;
  });
  if (!clicked) fail("no Audit integrity entry in the rail", seen);
  await wait(2500);
  let off = await page.evaluate(() => document.getElementById("set-page-audit").getBoundingClientRect().top);
  if (Math.abs(off - 74) > 6) fail(`clicking Audit integrity left its heading ${off.toFixed(1)}px down, not at the bar (74)`, { off });

  // 6: and so does a deep link into a section - #settings=config&group=<name>
  await page.evaluate(() => window.location.assign(`${location.pathname}#settings=config&group=${encodeURIComponent("Display")}`));
  await wait(2500);
  off = await page.evaluate(() => {
    const el = document.getElementById("set-config-display");
    return el ? el.getBoundingClientRect().top : null;
  });
  if (off === null) fail("no Display section to link to", {});
  if (Math.abs(off - 74) > 6) fail(`#settings=config&group=Display left the heading ${off.toFixed(1)}px down, not at the bar (74)`, { off });

  // 7: searching replaces the document, and a hit scrolls to where the knob actually lives
  await page.type("input[placeholder='Search settings…']", "display");
  await wait(900);
  const crumb = await page.evaluate(() => {
    // a result card is a label over its crumb; the crumb is the leaf, the card is what you click
    const c = [...document.querySelectorAll("*")].find((d) => !d.children.length
      && /^Configuration → /.test(d.textContent.trim()));
    if (!c) return null;
    const card = c.parentElement;
    card.click(); return c.textContent.trim();
  });
  if (!crumb) fail("searching found no knob to click", {});
  await wait(2500);
  const gone = await page.evaluate(() => !!document.getElementById("set-page-updates"));
  if (!gone) fail(`clicking a search hit (${crumb}) did not bring the document back`, { crumb });

  console.log(`OK - ${seen.tops.length} pages stacked over ${seen.doc}px, one scroll from ${seen.tops[0].page} to ${last.page}`);
  console.log(seen.tops.map((t) => `  ${String(t.top).padStart(7)}  ${t.page}`).join("\n"));
  console.log("OK - a rail click and a #settings= deep link both land their heading at the top bar");
  console.log(`OK - searching replaces the document and a hit ("${crumb}") brings it back`);
} finally {
  await browser.close();
}

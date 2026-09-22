// The tab pictures the setup walk shows, one run, one viewport, cropped to where each page ends.
//   npm exec --yes --package=node@22 -- node website/capture-walk.mjs
//
// These are NOT the README's shots. Those are narrative crops at mixed sizes on GitHub raw URLs,
// and an install must not fetch its own onboarding over the network. These ship inside the wheel:
// vite copies public/ into the build, so they land in taskuary/web/walk/ and serve at /walk/<key>.png.
//
// Server startup follows capture-readme.mjs (host 127.0.0.1, port 0, mode "demo") rather than the
// original sketch's fixed port - a fixed port collides with whatever else is listening on this box.
//
// Re-run this when a tab's layout changes. That is the whole cost of shipping pictures, and it is
// one command rather than nine judgement calls - which is why it is one script and not nine.
import { createServer } from "vite";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const out = path.join(root, "website/public/walk");
await mkdir(out, { recursive: true });

// key -> the tab label to click. The walk's stop keys, so a rename breaks here rather than silently
// shipping a picture of the wrong tab.
// ...and a stop whose page is a SECTION of another tab names the rail entry to click after it.
// Docs stopped being a tab of its own; the script refused to shoot it rather than shipping a
// picture of whatever was showing, which is how the walk's own dead "Open Docs" button was found.
const TABS = [
  // Two stops live on the same tab, so each names its own section AND something only that
  // section shows. Clicking a tab you are already on does not remount it and the deep link is
  // read once, at mount - so without this the Docs hash was still in force and settings.png
  // came back a second picture of SOUL.md.
  ["connections", "Connections"],
  ["docs", "Settings", "settings=docs", "SOUL.md"],
  ["settings", "Settings", "settings=config", "how the funnel behaves"],
  ["board", "Board"], ["tasks", "Tasks"],
  ["reports", "Reports"], ["assistant", "Assistant"], ["hub", "Hub"],
];

const server = await createServer({ root: path.join(root, "website"), mode: "demo",
  server: { host: "127.0.0.1", port: 0 }, logLevel: "warn" });
await server.listen();
const origin = `http://127.0.0.1:${server.httpServer.address().port}`;

const b = await launch();
try {
  const p = await b.newPage();
  // One viewport for all nine. The card is ~560px wide, so 1280 at 2x lands a crisp image that is
  // not a 4MB page in a wheel.
  await p.setViewport({ width: 1280, height: 860, deviceScaleFactor: 2 });
  await p.goto(`${origin}/`, { waitUntil: "networkidle0", timeout: 120000 });
  await p.evaluate(() => document.fonts.ready);

  // Scoped to the nav strip and picking the leaf-most match: the Assistant pill wraps an icon plus
  // a text node (childElementCount 1, not 0), so a bare "no children" filter clicks nothing for
  // it, and an unscoped text match can hit the word elsewhere on the page (a doc body, a task
  // title). The Review pill also carries a pending-count badge appended to its text ("Review3"),
  // stripped by `norm` below - without it this matched nothing and silently left the shot on the
  // prior tab. Returns whether it actually found something to click, so a miss can fail the run
  // instead of silently shipping a picture of whatever tab was showing before.
  const clickTab = (label) => p.evaluate((l) => {
    const norm = (s) => s.trim().replace(/[\d+]+$/, "").trim();
    const els = [...document.querySelectorAll("#tqTopNav div,#tqTopNav button,#tqTopNav span")]
      .filter((d) => norm(d.textContent) === l);
    els.sort((a, c) => a.querySelectorAll("*").length - c.querySelectorAll("*").length);
    if (!els[0]) return false;
    els[0].click();
    return true;
  }, label);

  for (const [key, label, railEntry, proof] of TABS) {
    // A section deep link is read ONCE, when the page mounts, and cleared as it is read - so it has
    // to be in the bar BEFORE the tab opens. Setting it afterwards left the shot on whatever section
    // the page opens by default, which is how docs.png came back a second picture of About you.
    if (railEntry) {
      // ...and the page has to MOUNT with it: step off the tab first, so the link is read.
      await clickTab("Board");
      await new Promise((r) => setTimeout(r, 600));
      await p.evaluate((h) => { window.location.hash = h; }, railEntry);
    }
    const clicked = await clickTab(label);
    // This is exactly how review.png first came out a duplicate of tasks.png: the click missed,
    // nothing threw, and the loop screenshotted whatever tab was already showing. A failed run is
    // far better than a wrong picture that ships silently.
    if (!clicked) throw new Error(`no nav control matched "${label}" - the tab was renamed, or its label grew something norm() does not strip`);
    await new Promise((r) => setTimeout(r, 2200));          // let the tab's own fetches land
    if (railEntry) {
      await new Promise((r) => setTimeout(r, 2500));   // the page's own rows arrive from the server
      // ...and it is checked by what the PAGE says, not by the hash, which the reader wipes: the
      // rail entry it landed on has to be the one asked for.
      const landed = await p.evaluate((w) => document.body.innerText.includes(w), proof);
      if (!landed) {
        const shown = await p.evaluate(() => document.body.innerText.slice(0, 300).replace(/\s+/g, " "));
        throw new Error(`"${label}" opened, but ${railEntry} did not land - no "${proof}" on the page.
  it shows: ${shown}`);
      }
    }
    // The demo raises a hand every few seconds ("TQ-0004 · coder stopped and is waiting on you") and
    // the toast landed in every one of the nine pictures, bottom right, as if it were part of the tab.
    // A shot of the Settings tab is not the place to learn what a toast looks like (2026-09-18).
    await p.evaluate(() => document.querySelectorAll(".MuiSnackbar-root").forEach((el) => { el.style.display = "none"; }));
    // ...and the shot STOPS WHERE THE PAGE DOES. A fixed 760px window is the viewport, not the tab:
    // About you is 600px of content and the rest of the frame was the page's own background, so the
    // card - which zooms 2x into the top-left corner - spent a third of itself on nothing (the owner,
    // 2026-09-22: "the image only takes up part of it"). The ink is measured here instead: every
    // painted box narrower than the viewport, which skips the full-width wrappers.
    const inkBottom = await p.evaluate(() => {
      const page = getComputedStyle(document.body).backgroundColor;
      let bottom = 0;
      for (const el of document.querySelectorAll("body *")) {
        const r = el.getBoundingClientRect();
        if (r.width < 4 || r.height < 4 || r.bottom < 44 || r.width >= 1279) continue;
        const cs = getComputedStyle(el);
        if (cs.visibility === "hidden" || cs.opacity === "0") continue;
        const paints = (cs.backgroundColor !== "rgba(0, 0, 0, 0)" && cs.backgroundColor !== page)
          || cs.borderTopWidth !== "0px" || cs.borderLeftWidth !== "0px"
          || [...el.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim());
        if (paints) bottom = Math.max(bottom, Math.min(r.bottom, 804));
      }
      return bottom;
    });
    const height = Math.max(380, Math.min(760, Math.ceil(inkBottom - 44 + 12)));
    await p.screenshot({ path: path.join(out, `${key}.png`),
                         clip: { x: 0, y: 44, width: 1280, height } });
    console.log(`walk shot ${key} ok - 1280x${height} (the page ends at ${Math.round(inkBottom)})`);
  }
  console.log(`${TABS.length} walk shots in ${out}`);
} finally {
  // A goto timeout or a failed screenshot must not leave a headless Chrome running and this port
  // bound - that is what breaks the NEXT run, for a completely unrelated reason.
  await b.close();
  await server.close();
}

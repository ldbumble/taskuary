// The nine tab pictures the setup walk shows, one run, one viewport, one crop.
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
const TABS = [
  ["connections", "Connections"], ["docs", "Docs"], ["settings", "Settings"],
  ["board", "Board"], ["tasks", "Tasks"], ["review", "Review"],
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

  for (const [key, label] of TABS) {
    const clicked = await clickTab(label);
    // This is exactly how review.png first came out a duplicate of tasks.png: the click missed,
    // nothing threw, and the loop screenshotted whatever tab was already showing. A failed run is
    // far better than a wrong picture that ships silently.
    if (!clicked) throw new Error(`no nav control matched "${label}" - the tab was renamed, or its label grew something norm() does not strip`);
    await new Promise((r) => setTimeout(r, 2200));          // let the tab's own fetches land
    // The demo raises a hand every few seconds ("TQ-0004 · coder stopped and is waiting on you") and
    // the toast landed in every one of the nine pictures, bottom right, as if it were part of the tab.
    // A shot of the Settings tab is not the place to learn what a toast looks like (2026-09-18).
    await p.evaluate(() => document.querySelectorAll(".MuiSnackbar-root").forEach((el) => { el.style.display = "none"; }));
    await p.screenshot({ path: path.join(out, `${key}.png`),
                         clip: { x: 0, y: 44, width: 1280, height: 760 } });
    console.log(`walk shot ${key} ok`);
  }
  console.log(`nine walk shots in ${out}`);
} finally {
  // A goto timeout or a failed screenshot must not leave a headless Chrome running and this port
  // bound - that is what breaks the NEXT run, for a completely unrelated reason.
  await b.close();
  await server.close();
}

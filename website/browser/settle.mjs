// WAIT FOR QUIET, NEVER A FIXED SLEEP: resolves once the page has made no /api request for `quiet` ms (counting the requests as they
// are issued, not as they answer), so a test that counts reads counts the whole of an opening or a turn whatever the machine's speed.
export function quietWatch(page) {
  let last = Date.now(), open = 0;
  page.on("request", (r) => { if (new URL(r.url()).pathname.startsWith("/api/")) { open++; last = Date.now(); } });
  const done = (r) => { if (new URL(r.url()).pathname.startsWith("/api/")) { open = Math.max(0, open - 1); last = Date.now(); } };
  page.on("requestfinished", done); page.on("requestfailed", done);
  return (quiet = 2500, timeout = 60000) => new Promise((resolve, reject) => {
    const t0 = Date.now(), id = setInterval(() => {
      if (!open && Date.now() - last >= quiet) { clearInterval(id); resolve(); }
      else if (Date.now() - t0 > timeout) { clearInterval(id); reject(new Error("the page never went quiet")); }
    }, 100);
  });
}

/* EVERY STATE THE CHAT WAS IN, NOT EVERY 100 MS OF IT (CI, 2026-11-10: a sample 5 s after the press found nothing under the owner's line - the
   turn's head was swapped, not filled in). Installed in the page at the press: after every DOM change React commits (a MutationObserver) and on
   every painted frame, the chat is read with `check` - '' when right, else why - until the answer stands; each wrong state is kept with its ms
   from the press. `check(said)` runs in the page and must be self-contained. */
export async function watchTurn(page, said, answer, check) {
  await page.evaluate((said, answer, src) => {
    const check = new Function(`return (${src})`)(), t0 = performance.now(), w = (window.__tqWatch = { bad: [], first: null, done: false, n: 0 });
    const look = () => {
      if (w.done) return;
      const pane = document.querySelector("[data-tq-task-page]");
      if (new RegExp(answer).test(pane?.innerText || "")) { w.done = true; obs.disconnect(); return; }
      const why = check(said), at = Math.round(performance.now() - t0);
      w.n += 1;
      if (!why && w.first == null) w.first = at;
      // ...with what the chat's foot held then: the rows under his line, by their marks
      const foot = () => [...(document.querySelector("[data-tq-task-page] .tq-aui-viewport")?.children || [])].slice(-4)
        .map((e) => `${e.className}`.split(" ").filter((c) => c.startsWith("tq-")).join(".") + `[${(e.innerText || "").slice(0, 40).replace(/\s+/g, " ")}]`).join(" | ");
      if (why && (!w.bad.length || w.bad.at(-1)[1] !== why)) w.bad.push([at, why.slice(0, 300), foot()]);
    };
    const obs = new MutationObserver(look);
    obs.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
    const frame = () => { look(); if (!w.done) requestAnimationFrame(frame); };
    requestAnimationFrame(frame);
  }, said, answer.source, check.toString());
}
export const turnWatched = async (page, timeout = 60000) => {
  await page.waitForFunction(() => window.__tqWatch?.done, { timeout, polling: 100 });
  return page.evaluate(() => window.__tqWatch);
};
// ...the turn he asked for, under his line as its own head (the owner, 2026-11-10: "it should show agent and time and how long it's running
// rightg away. under it it can spin like normal"): his bubble once, a running head under it, nothing of the turn's above it, no "Working" words
export function headUnderLine(said) {
  const pane = document.querySelector("[data-tq-task-page]");
  if (!pane) return "no task page";
  const vp = pane.querySelector(".tq-aui-viewport");
  if (/Working on this|Working on it|Working…|Starting…|Continuing…/.test(vp?.innerText || "")) return "the old working words";
  const mine = [...pane.querySelectorAll(".tq-aui-user-bubble")].filter((e) => e.innerText.includes(said));
  if (mine.length !== 1) return `his line is drawn ${mine.length} times`;
  const bottom = mine[0].getBoundingClientRect().bottom, stream = mine[0].closest(".tq-aui-viewport") || pane;
  const turn = [...stream.querySelectorAll("[data-tq-run-clock], [data-tq-pending-turn], .tq-aui-thinking, [data-tq-working]")];
  const above = turn.find((e) => e.getBoundingClientRect().top < bottom - 1);
  if (above) return `above his line: ${above.outerHTML.slice(0, 160)}`;
  return turn.some((e) => e.matches("[data-tq-run-clock]") && /ran \d/.test(e.innerText) && e.getBoundingClientRect().top >= bottom - 1) ? ""
    : `no running head: ${turn.map((e) => e.outerHTML.slice(0, 80)).join(" | ") || "nothing"}`;
}

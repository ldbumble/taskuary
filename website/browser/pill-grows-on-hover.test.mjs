import assert from "node:assert/strict";
import test from "node:test";
import path from "node:path";
import { mkdir } from "node:fs/promises";

import { startHarness } from "./harness.mjs";

/* A TRIAL: THE PILL GROWS UNDER THE MOUSE (the owner, 2026-10-31: "try it"). Hovered, the chat pill in the corner grows taller over its
   own corner - never wider (the owner, 2026-10-31: "size of the chat should never change"), the open window's own width, so a press on it
   changes no width; the bar beside it and the canvas do not move, and it never covers the bar's buttons. A moment after the
   mouse leaves it is the pill again; a mouse passing across does not flicker it. It never shrinks while it is open (focus), nor while words
   are typed in it. TASKUARY_HOVERBOX_SHOTS=<folder> keeps a frame of each state and a frame sequence of the grow and the shrink. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const shots = process.env.TASKUARY_HOVERBOX_SHOTS || "";

test("the chat pill grows under the mouse, shrinks after it leaves, and never with focus or words in it", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1366, height: 768, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  if (shots) await mkdir(shots, { recursive: true });
  const shot = (n) => shots && page.screenshot({ path: path.join(shots, `${n}.png`) });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const inv = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  await page.waitForSelector(".tq-dock [data-tq-row] [data-tq-next]", { timeout: 20000 });
  await sleep(2000);
  const geo = () => page.evaluate(() => {
    const r = (e) => { const b = e.getBoundingClientRect(); return { l: Math.round(b.left), r: Math.round(b.right), t: Math.round(b.top), b: Math.round(b.bottom), w: Math.round(b.width), h: Math.round(b.height) }; };
    const box = document.querySelector(".tq-chat-unit > .tq-compose-box"), dock = document.querySelector(".tq-compose > .tq-dock");
    const btns = [...document.querySelectorAll(".tq-dock button")].filter((b) => b.offsetParent).map(r);
    return { box: r(box), field: r(box.querySelector(".tq-compose-field")), dock: dock?.offsetParent ? r(dock) : null, btnR: Math.max(0, ...btns.map((b) => b.r)),
      canvas: r(document.querySelector(".tq-asst-col")), grow: box.hasAttribute("data-tq-grow"), open: box.hasAttribute("data-tq-open") };
  });
  const at = async (sel) => page.$eval(sel, (e) => { const b = e.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; });
  const away = () => page.mouse.move(300, 300);

  const rest = await geo();
  assert.ok(!rest.grow && !rest.open && rest.field.h <= 46, `at rest the one-line pill ${JSON.stringify(rest)}`);
  await shot("1-rest");

  // ...hovered (on the pill's middle, off its buttons): wider and taller over its own corner, nothing else moves
  const [x, y] = await at(".tq-chat-unit > .tq-compose-box textarea");
  const frames = [];
  const film = async (tag, n) => { if (!shots) return; const c = { x: 0, y: 768 - 200, width: 1366, height: 200 };
    for (let i = 0; i < n; i++) { const p = path.join(shots, `${tag}-${String(i).padStart(2, "0")}.png`); await page.screenshot({ path: p, clip: c }); frames.push(p); } };
  await page.mouse.move(x, y);
  await film("in", 8);
  await sleep(300);
  const big = await geo();
  const say = JSON.stringify({ rest, big });
  assert.ok(big.grow && !big.open, `hovered it grows, and does not open ${say}`);
  assert.ok(big.field.h >= rest.field.h + 24, `taller ${say}`);
  assert.ok(Math.abs(big.field.l - rest.field.l) <= 1 && Math.abs(big.field.r - rest.field.r) <= 1, `never wider: the same left and right edges ${say}`);
  assert.ok(Math.abs(big.field.b - rest.field.b) <= 1, `grown up out of its own foot ${say}`);
  assert.deepEqual([big.box, big.dock, big.canvas], [rest.box, rest.dock, rest.canvas], `nothing else moved ${say}`);
  assert.ok(big.field.l >= big.btnR, `it never covers the bar's buttons ${say}`);
  await shot("2-hover");

  // ...left: still grown a moment (a pass across does not flicker), then the pill again
  await away(); await sleep(120);
  assert.ok((await geo()).grow, "still grown just after the mouse leaves");
  await film("out", 10);
  await sleep(700);
  const back = await geo();
  assert.ok(!back.grow && Math.abs(back.field.w - rest.field.w) <= 1 && Math.abs(back.field.h - rest.field.h) <= 1, `the pill again ${JSON.stringify(back)}`);
  // ...out and back in inside the delay: it stays grown throughout
  await page.mouse.move(x, y); await sleep(250); await away(); await sleep(100); await page.mouse.move(x, y); await sleep(500);
  assert.ok((await geo()).grow, "back in before the delay: still grown");
  await away(); await sleep(800);

  // ...opened by a click on the grown pill: the window at the same width, then the mouse away: open (only its × or Esc shuts it)
  await page.mouse.move(x, y); await sleep(400);
  assert.ok((await geo()).grow, "grown before the press");
  // ...pressed where its words sat at rest, the grown field's bare middle between the tools and send: that opens it too (chat-window, CI)
  assert.equal(await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.className, [x, y]), "tq-compose-field", "the press lands on the field's middle");
  await page.mouse.click(x, y);
  await page.waitForSelector(".tq-compose-box[data-tq-open]", { timeout: 5000 });
  await page.waitForSelector("[data-tq-chat-pop]:not([hidden])", { timeout: 5000 }); await sleep(300);
  const opened = await geo(), popW = await page.$eval("[data-tq-chat-pop]", (e) => Math.round(e.getBoundingClientRect().width));
  assert.ok(Math.abs(opened.field.w - rest.field.w) <= 1 && Math.abs(opened.field.r - rest.field.r) <= 1 && Math.abs(popW - rest.field.w) <= 1,
    `the press opens the window at the pill's width ${JSON.stringify({ rest: rest.field, opened: opened.field, popW })}`);
  await page.keyboard.type("draft a reply to Erin");
  await away(); await sleep(900);
  assert.ok((await geo()).open, "focused and typed in, a look away leaves it open");
  await shot("3-typed-mouse-away");
  // ...Esc shuts the window; with words still in it the pill stays grown, the mouse nowhere near
  await page.keyboard.press("Escape"); await sleep(200);
  if (await page.$(".tq-compose-box[data-tq-open]")) { await page.keyboard.press("Escape"); await sleep(200); }
  await away(); await sleep(900);
  const typed = await geo();
  assert.ok(!typed.open && typed.grow && typed.field.h >= rest.field.h + 24, `words in it: it stays grown ${JSON.stringify(typed)}`);
  await shot("4-shut-with-words");
  // ...emptied: the pill again
  await page.$eval(".tq-chat-unit > .tq-compose-box textarea", (e) => e.focus());
  await page.keyboard.down("Control"); await page.keyboard.press("a"); await page.keyboard.up("Control"); await page.keyboard.press("Backspace");
  await page.keyboard.press("Escape"); await sleep(200);
  if (await page.$(".tq-compose-box[data-tq-open]")) { await page.keyboard.press("Escape"); await sleep(200); }
  await sleep(800);
  assert.ok(!(await geo()).grow, "empty and shut: the pill again");

  // ...keyboard focus opens it, the same as a press; it stays open with the mouse away
  await page.$eval(".tq-chat-unit > .tq-compose-box textarea", (e) => e.focus()); await away(); await sleep(800);
  assert.ok((await geo()).open, "focus by keyboard opens it, and a mouse away does not shut it");
  await page.keyboard.press("Escape"); await sleep(200);
  if (await page.$(".tq-compose-box[data-tq-open]")) { await page.keyboard.press("Escape"); await sleep(200); }

  // ...at 1920 and a narrow desk window too: grown in its corner, the bar and the canvas still, the buttons never covered
  for (const [w, h] of [[1920, 1080], [820, 700]]) {
    await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 }); await away(); await sleep(1500);
    const r0 = await geo(), [px, py] = await at(".tq-chat-unit > .tq-compose-box textarea");
    await page.mouse.move(px, py); await sleep(400);
    const r1 = await geo(), s = `${w}x${h} ${JSON.stringify({ r0, r1 })}`;
    assert.ok(r1.grow && r1.field.h >= r0.field.h + 24 && Math.abs(r1.field.l - r0.field.l) <= 1 && Math.abs(r1.field.r - r0.field.r) <= 1, `taller, never wider ${s}`);
    assert.deepEqual([r1.box, r1.dock, r1.canvas], [r0.box, r0.dock, r0.canvas], `nothing else moved ${s}`);
    assert.ok(r1.field.l >= r1.btnR && r1.field.l >= 0, `the buttons never covered ${s}`);
    await shot(`5-hover-${w}`);
    await away(); await sleep(800);
  }
  if (frames.length) console.log(`# frames: ${frames.length} in ${shots}`);
  assert.deepEqual(errors, []);
});

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* THE PROMPT BOX HOLDS STILL (the owner, 2026-11-18: clicking the paperclip several times makes the box JUMP). The box on a task's chat is
   pressed, its file picked, again and again; every frame of the box is read - where it stands, how big it is, where its words begin. Invented
   people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "prompt-box");
// a 1x1 PNG
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

export async function world(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), "[]");
  for (const n of ["a.png", "b.png", "c.png", "d.png", "e.png"]) await writeFile(path.join(bin, n), PNG);
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "1" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api, bin };
}

// every frame from now until `stop`: the box's rect, its words' rect, its attach button's rect
export const watchBox = (page, sel) => page.evaluate((sel) => {
  window.__seen = []; const t0 = performance.now();
  const r = (el) => { if (!el) return null; const b = el.getBoundingClientRect(); return [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)]; };
  const tick = () => {
    const box = document.querySelector(sel), s = { box: r(box), words: r(box?.querySelector(".tq-aui-input")), clip: r(box?.querySelector("[data-tq-box-attach]")),
      chips: box?.querySelector(".tq-aui-attachments")?.innerText || "" };
    const last = window.__seen.at(-1);
    if (!last || JSON.stringify([last.box, last.words, last.clip, last.chips]) !== JSON.stringify([s.box, s.words, s.clip, s.chips])) window.__seen.push({ at: Math.round(performance.now() - t0), ...s });
    if (!window.__stop) requestAnimationFrame(tick);
  };
  window.__stop = false; tick();
}, sel);

// the paperclip pressed seven times: five pictures picked, two pickers cancelled - every frame of the box read
async function pressClip(page, w, sel, name) {
  const dir = path.join(out, name); await mkdir(dir, { recursive: true });
  const rec = await record(page, dir);
  await watchBox(page, sel);
  const clip = `${sel} [data-tq-box-attach]`;
  for (const [i, f] of ["a.png", "b.png", "", "c.png", "d.png", "", "e.png"].entries()) {
    const [chooser] = await Promise.all([page.waitForFileChooser({ timeout: 5000 }).catch(() => null), page.click(clip).catch(() => {})]);
    if (chooser) { if (f) await chooser.accept([path.join(w.bin, f)]); else await chooser.cancel(); }
    await new Promise((r) => setTimeout(r, i % 2 ? 150 : 600));
  }
  await new Promise((r) => setTimeout(r, 1500));
  const seen = await page.evaluate(() => { window.__stop = true; return window.__seen; });
  await rec.stop();
  await writeFile(path.join(dir, "seen.json"), JSON.stringify(seen, null, 1));
  // ...each picked file moves the box's words once at most, never in two steps (an "uploading…" first, then the chip); the box and its paperclip
  // hold still - on a phone the chips' own line comes once, with the first file, and the box grows that once
  const changes = (k) => seen.filter((x, i) => i > 0 && JSON.stringify(x[k]) !== JSON.stringify(seen[i - 1][k])).length;
  const picked = 5, verdict = { words: changes("words") <= picked, box: changes("box") <= 1, clip: changes("clip") <= 1,
    grewOnce: changes("box") === 0 || seen.at(-1).box[3] > seen[0].box[3] };
  await note(dir, { done: `${name}: the paperclip is pressed seven times - five pictures picked, two pickers cancelled.`,
    expect: "Each file comes in as its chip in one step; the box and the paperclip hold still (on a phone the chips' line comes once).",
    saw: JSON.stringify(seen), verdict: Object.values(verdict).every(Boolean) ? "PASS" : "FAIL" });
  return { seen, verdict };
}
const check = ({ seen, verdict }) => assert.deepEqual(verdict, { words: true, box: true, clip: true, grewOnce: true }, `the box jumped: ${JSON.stringify(seen)}`);

for (const [width, height] of [[1600, 900], [390, 844]]) {
  test(`the paperclip pressed again and again on a task's chat at ${width}px: the box holds still`, { timeout: 300000 }, async (t) => {
    const w = await world(t), page = await w.newPage();
    await page.setViewport({ width, height });
    const errors = []; page.on("pageerror", (e) => errors.push(e.message));
    const made = await w.api("/api/fixture/mail-task", {});
    await page.goto(w.ui, { waitUntil: "domcontentloaded" });
    await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
    const sel = "[data-tq-task-page] [data-tq-one-box]";
    await page.waitForSelector(sel, { visible: true, timeout: 60000 });
    await new Promise((r) => setTimeout(r, 2500));
    check(await pressClip(page, w, sel, `task-${width}`));
    assert.deepEqual(errors, []);
  });
  test(`the paperclip pressed again and again in New at ${width}px: the box holds still`, { timeout: 300000 }, async (t) => {
    const w = await world(t), page = await w.newPage();
    await page.setViewport({ width, height });
    const errors = []; page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(`${w.ui}#new-task`, { waitUntil: "domcontentloaded" });
    const sel = "[data-tq-new] [data-tq-prompt-box]";
    await page.waitForSelector(sel, { visible: true, timeout: 60000 });
    await new Promise((r) => setTimeout(r, 2500));
    check(await pressClip(page, w, sel, `new-${width}`));
    assert.deepEqual(errors, []);
  });
}

// ENTER WHILE A FILE UPLOADS (2026-11-18): the words went without it, and the file landed alone in the emptied box. The upload is held back
// two seconds; Enter is pressed in it. What the server is sent must carry the words and the file together, once
const slowUploads = async (page, ms = 2000) => {
  const posted = [], guard = page.fixtureRequestGuard;
  page.off("request", guard);
  page.on("request", (r) => {
    if (r.method() === "POST" && /\/api\/(tasks\/\d+\/(assistant\/messages|dispatch)|tasks|concierge\/say)$/.test(r.url().split("?")[0])) posted.push({ url: r.url(), body: r.postData() || "" });
    if (/\/api\/prompt-(image|file)/.test(r.url())) setTimeout(() => guard(r), ms); else guard(r);
  });
  return posted;
};
const typeThenPick = async (page, w, sel, words) => {
  await page.click(`${sel} .tq-aui-input`); await page.keyboard.type(words);
  const [chooser] = await Promise.all([page.waitForFileChooser({ timeout: 5000 }), page.click(`${sel} [data-tq-box-attach]`)]);
  await chooser.accept([path.join(w.bin, "a.png")]);
  await new Promise((r) => setTimeout(r, 300));
  await page.focus(`${sel} .tq-aui-input`); await page.keyboard.press("Enter");
  await new Promise((r) => setTimeout(r, 4000));
};

test("Enter on a task's chat while its file uploads: the line goes with the file", { timeout: 300000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  const made = await w.api("/api/fixture/mail-task", {});
  const posted = await slowUploads(page);
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const sel = "[data-tq-task-page] [data-tq-one-box]";
  await page.waitForSelector(sel, { visible: true, timeout: 60000 });
  await new Promise((r) => setTimeout(r, 2000));
  await typeThenPick(page, w, sel, "Here is the screenshot Erin asked for");
  const lines = posted.filter((p) => /assistant\/messages/.test(p.url)).map((p) => JSON.parse(p.body));
  assert.equal(lines.length, 1, JSON.stringify(posted));
  assert.equal(lines[0].text, "Here is the screenshot Erin asked for");
  assert.equal(lines[0].attachments.length, 1, `the line went without its file: ${JSON.stringify(lines)}`);
  const left = await page.$$eval(`${sel} [data-tq-file-chip]`, (x) => x.length);
  assert.equal(left, 0, "the file was left behind in the box");
  assert.deepEqual(errors, []);
});

test("Enter in New while its file uploads: the task is made with the file", { timeout: 300000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  const posted = await slowUploads(page);
  await page.goto(`${w.ui}#new-task`, { waitUntil: "domcontentloaded" });
  const sel = "[data-tq-new] [data-tq-prompt-box]";
  await page.waitForSelector(sel, { visible: true, timeout: 60000 });
  await new Promise((r) => setTimeout(r, 2000));
  await typeThenPick(page, w, sel, "Make a one-page summary of this chart");
  assert.equal(posted.length, 1, JSON.stringify(posted));
  assert.match(posted[0].body, /ATTACHED IMAGES|"images":\["/, `the task was made without its file: ${JSON.stringify(posted)}`);
  assert.deepEqual(errors, []);
});

// A PASTE FROM WORD OR EXCEL (2026-11-18): their clipboard holds the copied words AND a picture of them. The box took the picture and cancelled
// the paste - the words never came, a picture of them was attached instead. A paste with words is words; a picture alone is the picture
test("a paste of words that also carries a picture of them is words; a picture alone is attached", { timeout: 300000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`${w.ui}#new-task`, { waitUntil: "domcontentloaded" });
  const sel = "[data-tq-new] [data-tq-prompt-box]";
  await page.waitForSelector(sel, { visible: true, timeout: 60000 });
  await new Promise((r) => setTimeout(r, 1500));
  const paste = (withText) => page.evaluate(async (sel, withText, b64) => {
    const dt = new DataTransfer(), bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    if (withText) { dt.setData("text/plain", "Q3 totals\t1,200\t1,450"); dt.setData("text/html", "<table><tr><td>Q3 totals</td></tr></table>"); }
    dt.items.add(new File([bytes], "image.png", { type: "image/png" }));
    const ev = new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true });
    document.querySelector(`${sel} .tq-aui-input`).dispatchEvent(ev);
    await new Promise((r) => setTimeout(r, 1500));
    return { prevented: ev.defaultPrevented, chips: document.querySelectorAll(`${sel} [data-tq-file-chip]`).length };
  }, sel, withText, PNG.toString("base64"));
  assert.deepEqual(await paste(true), { prevented: false, chips: 0 }, "words from a sheet pasted as a picture of them");
  assert.deepEqual(await paste(false), { prevented: true, chips: 1 }, "a picture alone is attached");
  assert.deepEqual(errors, []);
});

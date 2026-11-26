// ONE CLICK OR TWO? Every button he named, pressed once as a hand does (press-lib.mjs) on the instance press-keep.mjs holds up, its screen
// recorded (recorder.mjs) - and for each: did the one press do it, and how long from the release to the first change on screen.
//   PRESS_OUT=<folder> node browser/press-keep.mjs &          then          PRESS_OUT=<folder> node browser/press-measure.mjs <label> ["a rail row's words"]
// Writes <folder>/<label>/<scenario>/ (frames, sheet.png, README.txt) and <folder>/<label>/presses.json. SLOW=<ms> answers every request late.
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { connect, out, press, sleep, slow } from "./press-lib.mjs";
import { note, record } from "./recorder.mjs";

const [label = "run", rowWords = "Can you confirm the AP cutover date?"] = process.argv.slice(2);
const { browser, page } = await connect(), dir = path.join(out, label), rows = [];
await mkdir(dir, { recursive: true });
const q = (css) => new Function(`return () => [...document.querySelectorAll(${JSON.stringify(css)})].filter((e) => e.getBoundingClientRect().width > 0)[0]`)();
const says = (words, scope = "body") => new Function(`return () => [...document.querySelectorAll(${JSON.stringify(`${scope} button, ${scope} [role=button]`)})]
  .filter((b) => b.getBoundingClientRect().width > 0 && (b.innerText || b.getAttribute("aria-label") || "").trim().replace(/\\s+/g, " ") === ${JSON.stringify(words)})[0]`)();
const quiet = async (find) => { const r = await press(page, find, { watch: 300 }); await sleep(900); return r; };
const hash = () => page.evaluate(() => location.hash);

// `did`: run in the page after the press - true once the press has visibly done its job
async function scenario(name, what, find, did, o = {}) {
  if (!o.still) { await page.mouse.move(700, 60); await sleep(300); }
  const rec = await record(page, path.join(dir, name));
  await sleep(400);
  const r = await press(page, find, { watch: 4000, changed: did, ...o });
  await sleep(900);
  const frames = await rec.stop({ sheet: 9 });
  const one = r.ok && !r.off && !!r.did, landed = r.ok && r.click && r.click.target === r.down && !r.click.prevented;
  const row = { button: what, oneClick: one, clickLandedOnIt: !!landed, movedWhileHeldPx: r.movedWhileHeld ?? null, msReleaseToFirstChange: r.msUpToFirstChange ?? null,
    msReleaseToDone: r.msUpToDone ?? null, firstChange: r.firstChange || "", down: r.down || r.why, clickWentTo: r.click?.target || "none" };
  rows.push(row);
  await note(path.join(dir, name), { done: `${what}: the pointer travelled to it, rested 140 ms, went down, came up 90 ms later. One press.`,
    expect: "The press does its job, and the screen shows it took within a beat of the release.",
    saw: `${one ? "It did." : "NOTHING HAPPENED - the press did not do it."} The click went to: ${row.clickWentTo}. The button moved ${row.movedWhileHeldPx} px while the pointer was down. `
      + `First change on screen ${row.msReleaseToFirstChange} ms after the release (${row.firstChange}); done at ${row.msReleaseToDone} ms. ${frames.length} frames.`,
    verdict: one ? "one click" : "TWO CLICKS NEEDED" });
  console.log(`${one ? "one click " : "TWO CLICKS"}  ${what.padEnd(58)} first change ${String(row.msReleaseToFirstChange).padStart(5)} ms, done ${String(row.msReleaseToDone).padStart(5)} ms, moved ${row.movedWhileHeldPx} px${landed ? "" : `  -> click went to ${row.clickWentTo}`}`);
  return r;
}

await slow(page, +(process.env.SLOW || 0));
// the day's opener: the task and the chat window shut, a new chat
await page.keyboard.press("Escape");
if (await page.evaluate(() => !!document.querySelector("[data-tq-box-close]")?.getBoundingClientRect().width)) await quiet(q("[data-tq-box-close]"));
if (await page.evaluate(() => !![...document.querySelectorAll("button")].find((b) => b.getAttribute("aria-label") === "Close task" || b.title === "Close task"))) await quiet(says("Close task"));
await quiet(q("[data-tq-new-chat], [data-tq-new-chat-head]")); await sleep(1500);

await scenario("1-walk", "Walk me through my tasks", says("Walk me through my tasks"), () => !!document.querySelector("[data-tq-task-page]") || /^#task=/.test(location.hash));
let h = await hash();
await scenario("2-next", "Next", says("Next"), new Function(`return () => location.hash !== ${JSON.stringify(h)}`)());
h = await hash();
await scenario("3-next-again", "Next again, the pointer left on it", says("Next"), new Function(`return () => location.hash !== ${JSON.stringify(h)}`)(), { still: true });
h = await hash();
await scenario("4-back", "Back", says("Back"), new Function(`return () => location.hash !== ${JSON.stringify(h)}`)());
h = await hash();
await scenario("5-rail-row", `A row on the rail`, new Function(`return () => [...document.querySelectorAll("[data-tq-rail] .tq-pile-row[data-tq-key]")].find((r) => r.innerText.includes(${JSON.stringify(rowWords)}))`)(),
  new Function(`return () => location.hash !== ${JSON.stringify(h)}`)());
await sleep(1200);
// a card's own button, if the row's task holds one that is lit
if (await page.evaluate(() => !![...document.querySelectorAll("[data-tq-task-page] [data-tq-review] button")].find((b) => b.innerText.trim() === "Send" && !b.matches(":disabled") && b.getBoundingClientRect().width > 0)))
  await scenario("6-card-send", "Send on a reply card", () => [...document.querySelectorAll("[data-tq-task-page] [data-tq-review] button")].find((b) => b.innerText.trim() === "Send" && b.getBoundingClientRect().width > 0),
    () => ![...document.querySelectorAll("[data-tq-task-page] [data-tq-review] button")].find((b) => b.innerText.trim() === "Send" && !b.matches(":disabled") && b.getBoundingClientRect().width > 0));
else console.log("           (no lit Send card on that row's task - skipped)");
// the task's own box: his words to the agent
await quiet(q("[data-tq-task-page] .tq-aui-input")); await page.keyboard.type("what is left on this one?", { delay: 20 }); await sleep(300);
await scenario("7-task-send", "The up arrow, a prompt to the task's agent", q("[data-tq-task-page] .tq-aui-send"), () => !document.querySelector("[data-tq-task-page] .tq-aui-input")?.value);
// the Assistant's box, on the day's opener
await quiet(says("Close task")); await sleep(600);
await quiet(q(".tq-compose-box textarea")); await page.keyboard.type("What's on me right now?", { delay: 20 }); await sleep(300);
await scenario("8-assistant-send", "The up arrow, the Assistant's box open", q(".tq-compose-box .tq-send"), () => !document.querySelector(".tq-compose-box textarea")?.value);
await sleep(2500);
// ...and the same box shut with words in it (Esc, its x, or a Next/Back/rail press shuts it and keeps what is typed)
await page.evaluate(() => document.querySelector(".tq-compose-box textarea")?.focus()); await page.keyboard.type("Show me the reports", { delay: 20 }); await sleep(200);
await page.keyboard.press("Escape"); await sleep(700);
const shut = await page.evaluate(() => !document.querySelector(".tq-compose-box")?.hasAttribute("data-tq-open"));
await scenario("9-assistant-send-shut", `The up arrow, the Assistant's box shut with words in it${shut ? "" : " (IT DID NOT SHUT)"}`, q(".tq-compose-box .tq-send"), () => !document.querySelector(".tq-compose-box textarea")?.value);
await slow(page, 0);
await writeFile(path.join(dir, "presses.json"), JSON.stringify(rows, null, 1));
console.log(`\n${dir}`);
browser.disconnect();

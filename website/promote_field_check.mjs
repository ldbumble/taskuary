// The third conditional section on a report/workflow: "MOVE IT UP IN THE PIPE IF". The sentence is
// the switch - there used to be a `triage` toggle with the text hidden behind it, off by default,
// which is why none of the owner's seven reports had one (2026-09-04). Only a browser can tell
// whether the section is on the page, in the right place, and whether its switch reveals the field.
//
//   node website/promote_field_check.mjs <url>     # against a `taskuary --demo --port N` server
import { launch } from "./browser.mjs";

const url = process.argv[2] || "http://127.0.0.1:7912/";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
let bad = 0;
const check = (ok, msg, extra) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${msg}`);
  if (!ok) { bad += 1; if (extra !== undefined) console.error("   ", JSON.stringify(extra)); }
};

const browser = await launch();
const page = await browser.newPage();
await page.setViewport({ width: 1400, height: 1000 });
try {
  await page.goto(url, { waitUntil: "networkidle2" });
  await wait(2500);
  await page.evaluate(() => [...document.querySelectorAll("button,div,a")].find((e) => e.textContent.trim() === "Reports")?.click());
  await wait(1800);
  await page.evaluate(() => [...document.querySelectorAll("button,a,span,div")]
    .filter((e) => e.textContent.trim() === "Edit" && e.children.length === 0)[3]?.click());
  await wait(2500);

  const before = await page.evaluate(() => {
    const t = document.body.innerText;
    const heads = [...document.querySelectorAll("*")].map((e) => e.textContent.trim())
      .filter((x) => /\(OPTIONAL\)$/.test(x) && x.length < 60);
    return { section: /MOVE IT UP IN THE PIPE IF/i.test(t), offCopy: /every run is news/i.test(t),
             field: /worth interrupting you for/i.test(t), order: [...new Set(heads)] };
  });
  check(before.section, "the section is on the report editor");
  check(before.offCopy, "off by default, and says so");
  check(!before.field, "the sentence field is hidden while it is off");
  // it belongs WITH the other two conditions, not in another step
  const idx = before.order.findIndex((h) => /MOVE IT UP/i.test(h));
  check(idx === before.order.length - 1 && before.order.length >= 3,
    `it sits after the other two conditions: ${before.order.join(" | ")}`, before.order);

  // the switch reveals the sentence
  await page.evaluate(() => {
    const head = [...document.querySelectorAll("*")].find((e) => /^MOVE IT UP IN THE PIPE IF/i.test(e.textContent.trim()) && e.children.length === 0);
    head?.parentElement?.querySelector("input[type=checkbox]")?.click();
  });
  await wait(900);
  const after = await page.evaluate(() => ({
    field: /worth interrupting you for/i.test(document.body.innerText),
    judged: /judged against this sentence/i.test(document.body.innerText),
  }));
  check(after.field, "turning it on reveals the sentence field");
  check(after.judged, "and explains that each run is judged against it");
} finally { await browser.close(); }
process.exit(bad ? 1 : 0);

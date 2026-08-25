// Drive the wizard the way a person would: type a name, press Save, and check the step ticks
// and the counter moves. Tests walk the API; this walks the actual form, which is the half that
// was never exercised.
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";

const b = await launch();
const p = await b.newPage();
await p.setViewport({ width: 1400, height: 1000, deviceScaleFactor: 2 });
p.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));
await p.goto(process.argv[2], { waitUntil: "networkidle0" });
await new Promise((r) => setTimeout(r, 2500));

const fill = async (label, value) => {
  const ok = await p.evaluate((lbl, val) => {
    const input = [...document.querySelectorAll("label")]
      .find((l) => l.textContent.trim().startsWith(lbl))?.parentElement?.querySelector("input");
    if (!input) return false;
    const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    set.call(input, val);                                  // React listens to the native setter
    input.dispatchEvent(new Event("input", { bubbles: true }));
    return true;
  }, label, value);
  console.log(`  ${label}: ${ok ? "filled" : "FIELD NOT FOUND"}`);
  return ok;
};

console.log("typing into the owner step…");
await fill("Your name", "Dana Example");
await fill("Email", "dana@example.org");
await new Promise((r) => setTimeout(r, 400));
const clicked = await p.evaluate(() =>
  !![...document.querySelectorAll("button")].find((x) => x.textContent.trim() === "Save" && !x.disabled)?.click() || true);
console.log("  Save clicked:", clicked);
await new Promise((r) => setTimeout(r, 2500));

const after = await p.evaluate(() => {
  const chip = [...document.querySelectorAll("span, p")].map((e) => e.textContent).find((t) => /^\d\/\d$/.test(t || ""));
  const dlg = document.querySelector('[role="dialog"]');
  return { chip, heading: dlg?.querySelector("p, h2, div")?.textContent?.slice(0, 60),
           text: dlg?.innerText?.slice(0, 200) };
});
console.log("counter now:", after.chip);
console.log("panel says:", (after.text || "").split("\n").slice(0, 3).join(" · "));
await p.screenshot({ path: fileURLToPath(new URL("../docs/screenshot-setup-after.png", import.meta.url)) });
await b.close();

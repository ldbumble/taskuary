// Does the Install button appear where a CLI is missing? Shoots the two places it lives: the
// setup wizard's coding-agent step (onboarding) and the AI CLI agents page under Connections.
//   node website/shot_cli_install.mjs <url> <outdir>
import { launch } from "./browser.mjs";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const [url, out] = process.argv.slice(2);

const clickText = (page, label, tags = "div,button,span,p") => page.evaluate((l, t) => {
  const el = [...document.querySelectorAll(t)].find(
    (e) => e.childElementCount <= 2 && e.textContent.trim() === l && e.offsetParent !== null);
  if (!el) return `no "${l}" on the page`;
  el.click(); return "";
}, label, tags);

// the wizard is a MUI Dialog whose dismiss is an unlabelled icon button in the header - not
// always a CloseIcon. Escape after it, because that closes the dialog either way.
const closeWizard = async (page) => {
  const hit = await page.evaluate(() => {
    const dlg = document.querySelector('[role="dialog"]');
    if (!dlg) return "no wizard open";
    const b = [...dlg.querySelectorAll("button")].find((e) => e.offsetParent !== null
      && (e.querySelector("svg") && !e.textContent.trim()));
    if (b) { b.click(); return "closed"; }
    return "no close button";
  });
  await page.keyboard.press("Escape");
  return hit;
};

// every Install button on the page, with the row it belongs to - the assertion, not the picture
const installs = (page) => page.evaluate(() =>
  [...document.querySelectorAll("button")].filter((b) => b.textContent.trim() === "Install")
    .map((b) => (b.closest("div").parentElement || b.parentElement).textContent.trim().slice(0, 90)));

const browser = await launch();
const page = await browser.newPage(); await page.setViewport({ width: 1280, height: 1000 });
page.on("pageerror", (e) => console.log("pageerror:", e.message.slice(0, 200)));
try {
  await page.goto(url);
  if (process.env.TASKUARY_TOKEN) await page.evaluate((t) => localStorage.setItem("taskuary_token", t), process.env.TASKUARY_TOKEN);
  await page.goto(url, { waitUntil: "networkidle2" }); await wait(1500);

  // the wizard's own CLI step first - the dead end this button exists to remove
  console.log("coding agent step:", await clickText(page, "Set up", "button"));
  await wait(2500);
  await page.screenshot({ path: `${out}/wizard-cli.png` });
  console.log("wizard installs:", JSON.stringify(await installs(page)));

  console.log("close:", await closeWizard(page)); await wait(1200);
  console.log("Connections:", await clickText(page, "Connections")); await wait(1500);
  console.log("card:", await clickText(page, "AI CLI agents")); await wait(2500);
  await page.screenshot({ path: `${out}/agents.png`, fullPage: true });
  console.log("agents installs:", JSON.stringify(await installs(page)));
} finally { await browser.close(); }

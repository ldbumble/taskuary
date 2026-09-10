// Does the Docs tab fit ONE screen?
//
// The page used to grow with the document: SOUL.md at minRows 22/maxRows 40 pushed "Who the
// documents speak for" - and its Save button - below the fold, behind eight document rows (the
// owner, 2026-09-10: "should be in first view of the screen ... make it fit the screen").
//
// Checks what a screenshot cannot assert: that the body does not scroll, that the identity card is
// inside the viewport, and that the editor scrolls INSIDE itself rather than growing the page.
import puppeteer from "puppeteer-core";

const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";

const clickTab = (page, label) => page.evaluate((l) => {
  const el = [...document.querySelectorAll("div,button")].find((d) => d.childElementCount === 0 && d.textContent.trim() === l);
  if (!el) throw new Error(`no tab '${l}'`);
  el.click();
}, label);

(async () => {
  const url = process.argv[2];
  const shot = process.argv[3] || "docs-fit.png";
  const browser = await puppeteer.launch({ executablePath: EDGE, headless: "new" });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && errors.push(`console: ${m.text()}`));

  const bad0 = [];
  await page.goto(url, { waitUntil: "networkidle0", timeout: 30000 });
  await new Promise((r) => setTimeout(r, 1000));
  await clickTab(page, "Docs");
  await new Promise((r) => setTimeout(r, 1600));

  const m = await page.evaluate(() => {
    const el = document.scrollingElement;
    const owner = [...document.querySelectorAll("*")]
      .find((n) => n.children.length === 0 && /Who the documents speak for/i.test(n.textContent || ""));
    const card = owner ? owner.closest("div").parentElement.getBoundingClientRect() : null;
    const save = [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Save");
    // MUI multiline renders a HIDDEN shadow textarea for autosizing, height 0 - measuring that one
    // reported a collapsed editor on a page that was rendering perfectly
    const ta = [...document.querySelectorAll("textarea")]
      .filter((t) => !t.hasAttribute("aria-hidden"))
      .sort((a, b) => b.clientHeight - a.clientHeight)[0];
    return {
      pageScrolls: el.scrollHeight - el.clientHeight,
      viewport: window.innerHeight,
      ownerFound: !!owner,
      ownerBottom: card ? Math.round(card.bottom) : null,
      saveBottom: save ? Math.round(save.getBoundingClientRect().bottom) : null,
      editor: ta ? { h: Math.round(ta.clientHeight), scroll: Math.round(ta.scrollHeight),
                     overflowY: getComputedStyle(ta).overflowY,
                     bottom: Math.round(ta.getBoundingClientRect().bottom) } : null,
      profilesTab: [...document.querySelectorAll("div,button")].some((d) => /^Profiles( \(\d+\))?$/.test(d.textContent.trim())),
    };
  });

  // ...and the half a short demo document cannot prove: a LONG one must scroll INSIDE the editor
  // rather than grow the page. The owner's own SOUL.md is what pushed the identity card off screen.
  const long_ = await page.evaluate(() => {
    const ta = [...document.querySelectorAll("textarea")].filter((t) => !t.hasAttribute("aria-hidden"))
      .sort((a, b) => b.clientHeight - a.clientHeight)[0];
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
    setter.call(ta, Array.from({ length: 400 }, (_, i) => `line ${i + 1} of a very long operator document`).join(String.fromCharCode(10)));
    ta.dispatchEvent(new Event("input", { bubbles: true }));
    return new Promise((r) => setTimeout(() => {
      const el = document.scrollingElement;
      r({ pageScrolls: el.scrollHeight - el.clientHeight, h: Math.round(ta.clientHeight),
          scroll: Math.round(ta.scrollHeight), bottom: Math.round(ta.getBoundingClientRect().bottom) });
    }, 500));
  });
  console.log("with a 400-line document:", JSON.stringify(long_));
  if (long_.pageScrolls > 8) bad0.push(`a long document made the PAGE scroll by ${long_.pageScrolls}px`);
  if (long_.bottom > m.viewport) bad0.push(`a long document pushed the editor ${long_.bottom - m.viewport}px past the fold`);
  if (long_.scroll <= long_.h + 4) bad0.push("a 400-line document did not overflow the editor - it is not being clipped to the pane");

  await page.screenshot({ path: shot, fullPage: false });
  await browser.close();

  console.log(JSON.stringify(m, null, 2));
  const bad = [...bad0];
  if (errors.length) bad.push(`console/page errors:\n  ${errors.join("\n  ")}`);
  if (!m.ownerFound) bad.push("'Who the documents speak for' is not on the page at all");
  if (m.pageScrolls > 8) bad.push(`the page itself scrolls by ${m.pageScrolls}px - it should fit`);
  if (m.ownerBottom !== null && m.ownerBottom > m.viewport) bad.push(`the identity card ends ${m.ownerBottom - m.viewport}px below the fold`);
  if (m.saveBottom !== null && m.saveBottom > m.viewport) bad.push(`its Save button is ${m.saveBottom - m.viewport}px below the fold`);
  if (!m.editor) bad.push("no document editor found");
  else {
    if (m.editor.h < 200) bad.push(`the editor collapsed to ${m.editor.h}px`);
    if (m.editor.h > m.viewport) bad.push(`the editor is ${m.editor.h}px tall in a ${m.viewport}px viewport`);
    if (m.editor.bottom > m.viewport) bad.push(`the editor runs ${m.editor.bottom - m.viewport}px past the fold`);
    if (!["auto", "scroll"].includes(m.editor.overflowY)) bad.push(`the editor does not scroll inside itself (overflow-y: ${m.editor.overflowY})`);
  }
  if (!m.profilesTab) bad.push("the Profiles section is missing from Docs");
  if (bad.length) { console.error("\nFAIL\n- " + bad.join("\n- ")); process.exit(1); }
  console.log(`\nOK - fits: page scroll ${m.pageScrolls}px, editor ${m.editor.h}px of ${m.editor.scroll}px content, screenshot ${shot}`);
})();

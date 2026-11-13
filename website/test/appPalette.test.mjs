import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("dark reading text and every semantic ink clear WCAG AA on their surfaces", async () => {
  const { DARK } = await import("../src/appPalette.js");
  const luminance = (hex) => {
    const c = hex.slice(1).match(/../g).map((s) => parseInt(s, 16) / 255).map((n) => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4);
    return c[0] * .2126 + c[1] * .7152 + c[2] * .0722;
  };
  const contrast = (a, b) => { const x = luminance(a), y = luminance(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  for (const surface of ["canvas", "panel", "inset"]) for (const ink of ["text", "secondary", "muted", "link"])
    assert.ok(contrast(DARK[ink], DARK[surface]) >= 4.5, `${ink} on ${surface}`);
  for (const [ink, tint] of [["link", "slate"], ["success", "sage"], ["danger", "red"], ["warning", "brass"], ["secondary", "neutral"], ["purple", "purple"]])
    assert.ok(contrast(DARK[ink], DARK[`tint-${tint}`]) >= 4.5, `${ink} on ${tint}`);
});

test("changing the theme does not remount work and custom styles use shared tokens", () => {
  const shell = readFileSync(new URL("../src/TaskHubPage.jsx", import.meta.url), "utf8");
  assert.match(shell, /<ThemeToggle\s*\/>/);
  assert.doesNotMatch(shell, /key=\{(?:mode|theme)/);
  for (const file of ["assistantView.css", "generalWorkspace.css", "diffView.css"]) {
    const css = readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8");
    assert.ok(/var\(--tq-panel,/.test(css), `${file}: panel token`);
    assert.ok(/var\(--tq-(?:text|secondary|muted),/.test(css), `${file}: reading text token`);
  }
});

// rendered in the dark theme (2026-11-11): the strip of lines waiting by the box stood as a light box - its ground was a token no
// palette declares, so its light fallback was all it ever had. A colour the chat's styles take from a token is one the night palette names
test("every colour token the chat's own styles use is one the dark palette declares", async () => {
  const { darkVariables } = await import("../src/appPalette.js");
  for (const file of ["generalWorkspace.css", "agentStepRows.css", "publishedPages.css"]) {
    const css = readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8");
    const used = [...new Set([...css.matchAll(/var\((--tq-[a-z0-9-]+),\s*#/g)].map((m) => m[1]))];
    assert.deepEqual(used.filter((v) => !(v in darkVariables)), [], `${file}: a colour with a light fallback and no dark value`);
  }
});

// the dark-mode audit (2026-11-13): the rail's two commonest marks were fixed near-black art - the envelope's slate body vanished
// into the night rail and left only its flap, GitHub's disc was a hole - so each takes palette tokens the dark root declares
test("the mail and GitHub marks are drawn from palette tokens, so they show on the night rail", async () => {
  const { darkVariables } = await import("../src/appPalette.js");
  const logos = readFileSync(new URL("../src/logos.jsx", import.meta.url), "utf8");
  for (const name of ["email", "github"]) {
    const at = logos.indexOf(`  ${name}: (p) => (`), art = logos.slice(at, logos.indexOf("</S>", at));
    const used = [...art.matchAll(/(?:fill|stroke): "var\((--tq-[a-z-]+),/g)].map((m) => m[1]);
    assert.ok(used.length >= 2, `${name}: body and mark take tokens`);
    assert.deepEqual(used.filter((v) => !(v in darkVariables)), [], `${name}: a token the night palette names`);
    assert.doesNotMatch(art, /(?:fill|stroke)="#[0-9a-f]{3,6}"/i, `${name}: no fixed colour left`);
  }
});

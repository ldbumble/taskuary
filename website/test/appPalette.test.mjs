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

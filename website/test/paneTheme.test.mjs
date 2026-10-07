// A PANE IS WHITE UNLESS YOU PICK OTHERWISE (the owner, 2026-10-07: "are there any other themes which are white and keep
// it the default but show the other themes?"). The light palettes lead the picker, every dark one stays a pick away, and the
// page tells the server light or dark so the next Claude session paints in the matching theme (terminal.claude_theme_args).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/TerminalView.jsx", import.meta.url), "utf8");

test("the default pane is white, and an unknown or missing pick falls back to it", () => {
  assert.match(src, /export const DEFAULT_THEME = "GitHub Light";/);
  assert.match(src, /"GitHub Light": \{ background: "#ffffff"/);
  assert.match(src, /return THEMES\[n\] \? n : DEFAULT_THEME;/);
});

test("the picker offers light and dark, and the dark palettes are all still there", () => {
  for (const n of ["Catppuccin Latte", "Solarized Light", "One Light", "Catppuccin Mocha", "Dracula", "Tokyo Night", "Gruvbox Dark", "One Dark"])
    assert.ok(src.includes(`"${n}"`) || src.includes(`${n}:`), n);
  assert.match(src, /\[\["Light", true\], \["Dark", false\]\]/);
});

test("the page tells the server light or dark, once per change", () => {
  assert.match(src, /api\.patch\("\/api\/settings", \{ name: "pane_theme", value: mode \}\)/);
  assert.match(src, /if \(mode !== toldServer\)/);
});

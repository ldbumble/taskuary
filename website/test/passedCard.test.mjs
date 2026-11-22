// A CARD YOU HAVE MOVED PAST IS THE CARD IT WAS, ITS BUTTONS GREYED (the owner, 2026-11-18: "don't need reason. just keep it with buttons but the
// buttons grayed out once you moved on"): the server settles it (proposals.move_on); the page keeps it in its turn - its own card, `past`.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");


// ...ONE PROP, ONE LOOK (the owner, 2026-11-18: "just keep it with buttons but the buttons grayed out once you moved on"): a card moved past is
// drawn under MovedPast - every button in it off at once, greyed, out of the Tab order - and a card inside one is greyed once, not twice as faint
test("a card moved past keeps its buttons, every one of them off, greyed once", async () => {
  const { build } = await import("esbuild");
  const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: `
    import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser"; import { MovedPast } from "./src/PassedCard.jsx";
    const card = (on, inner) => <MovedPast on={on}><button>Send</button>{inner}</MovedPast>;
    export const html = (on, nested) => renderToStaticMarkup(card(on, nested ? card(true) : null));` },
    bundle: true, write: false, format: "esm", jsx: "automatic", platform: "browser", logLevel: "silent", define: { "process.env.NODE_ENV": '"production"' } });
  const { html } = await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString("base64")}`);
  assert.equal(html(false), "<button>Send</button>", "a live card is untouched");
  assert.match(html(true), /^<fieldset disabled="" inert="" data-tq-moved-past="" aria-disabled="true" style="[^"]*opacity:0\.6;filter:grayscale\(1\)[^"]*"><button>Send<\/button><\/fieldset>$/);
  assert.equal(html(true, true).match(/<fieldset/g).length, 1, "greyed once");
  assert.equal(html(true, true).match(/<button>Send<\/button>/g).length, 2, "its buttons stay");
});

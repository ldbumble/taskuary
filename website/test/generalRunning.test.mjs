import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("a running turn says so, whichever backend is answering", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.ok(view.includes("<ThreadPrimitive.If running>"), "the running thread must render something");
  assert.match(view, /<ThreadPrimitive\.If running>\s*<Thinking/);                  // this pane is streaming the answer
  assert.match(view, /\{serverBusy && <Thinking/);                                  // the turn is running without us
  assert.match(view, /serverBusy=\{busy\} provider=\{session\?\.provider \|\| pickedLabel\}/);   // named, even on a first turn
  assert.match(view, /const Thinking = \(/);
});

test("the offer to schedule the workflow waits for the answer it is offering to repeat", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.match(view, /!dock && !serverBusy && messages\?\.some/);
});

test("the working dots animate from the general workspace's own stylesheet", () => {
  const css = read("generalWorkspace.css");
  assert.match(css, /\.tq-aui-thinking i \{[^}]*animation: tqAuiThinking/);
  assert.match(css, /@keyframes tqAuiThinking/);
});

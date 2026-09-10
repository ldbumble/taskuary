import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("a running turn says so, whichever backend is answering", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.ok(view.includes("<ThreadPrimitive.If running>"), "the running thread must render something");
  // Both roads still say it - the pane that is streaming the answer, and a turn running without us.
  // The DOCK says it with the dots it always had; a work window says it with the band, which also
  // says who is working, what it is doing now, how long, and what it has got (agentWork.js).
  assert.match(view, /<ThreadPrimitive\.If running>\s*\{dock \? <Thinking[\s\S]*?: <AgentBand/);
  assert.match(view, /\{serverBusy && \(dock \? <Thinking[\s\S]*?: <AgentBand/);
  assert.match(view, /serverBusy=\{busy\} provider=\{session\?\.provider \|\| pickedLabel\} name=\{name\}/);
  assert.match(view, /const Thinking = \(/);
  assert.match(view, /const AgentBand = \(\{ name, provider, work, since \}\)/);
});

test("the band reports the turn, and never invents a total it was not told", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.match(view, /work\.steps\.length > 1 && <span className="tq-aui-band-step"> — step \{work\.steps\.length\}/);
  assert.doesNotMatch(view, /of about/);                                            // no made-up denominator
  assert.match(view, /elapsedText\(now - since\)/);                                 // the turn's clock
  assert.match(view, /what it has so far/);
  const css = read("generalWorkspace.css");
  assert.match(css, /\.tq-aui-band \{/);
  // ...and the six identical COMPLETEs go quiet, except in the dock, which is left as it was
  assert.match(css, /\.tq-aui-tool-complete summary em \{ display: none; \}/);
  assert.match(css, /\.tq-aui-dock \.tq-aui-tool-complete summary em \{ display: block; \}/);
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

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// A BURST FROM ONE SENDER READS AS ONE (the owner's four WhatsApp messages in a minute, 2026-11-05): the head once, then the time alone
test("the next message of the same sender on the same channel carries its time alone", () => {
  const ws = read("GeneralWorkspace.jsx");
  assert.match(ws, /const sameAs = \(a, b\) => !!a && !!b && a\.who === b\.who && String\(a\.channel \|\| ""\) === String\(b\.channel \|\| ""\);/);
  assert.match(ws, /\{more \? stamp : <><ChannelMark channel=\{x\.channel\} \/>/);
  // ...and one in the same minute as the one before carries no head at all
  assert.match(ws, /again = more && stamp === \(all\[i - 1\]\.at \? when\(all\[i - 1\]\.at\) : ""\)/);
  assert.match(ws, /\{!again && <span className="tq-aui-arrived-head">/);
  const css = read("generalWorkspace.css");
  assert.match(css, /\.tq-aui-chat \.tq-aui-arrived-more \{ margin-top: -8px; \}/);
  // ...and a summary under the agent's own words keeps a line's breath
  assert.match(css, /\+ \.tq-aui-summary\[data-tq-summary=open\] \{ margin-top: 12px; \}/);
});



// THE OWNER'S OWN REPLY draws nothing of its own - never the brief under it as a trigger (the scenario run, 2026-11-06)
test("a brief carrying only the owner's own reply is not drawn as a trigger", () => {
  assert.match(read("chatStream.js"), /: !mail\?\.length && words && words\.length <= 140 \? words : ""/);
});


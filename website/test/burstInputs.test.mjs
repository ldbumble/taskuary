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

// THE OWNER'S LINES TYPED IN A ROW READ AS ONE, as a sender's burst does (the scenario run, 2026-11-06: "You · 6:48 PM" over each of three lines)
test("the owner's next line in a row carries a new minute's time alone, a same minute nothing", () => {
  const ws = read("GeneralWorkspace.jsx"), um = ws.slice(ws.indexOf("const UserMessage = "), ws.indexOf("const ShownCtx"));
  // ...a press before it is an event, not a line of theirs (pressLine.test.mjs): the line after it gets its own head
  // the hook is read before the component's first return (hooks keep their order)
  assert.ok(um.indexOf("const prev = useAuiState") > 0 && um.indexOf("const prev = useAuiState") < um.indexOf("return"));
  assert.match(um, /return p\?\.role === "user" && !p\.metadata\?\.custom\?\.brief && !p\.metadata\?\.custom\?\.press \? \(p\.createdAt \? when\(new Date\(p\.createdAt\)\) : ""\) : null;/);
  assert.match(um, /\{prev === null \? <div className="tq-aui-user-head">/);
  assert.match(um, /: stamp && stamp !== prev \? <div className="tq-aui-user-head">\{stamp\}<\/div> : null\}/);
  const css = read("generalWorkspace.css");
  assert.match(css, /\.tq-aui-chat \.tq-aui-message:has\(\+ \.tq-aui-user-more\) \{ margin-bottom: 8px; \}/);
});

// RIGHT-TO-LEFT WORDS: each paragraph takes its own direction (the scenario run, 2026-11-06)
test("chat paragraphs and bubbles take their direction from their own words", () => {
  const ws = read("GeneralWorkspace.jsx");
  assert.match(ws, /<span className="tq-aui-arrived-words" dir="auto" title=\{x\.words\}>/);
  assert.match(ws, /<div className="tq-aui-user-bubble" dir="auto"><MessagePrimitive\.Parts \/><\/div>/);
  assert.match(read("generalWorkspace.css"), /\.tq-aui-agent-body p, \.tq-aui-agent-body li, \.tq-aui-user-bubble p, \.tq-aui-arrived-words, \.tq-aui-ask \{ unicode-bidi: plaintext; \}/);
});

// THE OWNER'S OWN REPLY draws nothing of its own - never the brief under it as a trigger (the scenario run, 2026-11-06)
test("a brief carrying only the owner's own reply is not drawn as a trigger", () => {
  assert.match(read("chatStream.js"), /: !mail\?\.length && words && words\.length <= 140 \? words : ""/);
});

// A FOLD'S LINE IS AN EVENT, the mail it brought the input under it (general.shown_history `fold`; the owner's rule of inputs, 2026-11-09)
test("a folded-in task's turn draws its line as an event with the mail it brought", () => {
  const ws = read("GeneralWorkspace.jsx"), um = ws.slice(ws.indexOf("const UserMessage = "), ws.indexOf("const ShownCtx"));
  assert.match(ws, /\.\.\.\(m\.fold \? \{ fold: m\.fold \} : \{\}\)/);
  assert.ok(um.indexOf("const fold = useAuiState") > 0 && um.indexOf("const fold = useAuiState") < um.indexOf("return"));
  assert.match(um, /const event = brief && chat \? eventOf\(words, fold, mail\) : "";/);
  assert.match(um, /data-tq-chat-trigger=\{fold \? "fold"/);
  assert.match(um, /\{!!mail\?\.length && <Arrived mail=\{mail\} \/>\}/);
});

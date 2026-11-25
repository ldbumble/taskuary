// "Give an agent a job" offered "Just talk it through" - the assistant's own thread. The assistant does nothing itself; only agents do
// (the owner, 2026-10-15: "other option should not be just talk it through with assistant but general agent with all the correct
// buttons ... assistant itself does nothing. only research agents should do things"). The second door is a general agent: which role,
// which brain, which model - the task page's own hand-off - and it starts the moment you press the button.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const ns = readFileSync(new URL("../src/NewSheet.jsx", import.meta.url), "utf8");

test("an agent's job has no door to pick: no live-session-or-general fork (TQ-1397)", () => {
  assert.doesNotMatch(ns, /Just talk it through|Ask the assistant/);
  assert.doesNotMatch(ns, /title="A general agent"|title="A live session"/);
});

// THE AGENT CHAT'S OWN BOX (the owner, 2026-11-08): a general agent's job is typed into the shared PromptBox - no role picker, no Connect an AI;
// with none connected the box says so with the way to connect one (its one AI chooser: the test below)
test("a general agent's job is typed into the chat's own box and dispatched as general work", () => {
  assert.doesNotMatch(ns, /generalBrains=\{generalBrains\} brainsRead=\{agentsRead\} pick=\{pick\}/);
  assert.match(ns, /<PromptBox text=\{words\} setText=\{setText\} pics=\{pics\} busy=\{busy\} onSend=\{submit\}/);
  assert.match(ns, /const agentBox = \(kind === "agent" && how === "general"\) \|\| kind === "chat"/);
  assert.match(ns, /!agentBox && <ButtonBar>\s*\{\/\*[\s\S]*?\*\/\}\s*<Button size="small" variant="contained"/, "the box's own Send, no second one in the footer");
  // ...and no Cancel beside the × (the design walk, 2026-11-20): the × and Esc close it
  assert.doesNotMatch(ns, />Cancel<\/Button>/);
  assert.match(ns, /!aiFor\(await capabilities\(\), "general"\)/, "no AI is the one capability's answer for general work - the demo's agents work");
  assert.ok(ns.includes('/dispatch`, general ? { kind: "general", pick: aiRef.current.pick || null'));
});

// NO KINDS TO PICK (TQ-1397): New is one box - the Assistant makes the words what they are - so there is no row of kinds to lose
test("New has no row of kinds", () => {
  assert.doesNotMatch(ns, /data-tq-new-kinds|KINDS\.map|role="tab"/);
});

// THE AI IS HIS TO CHOOSE (the owner, 2026-11-24: "in New I asked for a certain model astra, the agent did not start with it? maybe it should be
// dropdown there ... we already have the component ... on top of each task"): New's box draws the task header's own chooser (SwitchAi) inside
// it, on Auto - what routing picks - and its list is every AI ready here with its models, HIPAA AI's gemini-4-astra among them
const generalBrains = [{ pick: "cli:claude", label: "Claude Code", models: [{ id: "opus", label: "opus" }] },
  { pick: "connector:7", label: "HIPAA AI" }];
const live = { 7: ["claude-sonnet-5-5", "gemini-4-astra"] };       // ...an AI card's own list, as its provider serves it (/api/ai/models/7)
// ...server-rendered through the real components: no network (the one client answers nothing), and the agents as /api/agents reads them in
// place of the read the page makes once mounted (ui.useAgents)
const STUBS = { name: "stubs", setup(b) {
  const root = new URL("../src", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
  b.onResolve({ filter: /^axios$/ }, () => ({ path: "axios", namespace: "stub" }));
  b.onResolve({ filter: /^\.\/ui\.jsx$/ }, (a) => (a.importer.endsWith("NewSheet.jsx") ? { path: "agents", namespace: "stub" } : undefined));
  b.onLoad({ filter: /^axios$/, namespace: "stub" }, () => ({ loader: "js", contents: "const a = { get: async () => ({ data: {} }), post: async () => ({ data: {} }), interceptors: { request: { use() {} }, response: { use() {} } }, defaults: { headers: { common: {} } } }; export default { ...a, create: () => a };" }));
  b.onLoad({ filter: /^agents$/, namespace: "stub" }, () => ({ resolveDir: root, loader: "jsx", contents: `export * from "./ui.jsx";
    export const useAgents = () => ({ agentsRead: true, codingReady: false, devMode: false, generalBrains: ${JSON.stringify(generalBrains)},
      generalRuns: { pick: "cli:claude", brain: "Claude Code", model: "" } });` }));
} };
const newBox = async () => {
  const hold = setInterval(() => {}, 1000);      // ...the loop held open while esbuild works (Node 22 saw an empty loop)
  try {
    const { build } = await import("esbuild");
    const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: `
      import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser"; import NewSheet from "./src/NewSheet.jsx";
      export const html = () => renderToStaticMarkup(<NewSheet open inline />);` },
      bundle: true, write: false, format: "esm", jsx: "automatic", platform: "node", logLevel: "silent", plugins: [STUBS], define: { "process.env.NODE_ENV": '"production"' },
      loader: { ".css": "empty", ".png": "empty", ".svg": "empty", ".jpg": "empty", ".woff2": "empty", ".json": "json" } });
    const { writeFileSync } = await import("node:fs"), { join } = await import("node:path"), { pathToFileURL } = await import("node:url");
    const f = join((await import("../browser/tempdirs.mjs")).ownTemp("tq-new-"), "new.mjs"); writeFileSync(f, out.outputFiles[0].text);
    return (await import(pathToFileURL(f).href)).html();
  } finally { clearInterval(hold); }
};
test("New's box draws the task header's AI chooser, on Auto, listing every AI ready here and its models", async () => {
  const page = await newBox();
  assert.equal(page.match(/data-tq-switch-ai=""/g)?.length, 1, "one chooser");
  assert.match(page, /data-tq-one-box=""[\s\S]*data-tq-switch-ai=""[\s\S]*tq-aui-send/, "inside the box, before its Send");
  assert.match(page, /Auto · Claude Code/);
  const { cardsOf, switchChoices } = await import("../src/brainOptions.js");
  assert.deepEqual(cardsOf({ generalBrains }), ["7"], "the cards whose own lists the chooser reads");
  const { rows } = switchChoices({ generalBrains, auto: { brain: "Claude Code" }, live });
  assert.deepEqual(rows.map((r) => [r.pick, r.model, !!r.now]), [["", "", true], ["cli:claude", "", false], ["cli:claude", "opus", false],
    ["connector:7", "", false], ["connector:7", "claude-sonnet-5-5", false], ["connector:7", "gemini-4-astra", false]]);
  // ...and once he picks one, that one is ticked and the pill names it
  const picked = switchChoices({ generalBrains, auto: {}, current: "connector:7", model: "gemini-4-astra", live });
  assert.equal(picked.said, "HIPAA AI · gemini-4-astra"); assert.deepEqual(picked.rows.filter((r) => r.now).map((r) => r.model), ["gemini-4-astra"]);
});

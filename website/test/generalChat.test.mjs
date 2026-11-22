import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (f) => readFileSync(fileURLToPath(new URL(f, import.meta.url)), "utf8");


// A QUESTION IS SAID ONCE (the audit, 2026-11-15: the agent's words ended on its question, and "For you to do: Tell me ..." said it again under them)


// The chat's stylesheet styles only what the chat draws: a rule for a class no element carries is a second, drifting copy of a look
// (several such rules still carried the 9px tracked capitals the chat dropped). A class is carried when a source file names it, or
// builds it from a named prefix (`tq-aui-tool-${status}`).
test("every class the chat's stylesheet styles is one some component puts on an element", async () => {
  const { readdirSync } = await import("node:fs");
  const dir = fileURLToPath(new URL("../src/", import.meta.url));
  const src = readdirSync(dir, { recursive: true }).filter((f) => /\.(jsx?|mjs)$/.test(f)).map((f) => readFileSync(dir + f, "utf8")).join("\n");
  const named = new Set(src.match(/tq-[a-z0-9-]*[a-z0-9]/g));
  const prefixes = [...src.matchAll(/(tq-[a-z0-9-]*-)\$\{/g)].map((m) => m[1]);
  const css = read("../src/generalWorkspace.css").replace(/\/\*[\s\S]*?\*\//g, "");
  const styled = new Set([...css.matchAll(/\.(tq-[a-z0-9-]*[a-z0-9])/g)].map((m) => m[1]));
  const unworn = [...styled].filter((c) => !named.has(c) && !prefixes.some((p) => c.startsWith(p)));
  assert.deepEqual(unworn, []);
});

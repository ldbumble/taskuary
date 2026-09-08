import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { agentName, workOf, doingNow, trailText, turnStart, elapsedText, sourceOf, saidFromTail } from "../src/agentWork.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the agent doing the work is named, and never called the assistant", () => {
  assert.equal(agentName({ Kind: "research" }), "Research");
  assert.equal(agentName({ Kind: "marketing" }), "Marketing");
  assert.equal(agentName({ Kind: "coding" }), "Coder");
  // an explicitly assigned worker outranks the kind of work
  assert.equal(agentName({ Kind: "research", Assignee: "agent:Atlas" }), "Atlas");
  // a person owning it is not the agent's name; the kind still is
  assert.equal(agentName({ Kind: "research", Assignee: "owner" }), "Research");
  // "assistant" is the thing that helps you run Taskuary - it is never the name of a worker
  assert.equal(agentName({ Kind: "assistant" }), "Agent");
  assert.equal(agentName({ Kind: "general" }), "Agent");
  assert.equal(agentName({}), "Agent");
  assert.equal(agentName(null), "Agent");
});

test("a call with no result yet is what the agent is doing right now", () => {
  const trace = [
    { type: "start" },
    { type: "tool_call", name: "WebSearch", detail: { tool_call_id: "a", args: { query: "instinct pricing" } } },
    { type: "tool_result", name: "WebSearch", detail: { tool_call_id: "a", result: "…" } },
    { type: "tool_call", name: "WebFetch", detail: { tool_call_id: "b", args: { url: "https://www.vellum.ai/blog/x" } } },
    { type: "tool_result", name: "WebFetch", detail: { tool_call_id: "b", result: "…" } },
    { type: "tool_call", name: "WebFetch", detail: { tool_call_id: "c", args: { url: "https://cellcog.ai/blog/y" } } },
  ];
  const work = workOf(trace);
  assert.equal(work.steps.length, 3);
  assert.equal(work.running.length, 1);
  assert.equal(work.running[0].tool, "WebFetch");
  assert.equal(work.searches.length, 1);
  assert.equal(work.reads.length, 1);
  // what it HAS: the sources it finished reading, named, while it is still working
  assert.deepEqual(work.sources, ["vellum.ai"]);
  assert.equal(doingNow(work), "Reading cellcog.ai");
  assert.equal(trailText(work), "1 search · 1 page read");
});

test("between two calls it says the last thing it did, not nothing", () => {
  const work = workOf([
    { type: "tool_call", name: "WebSearch", detail: { tool_call_id: "a", args: { query: "who pays" } } },
    { type: "tool_result", name: "WebSearch", detail: { tool_call_id: "a", result: "…" } },
  ]);
  assert.equal(work.running.length, 0);
  assert.equal(doingNow(work), "Searching for who pays");
});

test("an empty trace claims no work", () => {
  const work = workOf([]);
  assert.deepEqual(work.steps, []);
  assert.equal(doingNow(work), "");
  assert.equal(trailText(work), "");
  assert.deepEqual(work.sources, []);
  assert.deepEqual(workOf(undefined).steps, []);
});

test("a failed call is finished, and is not counted as a source it has", () => {
  const work = workOf([
    { type: "tool_call", name: "WebFetch", detail: { tool_call_id: "a", args: { url: "https://instinct.co" } } },
    { type: "tool_result", name: "WebFetch", detail: { tool_call_id: "a", result: "403", is_error: true } },
  ]);
  assert.equal(work.running.length, 0);
  assert.equal(work.done[0].error, true);
});

test("the clock is the turn's, not the session's", () => {
  const messages = [
    { role: "user", createdAt: "2026-09-08 09:00:00" },
    { role: "assistant", createdAt: "2026-09-08 09:00:30" },
    { role: "user", createdAt: "2026-09-08 13:36:20" },
  ];
  assert.equal(turnStart(messages), new Date("2026-09-08T13:36:20").getTime());
  assert.equal(turnStart([]), null);
  assert.equal(turnStart([{ role: "assistant", createdAt: "nonsense" }]), null);
  assert.equal(elapsedText(15_000), "15s");
  assert.equal(elapsedText(124_000), "2m 04s");
  assert.equal(elapsedText(0), "0s");
});

test("a conversation's last turn is read out of its pseudo-terminal, without the prompts", () => {
  assert.equal(saidFromTail([
    "you> Before you go further: ask me the ONE question you most need answered.",
    "assistant> Do you have any direct material from Instinct I can analyze?",
    "you>",
  ]), "Do you have any direct material from Instinct I can analyze?");
  assert.equal(saidFromTail(["assistant> I can draft the nomination response, but I need the name."]),
    "I can draft the nomination response, but I need the name.");
  assert.equal(saidFromTail(["you>"]), "");
  assert.equal(saidFromTail([]), "");
  assert.equal(saidFromTail(undefined), "");
});

test("only a real http target names a source", () => {
  assert.equal(sourceOf("https://www.vellum.ai/blog/x"), "vellum.ai");
  assert.equal(sourceOf("C:/repo/notes.md"), "");
  assert.equal(sourceOf(""), "");
});

test("the general assistant's own window is left exactly as it was", () => {
  const view = read("GeneralWorkspace.jsx");
  // every part of the agent-at-work treatment is off in the dock, which IS the assistant
  assert.match(view, /const working = !dock && /);
  assert.match(view, /\{dock && busy && \(/);                       // the dock keeps its own "still working" banner
  assert.match(view, /const name = dock \? "Taskuary" : agentName\(task\)/);   // the dock's turns stay Taskuary's
  assert.match(view, /keepStart = true/);                           // and it keeps the trace's start line
  assert.match(view, /placeholder=\{working \? /);                  // and its composer keeps its own words
});

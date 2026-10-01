// REMIND ME WITH AN AGENT STILL OPEN (press audit, 2026-10-01): it put the task away anyway, and the row sat on under
// "agent waiting on you". The owner: warn that the agent is open and has to be saved and ended first - do not defer.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { agentOpen } from "../src/taskFilter.js";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("agentOpen is a live session on the walk's card - not a saved, stopped or paused one", () => {
  assert.equal(agentOpen({ kind: "agent", lane: "working", sid: "s1" }), true);
  assert.equal(agentOpen({ kind: "agent", lane: "blocked", sid: "s1", asking: true }), true);
  assert.equal(agentOpen({ kind: "agent", lane: "blocked", paused: true, sid: "s1" }), false);
  assert.equal(agentOpen({ kind: "agent", lane: "saved", sid: "s1" }), false);
  assert.equal(agentOpen({ kind: "agent", lane: "stopped", sid: "s1" }), false);
  assert.equal(agentOpen({ kind: "agent", lane: "working" }), false, "a headless run has no session to save and end");
  assert.equal(agentOpen({ kind: "task", lane: "yours" }), false);
  assert.equal(agentOpen(null), false);
});

test("the picker warns instead of offering days while the agent is open, and never posts", () => {
  const src = read("RemindMe.jsx");
  const picker = src.slice(src.indexOf("export function RemindPicker"), src.indexOf("export default function RemindMe"));
  assert.match(picker, /live/);
  assert.match(picker, /Save and end session/);
  assert.match(picker, /\{live && !away \?/, "the warning takes the days' place");
});

test("every Remind me tells the picker whether the agent is open", () => {
  const page = read("TaskPage.jsx");
  const uses = page.split("\n").filter((l) => /<RemindMe |<RemindPicker /.test(l));
  assert.ok(uses.length >= 4, "the three RemindMe buttons and the action row's picker");
  for (const u of uses) assert.match(u, /live=\{liveSession\}/, u);
  const view = read("AssistantView.jsx");
  assert.match(view, /live: agentOpen\(item\)/, "the walk's Remind me knows from the card");
  assert.match(view, /<RemindPicker [^\n]*live=\{remindOn\.live\}/);
});

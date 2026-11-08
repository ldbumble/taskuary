import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { arrange, lineOf, meta } from "../src/searchHits.js";

// F28: a task found by a line of its agent chat (search.py _chat) - under the title hits, tagged, at its line
const title = { type: "task", id: "task:7", tid: 7, title: "Quokka badge order", sub: "general" };
const chat = { type: "task", id: "chat:8", tid: 8, title: "Plan the offsite", sub: "general", tag: "in agent chat", who: "the agent",
  line: "comment-42", snippet: "The quokka room at the venue is free on Friday." };

test("a chat hit is a task, listed after the title hits, tagged with whose line it was", () => {
  assert.deepEqual(arrange([title, chat]).flat.map((h) => h.id), ["task:7", "chat:8"]);
  assert.deepEqual(meta(chat), ["general", "in agent chat", "the agent"]);
  assert.deepEqual(meta(title), ["general"]);
});

test("it opens at its line, and nothing else asks for one", () => {
  assert.equal(lineOf(chat), '[data-tq-chat-line="comment-42"]');
  assert.equal(lineOf(title), ""); assert.equal(lineOf({ line: 'x"]' }), "");
});

test("the row draws the snippet, the pick scrolls to the line, and the chat's lines carry their anchor", () => {
  const src = readFileSync(new URL("../src/SearchEverything.jsx", import.meta.url), "utf8");
  assert.match(src, /hit\.snippet && \(/);
  assert.match(src, /focusPlace\(null, \(\) => document\.querySelector\(lineOf\(h\)\)\)/);
  const ws = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.equal((ws.match(/data-tq-chat-line=\{(line|id)\}/g) || []).length, 2);
});

// Who wrote it is a fact the server sends, never a word the page searches for (the owner, 2026-10-11: "everything should
// be ai"). The wall hardcoded the demo persona's name to know the owner's face; the Timeline searched the classifier's
// sentence for "your reply" to know a row was the owner's own.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { isOwnerAuthor } from "../src/agentIdentity.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the wall knows the owner by the name the server sends with the notes", () => {
  assert.equal(isOwnerAuthor("you", ""), true);
  assert.equal(isOwnerAuthor("owner", ""), true);
  assert.equal(isOwnerAuthor("Alex Doyle", "Alex Doyle"), true);
  assert.equal(isOwnerAuthor(" alex doyle ", "Alex Doyle"), true);
  assert.equal(isOwnerAuthor("Alex Doyle", "Erin Blake"), false);
  assert.equal(isOwnerAuthor("coding", "Alex Doyle"), false);
  assert.equal(isOwnerAuthor("", ""), false);
});

test("no owner name is hardcoded on the wall, and the demo's owner still comes from its fixture", () => {
  const wall = read("AgentWall.jsx");
  assert.doesNotMatch(wall, /whitfield/i);
  assert.match(wall, /setOwnerName\(data\.owner/);
  const fx = JSON.parse(read("demoFixtures.json"));
  assert.equal(fx["/api/board/notes"].owner, fx["/api/whoami"].facts.owner_name);
});

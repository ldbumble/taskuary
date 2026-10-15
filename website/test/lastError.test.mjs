import test from "node:test";
import assert from "node:assert/strict";
import { record, recordAction, snapshot, last, reset } from "../src/lastError.js";

test.beforeEach(() => reset());

test("recordAction skips reads and normalises ids and the query", () => {
  recordAction("GET", "/api/tasks"); recordAction("head", "/api/x"); recordAction("OPTIONS", "/api/x");
  recordAction("post", "/api/tasks/123/notes/0123456789abcdef0123456789ABCDEF?x=1");
  assert.deepEqual(snapshot("Board").actions, ["POST /api/tasks/:id/notes/:id"]);
});

test("only the last five actions are kept", () => {
  for (let i = 0; i < 8; i++) recordAction("PUT", `/api/a${i}`);
  assert.deepEqual(snapshot("x").actions, [3, 4, 5, 6, 7].map((i) => `PUT /api/a${i}`));
});

test("record takes an Error, an axios error, or a string", () => {
  record(new Error("boom")); assert.equal(last().message, "boom"); assert.ok(last().stack.includes("boom")); assert.ok(!isNaN(Date.parse(last().at)));
  record({ message: "Request failed", config: { url: "/api/tasks/42" }, response: { status: 500, data: { detail: "disk full" } } });
  assert.ok(last().message.includes("disk full") && last().message.includes("500")); assert.equal(last().route, "/api/tasks/:id");
  record("plain words"); assert.equal(last().message, "plain words");
});

test("message and stack are capped", () => {
  const e = new Error("m".repeat(5000)); e.stack = "s".repeat(9000); record(e);
  assert.equal(last().message.length, 2000); assert.equal(last().stack.length, 4000);
});

test("snapshot carries screen, error, stack, actions and time", () => {
  recordAction("DELETE", "/api/tasks/7"); record(new Error("bad"));
  const s = snapshot("Settings");
  assert.equal(s.screen, "Settings"); assert.equal(s.error, "bad"); assert.ok(s.stack && s.at); assert.deepEqual(s.actions, ["DELETE /api/tasks/:id"]);
});

test("with no error the snapshot is still a dict", () => assert.deepEqual({ ...snapshot("Home"), at: 0 }, { screen: "Home", route: "", error: "", stack: "", actions: [], at: 0 }));

test("ids of every shape and the host are normalised away", () => {
  recordAction("POST", "http://127.0.0.1:7787/api/tasks/123e4567-e89b-12d3-a456-426614174000/x/deadbeef12/y?q=1");
  recordAction("POST", "/api/repos/some-org/some-repo-name/sync");
  assert.deepEqual(snapshot("x").actions, ["POST /api/tasks/:id/x/:id/y", "POST /api/repos/:id/:id/sync"]);
});

test("an unserialisable detail does not throw", () => {
  const a = {}; a.a = a; record({ message: "m", response: { status: 500, data: { detail: a } } });
  assert.ok(last().message.startsWith("m"));
});

test("the popup's own calls are neither the last error nor an action", () => {
  record(new Error("real one"));
  record({ message: "Request failed", config: { url: "/api/bug-report/draft" }, response: { status: 422, data: { detail: "could not prepare" } } });
  recordAction("POST", "/api/bug-report/draft"); recordAction("POST", "/api/open-url");
  assert.equal(last().message, "real one"); assert.deepEqual(snapshot("x").actions, []);
});

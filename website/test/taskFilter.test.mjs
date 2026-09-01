import test from "node:test";
import assert from "node:assert/strict";
import { filterForSelectedState } from "../src/taskFilter.js";

test("a selected task that finishes moves the rail from in progress to done", () => {
  assert.equal(filterForSelectedState("live", "done"), "done");
});

test("a selected active task reopened from done moves the rail back to in progress", () => {
  assert.equal(filterForSelectedState("done", "working"), "live");
  assert.equal(filterForSelectedState("done", "needs_you"), "live");
});

test("all and matching buckets are left alone", () => {
  assert.equal(filterForSelectedState("", "done"), "");
  assert.equal(filterForSelectedState("live", "working"), "live");
  assert.equal(filterForSelectedState("done", "done"), "done");
});

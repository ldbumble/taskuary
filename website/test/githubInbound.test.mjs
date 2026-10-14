import assert from "node:assert/strict";
import test from "node:test";
import { githubInboundValue } from "../src/githubInbound.js";

test("unconfigured issue pickers follow the connection's current inbound role", () => {
  for (const [roles, expected] of [
    [[], "off"],
    [["tool"], "off"],
    [["trigger"], "tasks"],
    [["feed"], "feed"],
    [["trigger", "feed"], "tasks"],
  ]) {
    assert.equal(githubInboundValue({}, new Set(roles), "issues"), expected, roles.join(","));
    assert.equal(githubInboundValue({ issues: "" }, new Set(roles), "issues"), expected);
  }
});

test("roles never opt a repo into PR ingestion or automatic agent starts", () => {
  for (const roles of [[], ["tool"], ["trigger"], ["feed"], ["trigger", "feed"]]) {
    for (const kind of ["prs", "auto"]) {
      assert.equal(githubInboundValue({}, new Set(roles), kind), "off", `${roles}: ${kind}`);
    }
  }
});

test("explicit repo settings override every connection role, including explicit off", () => {
  const choices = {
    issues: ["tasks", "feed", "replies", "off"],
    prs: ["tasks", "feed", "off"],
    auto: ["off", "team", "contributors", "anyone"],
  };
  for (const roles of [[], ["trigger"], ["feed"]]) {
    for (const [kind, values] of Object.entries(choices)) {
      for (const value of values) {
        assert.equal(githubInboundValue({ [kind]: value }, new Set(roles), kind), value,
          `${roles}: ${kind}=${value}`);
      }
    }
  }
});

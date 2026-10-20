import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { cliCardOf } from "../src/cliCard.js";

test("the CLI agents card is on only when a CLI is connected; installed alone is off and says so", () => {
  const clis = [{ name: "claude", label: "Claude Code", installed: true, configured: false }, { name: "codex", label: "OpenAI Codex CLI", installed: true, configured: false },
    { name: "qwen", label: "Qwen Code", installed: false, configured: false }];
  assert.deepEqual(cliCardOf(clis), { state: "off", desc: "2 installed on this computer · none connected - open to connect one" });
  clis[0].configured = true;
  assert.deepEqual(cliCardOf(clis), { state: "on", desc: "Connected: Claude Code" });
  // a saved connection to a CLI that is not on this machine is not "Connected" (a fresh install, 2026-10-20)
  assert.equal(cliCardOf([{ name: "claude", label: "Claude Code", installed: false, configured: true }]).state, "off");
  assert.equal(cliCardOf([]).state, "off");
  assert.deepEqual(cliCardOf(null), {});
});

test("the card reads it, and its pill says Connected, never Installed", () => {
  const cv = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");
  assert.match(cv, /\.\.\.cliCardOf\(clis\)/);
  assert.doesNotMatch(cv, /"Installed" : "Connected"/);
});

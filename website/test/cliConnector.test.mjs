// The agent connector's line on a CLI card (the owner, 2026-11-06: "will the adapters get installed when you set up claude code cli tool
// in the card section. we need to do that"): its state in words, and the one press that helps - Install, Update, or none.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { connectorLine } from "../src/cliConnector.js";

const cli = (connector, installed = true) => ({ name: "claude", label: "Claude Code", installed, connector });
const at = (status, have = "") => cli({ status, have, want: "0.101.0", pkg: "@agentclientprotocol/claude-agent-acp" });

test("a CLI here without its connector offers Install, and says not installed", () => {
  assert.deepEqual(connectorLine(at("missing")), { text: "Faster agent start: install the connector", state: "not installed", press: "Install" });
});

test("an older connector after a release moves the pin offers Update, with both versions", () => {
  const l = connectorLine(at("update", "0.100.2"));
  assert.equal(l.press, "Update");
  assert.equal(l.state, "0.100.2 installed · 0.101.0 available");
  assert.equal(connectorLine(at("other", "0.102.0")).press, "Install");      // a newer one is not "updated" down to the pin
});

test("installed, installing and no npm are said, with nothing to press", () => {
  assert.deepEqual(connectorLine(at("installed", "0.101.0")), { text: "Agent connector", state: "0.101.0 installed", press: "" });
  assert.equal(connectorLine(at("installing")).press, "");
  assert.match(connectorLine(at("no_npm")).state, /needs npm/);
});

test("no line for a CLI that is not here, or needs no connector", () => {
  assert.equal(connectorLine(cli({ status: "missing" }, false)), null);
  assert.equal(connectorLine(cli(undefined)), null);
  assert.equal(connectorLine(cli({})), null);
});

test("its press goes through the installer's one phase, on the CLI card", () => {
  const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
  assert.match(read("cliInstall.jsx"), /connector: \{ path: "\/api\/cli\/connector"/);
  assert.match(read("cliInstall.jsx"), /const connector = useCallback\(\(cli\) => run\(cli, "connector"\)/);
  assert.match(read("AgentsPanel.jsx"), /<ConnectorLine cli=\{cli\}/);
});

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { finishLine, pickStep, STEP_SAID, stepWords } from "../src/connectorStep.js";
import { canvasRequestFromHash } from "../src/canvasLinks.js";

// "add LinkedIn as a connector": the card comes up with its first real step lit and the line says it (the owner, 2026-10-20)

const btn = (text, primary = true, disabled = false) => ({ kind: "button", text, primary, disabled });
const box = (text, empty = true) => ({ kind: "field", text, empty });

test("the primary button when it can be pressed, else the first empty box that holds it back", () => {
  assert.equal(pickStep([btn("Back", false), box("Client id"), btn("Sign in with LinkedIn")]), 2);
  assert.equal(pickStep([btn("Back", false), box("Client id", false), box("Client secret"), btn("Save", true, true)]), 2);
  assert.equal(pickStep([btn("Test", false), btn("Save", true, true)]), 1);
  assert.equal(pickStep([btn("Back", false)]), -1);
});

test("the line is finished with what was lit", () => {
  const said = `Opened the LinkedIn card under Connections - ${STEP_SAID}. A key or password goes on the card, never in this chat.`;
  assert.equal(finishLine(said, { kind: "button", text: "Sign in with LinkedIn" }),
    "Opened the LinkedIn card under Connections - press Sign in with LinkedIn. A key or password goes on the card, never in this chat.");
  assert.equal(stepWords({ kind: "field", text: "Client id" }), "fill in Client id first");
  assert.equal(finishLine(said, { kind: "button", text: "" }), said);           // nothing lit: the line stands as it was
  assert.equal(finishLine("Opened Settings.", { kind: "button", text: "X" }), "Opened Settings.");
});

test("the link asks for the step, and the card lights it held in view", () => {
  assert.equal(canvasRequestFromHash("#connector=linkedin&step=1").state.step, true);
  assert.equal(canvasRequestFromHash("#connector=linkedin").state.step, undefined);
  const view = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");
  assert.ok(view.includes("data-tq-connector-scope") && view.includes("lightStep(scope"));
  const step = readFileSync(new URL("../src/connectorStep.js", import.meta.url), "utf8");
  assert.ok(step.includes('setAttribute("data-tq-setup-lit", "light")') && step.includes("focusPlace("));
  const css = readFileSync(new URL("../src/assistantView.css", import.meta.url), "utf8");
  assert.ok(css.includes(".MuiInputBase-root[data-tq-setup-lit]"));
  const server = readFileSync(new URL("../../taskuary/concierge.py", import.meta.url), "utf8");
  assert.ok(server.includes(STEP_SAID), "the server says the words the page fills in");
});

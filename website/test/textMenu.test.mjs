import test from "node:test";
import assert from "node:assert/strict";
import { typedInto, shutMenu, installTextMenu } from "../src/textMenu.js";

// TQ-1251: "taskuary is catching the typos, but not allowing me to edit them by clicking on it" - the desktop window's menu, where the
// spelling suggestions live, opens again in a box you type in or over selected text, and nowhere else.
const el = (tagName, props = {}, parentElement = null) => ({ nodeType: 1, tagName, isContentEditable: false, parentElement, ...props });
const win = (desktop, selected = "") => ({ ...(desktop ? { pywebview: {} } : {}), getSelection: () => selected });

test("a box you type in is one; a button, a checkbox or a read-only box is not", () => {
  assert.equal(typedInto(el("TEXTAREA")), true);
  assert.equal(typedInto(el("INPUT", { type: "text" })), true);
  assert.equal(typedInto(el("INPUT", { type: "search" })), true);
  assert.equal(typedInto(el("SPAN", {}, el("DIV", { isContentEditable: true }))), true, "inside an editable region");
  assert.equal(typedInto(el("INPUT", { type: "checkbox" })), false);
  assert.equal(typedInto(el("TEXTAREA", { readOnly: true })), false);
  assert.equal(typedInto(el("BUTTON")), false);
});

test("in the desktop window the menu stays shut outside a box, and opens in one or over selected text", () => {
  assert.equal(shutMenu(el("DIV"), win(true)), true);
  assert.equal(shutMenu(el("TEXTAREA"), win(true)), false);
  assert.equal(shutMenu(el("DIV"), win(true, "a word")), false, "selected text can be copied");
  assert.equal(shutMenu(el("DIV"), win(false)), false, "a browser tab keeps its own menu");
});

test("installed once, on the bubble, leaving a menu a pane already handled alone", () => {
  const seen = [];
  const doc = { defaultView: win(true), addEventListener: (k, f, cap) => seen.push([k, f, cap]), removeEventListener: () => {} };
  installTextMenu(doc); installTextMenu(doc);
  assert.equal(seen.length, 1); assert.equal(seen[0][0], "contextmenu"); assert.equal(seen[0][2], undefined);
  let shut = 0; seen[0][1]({ defaultPrevented: false, target: el("DIV"), preventDefault: () => shut++ });
  seen[0][1]({ defaultPrevented: false, target: el("TEXTAREA"), preventDefault: () => shut++ });
  assert.equal(shut, 1);
});

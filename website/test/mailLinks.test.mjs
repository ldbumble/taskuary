import test from "node:test";
import assert from "node:assert/strict";
import { keepAddresses, linkParts } from "../src/mailLinks.js";

const DOC = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOp/edit?usp=sharing";
const links = (s) => linkParts(s).filter((p) => p.href).map((p) => p.href);

test("a plain-text mail's <address> survives the tag strip as a bare address", () => {
  const got = keepAddresses(`Please see the cash status by clicking HERE <${DOC}>.`).replace(/<[^>]+>/g, " ");
  assert.ok(got.includes(DOC));
  assert.equal(keepAddresses("a <b>bold</b> word"), "a <b>bold</b> word");
});

test("addresses become links and the sentence's punctuation stays text", () => {
  assert.deepEqual(links(`by clicking HERE (${DOC}).`), [DOC]);
  assert.deepEqual(links(`see ${DOC}, then https://vendor.example/a.pdf!`), [DOC, "https://vendor.example/a.pdf"]);
  assert.deepEqual(links("https://en.wikipedia.example/wiki/Foo_(bar)."), ["https://en.wikipedia.example/wiki/Foo_(bar)"]);
  assert.equal(linkParts(`HERE (${DOC}).`).map((p) => p.text).join(""), `HERE (${DOC}).`);
});

test("text with no address is one text part, and nothing but http(s) is a link", () => {
  assert.deepEqual(linkParts("Hi, please mark off which bills to pay."), [{ text: "Hi, please mark off which bills to pay." }]);
  assert.deepEqual(links("javascript:alert(1) mailto:erin@northwind.example ftp://x.example"), []);
});

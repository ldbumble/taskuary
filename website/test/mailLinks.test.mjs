import test from "node:test";
import assert from "node:assert/strict";
import { bareLine, keepAddresses, linkParts, pictureWords, remotePicture, wordsOnly } from "../src/mailLinks.js";
import { gistFor } from "../src/fyiRow.js";

const DOC = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOp/edit?usp=sharing";
const links = (s, l) => linkParts(s, l).filter((p) => p.href).map((p) => p.href);

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

// the owner, 2026-11-03: "hyper links in fyi email like view report are not coming thru" - the words an HTML mail put a link behind
// (message.Links, channels.mail_links) are that link again; web and mail addresses only
test("the words a mail put a link behind become that link, once, in order", () => {
  const R = "https://reports.vendor.example/r/9?u=alex";
  const parts = linkParts("Your October report is ready.\nView\nreport · Write to us", [["View report", R], ["Write to us", "mailto:help@vendor.example"]]);
  assert.deepEqual(parts.filter((p) => p.href), [{ href: R, text: "View\nreport" }, { href: "mailto:help@vendor.example", text: "Write to us" }]);
  assert.equal(parts.map((p) => p.text).join(""), "Your October report is ready.\nView\nreport · Write to us");
  assert.deepEqual(links("Run me now", [["Run me", "javascript:alert(1)"]]), []);
  assert.deepEqual(links("Nothing here", [["View report", R]]), []);
  // ...and an address already in the text stays its own link, never doubled by words over it
  assert.deepEqual(links(`Open ${R}`, [[R, R]]), [R]);
});

// the owner, 2026-11-03: "in a fyi email where entire email was a image it showed nothing"
test("a picture-only mail says what it is: on its card's line, and in the open message that has no words", () => {
  assert.equal(pictureWords("[image: October numbers]"), "Picture: October numbers");
  assert.equal(pictureWords("[remote image]"), "A picture");
  assert.equal(gistFor({ title: "October report", preview: "[image: October numbers]" }), "Picture: October numbers");
  assert.equal(wordsOnly("[image: October numbers]\n[remote image: banner.png]"), "");
  assert.equal(wordsOnly("Thanks [image: logo.png]"), "Thanks");
  assert.ok(remotePicture("[remote image: banner.png]") && !remotePicture("[image: a.png]"));
  assert.equal(bareLine({ drawn: 1 }), "");
  assert.match(bareLine({ remote: true }), /picture on the sender's site, and Taskuary does not load outside pictures - open the original/);
  assert.equal(bareLine({ files: 2 }), "Nothing written in this message - only what is attached.");
  assert.match(bareLine({}), /nothing attached came through - open the original/);
});

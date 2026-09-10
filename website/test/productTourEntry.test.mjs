import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the question mark opens How Taskuary works, and still offers a way to report a problem", () => {
  const page = read("TaskHubPage.jsx");
  assert.match(page, /function HelpMenu/);
  assert.match(page, /How Taskuary works/);
  assert.match(page, /Report a problem/);
  assert.match(page, /<ProductTour open=\{tourOpen\}/);
  assert.match(page, /onTour=\{openTour\}/);
  assert.doesNotMatch(page, /IconButton component="a" href=\{SUPPORT_URL\}/);
});

test("the walkthrough is offered once, after setup is out of the way, and #tour always starts it", () => {
  const page = read("TaskHubPage.jsx");
  assert.match(page, /shouldOfferTour/);
  assert.match(page, /hashWantsTour\(window\.location\.hash\)/);
  assert.match(page, /addEventListener\(TOUR_EVENT/);
  assert.match(page, /rememberTour\(reason === "done" \? "done" : "skipped"\)/);
});

test("the Assistant welcome can start the same walkthrough without leaving the chat", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /from "\.\/productTour\.js"/);
  assert.match(view, /onClick=\{\(\) => requestTour\(\)\}/);
  assert.match(view, />How Taskuary works</);
});

test("each page the walkthrough names has a tab marker on the strip", () => {
  const page = read("TaskHubPage.jsx");
  assert.match(page, /data-tour="tab-Assistant"/);
  assert.match(page, /data-tour=\{`tab-\$\{t\}`\}/);
  assert.match(page, /data-tour="pages"/);
});

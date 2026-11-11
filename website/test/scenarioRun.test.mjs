import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// What the scenario run (2026-11-06: many messages, many tasks, three widths) found off by a pixel or a word, pinned

// A FOLDED TURN'S ONE LINE is cut where it ends - its whole words on hover too, not only a press away
test("the folded What I did line carries its whole words as its title", () => {
  assert.match(read("AgentSummary.jsx"), /<Box component="summary" title=\{did\} sx=\{\{ \.\.\.HEAD, mt: 0, cursor: "pointer", whiteSpace: "nowrap"/);
});
// THE RAIL'S FOOT FADE reaches the card's inner edge: a pixel short, a row's top showed through as a dark sliver (the scenario run, 2026-11-06)
test("the rail's bottom fade sits on the card's inner edge", () => {
  assert.match(read("FeedView.jsx"), /position: "absolute", left: "1px", right: "1px", bottom: 0, zIndex: 6,/);
});



// AN ACTION CARD'S PICK is as wide as what it shows, and the keyboard sees it (the scenario run, 2026-11-06: "Anyone" a word's gap from its chevron)
test("an action card's choice sizes to its pick and rings on keyboard focus", () => {
  assert.match(read("ActionCard.jsx"), /fieldSizing: "content", borderRadius: "4px", "&:focus-visible": \{ outline: `2px solid \$\{ACCENT\}`, outlineOffset: 1 \} \};/);
});


// A REPORT MADE A TASK says where it went on its row - and squeezed, its words drop out whole, never "Mo…" (the scenario run, 2026-11-06)
test("a moved row's words wrap away whole before they are cut", () => {
  const css = read("assistantView.css"), av = read("AssistantView.jsx");
  assert.match(css, /\.tq-pile-moved \{[^}]*flex-direction: row-reverse; flex-wrap: wrap;[^}]*height: 1\.5em; overflow: hidden;/);
  assert.match(css, /\.tq-pile-moved \.w \{ flex: 0 0 auto; \}/);
  assert.match(css, /\.tq-pile-moved \{ flex: 0 1000 auto; min-width: 5em;/, "it gives way before the title, down to its ref");
  assert.ok(av.indexOf('<span className="ref" role="link"') < av.indexOf('<span className="w">Moved to Tasks ·</span>'), "the ref comes first in the page");
});


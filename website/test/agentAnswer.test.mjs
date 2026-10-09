// The agent's answer on the task card, short: one line per item, the whole of it one click away (the owner, 2026-10-09).
import test from "node:test";
import assert from "node:assert/strict";
import { answerOutline } from "../src/agentAnswer.js";

const ANSWER = `# TQ-0042 — 1. Upload the supervisor sheet
2. Pull supervisors from the HR feed

Hi,

All three are handled. Each change is built and tested.

1. Supervisor upload template. The Corporate Supervisors page now has a Download Template button.

2. **HR feed.** Yes, the app has the HR employee data, refreshed nightly.
   It is read once a day.

3. Browser tab. The app now has a tab icon.
`;

test("each numbered item is one short line, and the title heading and greeting are not the answer", () => {
  const o = answerOutline(ANSWER);
  assert.deepEqual(o.items.map((i) => [i.n, i.short]), [[1, "Supervisor upload template."], [2, "HR feed."], [3, "Browser tab."]]);
  assert.equal(o.intro, "All three are handled.");
  assert.doesNotMatch(o.full, /^# TQ-0042|Pull supervisors from the HR feed\n\nHi/);
  assert.match(o.full, /^Hi,/);
});

test("an answer with no list keeps its first sentence and nothing else is invented", () => {
  const o = answerOutline("Nothing needed changing: the export already drops the transfers. I checked August and July.");
  assert.deepEqual(o.items, []);
  assert.equal(o.intro, "Nothing needed changing:");
});

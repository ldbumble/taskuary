import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

// COLLECTIONS START NULL (the 2026-10-19 UI walk, G8): a list a component fetches, started as [], cannot tell "still reading" from
// "there are none" - a goal said "no steps yet" over the five it was loading, and said it for good when the read failed (its catch
// set [] too). A fetched list starts as null, so loading, failed and empty can each be drawn as themselves.
// THE ONES BEFORE THE RULE (2026-10-20), left for their own passes - a new one may not join them, and one fixed comes off the list.
const KNOWN = new Set([
  "AiDefaults.jsx live", "AssistantView.jsx chats", "ConnectorsView.jsx drivers", "ConnectorsView.jsx sources", "ConnectorsView.jsx types",
  "DocsView.jsx books", "DocsView.jsx people", "EmailSomeone.jsx targets", "EmailSomeone.jsx boxes", "Handoff.jsx targets", "Handoff.jsx people",
  "ReportsView.jsx customers", "ReportsView.jsx brains", "ReportsView.jsx targets", "RoleStart.jsx roles", "SettingsView.jsx brains",
  "SettingsView.jsx connectors", "SettingsView.jsx rows", "TaskHubPage.jsx items", "TaskHubPage.jsx news", "TaskPage.jsx repos", "TasksView.jsx repos",
  "ui.jsx brainList", "ui.jsx generalBrains", "ui.jsx people", "AssistantGame.jsx agents", "AssistantGame.jsx pile", "FirstRun.jsx conns",
  "GeneralWorkspace.jsx reviews", "GeneralWorkspace.jsx tasks", "NewPlaybookDialog.jsx rows", "ReportsView.jsx types", "ReportsView.jsx connectors",
  "SettingsView.jsx settings", "SettingsView.jsx memory", "SkillImport.jsx rows", "ui.jsx agents",
  // ...and lists the page builds itself, which the scan cannot tell from a fetch: no loading state to draw
  "AssistantView.jsx msgs", "promptImages.jsx imgs", "SoulInterview.jsx answers",
]);
const dir = fileURLToPath(new URL("../src/", import.meta.url));
// a list state whose setter is handed an answer from the server in the same file
const fetchedLists = (file, text) => [...text.matchAll(/const \[(\w+), (set\w+)\] = useState\(\[\]\)/g)]
  .filter(([, , set]) => text.split("\n").some((l) => l.includes(`${set}(`) && /\bapi\.|\bdata\b|\(await /.test(l)))
  .map(([, name]) => `${file} ${name}`);

test("a list a component fetches starts as null, not as an empty list", () => {
  const found = readdirSync(dir).filter((f) => f.endsWith(".jsx")).flatMap((f) => fetchedLists(f, readFileSync(dir + f, "utf8")));
  const fresh = found.filter((k) => !KNOWN.has(k));
  assert.deepEqual(fresh, [], `fetched into useState([]) - start it as null and draw loading, failed and empty apart: ${fresh.join(", ")}`);
  assert.ok(found.length > 5, "the scan found nothing - the pattern no longer matches the source");
});

test("the goal's steps start null, and a failed read is said, not drawn as no steps", () => {
  const page = readFileSync(dir + "TaskPage.jsx", "utf8");
  assert.match(page, /const \[steps, setSteps\] = useState\(\(\) => heldSteps\(task\.TaskId\)\);/);
  assert.match(page, /\.catch\(\(\) => setStepsFailed\(true\)\)/);
  assert.match(page, /The steps didn't load\./);
  assert.doesNotMatch(page, /catch\(\(\) => setSteps\(\[\]\)\)/);
});

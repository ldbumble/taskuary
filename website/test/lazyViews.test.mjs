// The views kept out of the entry chunk (lazyView.jsx) stay out: one static import from a module the first screen loads pulls a
// view - and everything under it - back into the bundle every page parses before it paints, with only a build warning to say so.
// Each may be imported statically only from modules that are themselves in a split chunk.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

const src = new URL("../src/", import.meta.url);
const read = (f) => readFileSync(new URL(f, src), "utf8");
const SPLIT = {   // view: the modules allowed a static import of it (all in split chunks)
  "CanvasBrowse.jsx": ["FirstRun.jsx"], "FirstRun.jsx": [], "GeneralWorkspace.jsx": ["DemoJourney.jsx"], "DemoJourney.jsx": [],
  "ConnectorsView.jsx": ["FirstRun.jsx"], "ReportsView.jsx": ["WorkflowSteps.jsx", "DashboardEditor.jsx"], "SettingsView.jsx": [],
  "BoardView.jsx": ["AssistantGame.jsx", "WallView.jsx"],
};
const files = readdirSync(src).filter((f) => /\.(jsx?|mjs)$/.test(f));

test("a split view is never imported statically from the first screen's modules", () => {
  for (const [view, allowed] of Object.entries(SPLIT)) {
    const re = new RegExp(`^import\\s[^;]*?from\\s+["']\\./${view.replace(".", "\\.")}["']`, "m");
    const by = files.filter((f) => f !== view && re.test(read(f)));
    assert.deepEqual(by.filter((f) => !allowed.includes(f)), [], `${view} is imported statically by`);
  }
});

test("each is loaded through lazyView where the first screen draws it", () => {
  assert.match(read("AssistantView.jsx"), /const FirstRun = lazyView\(\(\) => import\("\.\/FirstRun\.jsx"\)\)/);
  assert.match(read("AssistantView.jsx"), /const CanvasBrowse = lazyView\(\(\) => import\("\.\/CanvasBrowse\.jsx"\)\)/);
  assert.match(read("AssistantView.jsx"), /const GeneralWorkspace = lazyView\(loadGeneral\)/);
  for (const v of ["ConnectorsView", "ReportsView", "SettingsView"]) assert.match(read("CanvasBrowse.jsx"), new RegExp(`const ${v} = lazyView\\(\\(\\) => import\\("\\./${v}\\.jsx"\\)\\)`));
  assert.match(read("TaskHubPage.jsx"), /const BoardView = lazyView\(\(\) => import\("\.\/BoardView\.jsx"\)\)/);
});

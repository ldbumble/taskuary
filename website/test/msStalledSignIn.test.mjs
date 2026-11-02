import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const cv = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");
// the Microsoft card's browser-waiting branch, up to its device-code one
const waiting = () => { const i = cv.indexOf(') : flow?.mode === "browser" ? ('); return cv.slice(i, cv.indexOf(") : flow ? (", i)); };

// the owner, 2026-11-02: a colleague's corporate tenant asked for an admin's approval and Microsoft's own page ended on AADSTS900971
// "No reply address provided" - the browser never came back, and the card just waited
test("a browser sign-in not back in 90 seconds says why, with the approval link the card already has", () => {
  assert.match(cv, /const STALL_MS = 90 \* 1000;/);
  // the timer runs only for a browser round, starts over with each round, and fetches the existing admin link when none is shown yet
  assert.match(cv, /useEffect\(\(\) => \{\s+setStalled\(false\);\s+if \(flow\?\.mode !== "browser"\) return undefined;\s+const id = setTimeout\(\(\) => \{ setStalled\(true\); if \(!adminUrl\) adminLink\(\); \}, STALL_MS\);\s+return \(\) => clearTimeout\(id\);\s+\}, \[flow\]\);/);
  assert.match(cv, /const adminLink = async \(\) => \{\s+try \{ const \{ data \} = await api\.get\(`\/api\/connectors\/\$\{conn\.ConnectorId\}\/ms\/adminlink`\); setAdminUrl\(data\.url\); \}/, "the card's own admin link, no new endpoint");
  // the line sits in the waiting state, beside the code fallback that is already there
  const wait = waiting();
  assert.match(wait, /Sign in with a code instead<\/Button>/);
  assert.match(wait, /\{stalled && <Box component="span" data-tq-ms-stalled=""/);
  const line = wait.slice(wait.indexOf("data-tq-ms-stalled")).replace(/\s+/g, " ");
  for (const w of ["The sign-in didn't come back.", "asked for an admin's approval", "AADSTS900971", '"No reply address provided"', '"Need admin approval"',
    "your IT admin approves Taskuary once with the link below"]) assert.ok(line.includes(w), w);
  // ...and the link box (copyable) draws whenever there is a link and nobody is signed in - during the wait too
  assert.match(cv, /\{adminUrl && !signedIn && \(/);
  assert.match(cv, /onClick=\{\(\) => copy\(adminUrl\)\} title="copy the link"/);
});

test("no new buttons: the stalled line adds none", () => {
  const wait = waiting();
  assert.equal((wait.match(/<Button/g) || []).length, 2, "Sign in with a code instead + Cancel, as before");
});

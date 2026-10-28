// SIGN IN WITH GOOGLE FOR THE CALENDAR (the owner, 2026-10-26: "yes" to the Gmail card offering it): one step on the Gmail card while
// no Google calendar is on it - it opens Google, finishes by itself - on Taskuary's own Google client (the owner, 2026-10-26: "don't
// want to create my own google client, want to use their own"): a build without one draws no step, and sends nobody to Cloud.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = (f) => fs.readFileSync(path.join(import.meta.dirname, "../src", f), "utf8");

test("the Gmail card carries the step, above Allow saving files", () => {
  const cv = src("ConnectorsView.jsx");
  assert.match(cv, /import \{ GoogleCalendar \} from "\.\/GoogleCalendar\.jsx";/);
  assert.match(cv, /conn\.Type === "gmail" && <GoogleCalendar conn=\{conn\} cfg=\{cfg\} reload=\{reload\} \/>\}\n\s+\{conn\.Type === "gmail" && <GoogleFiles/);
});

test("it signs in through the card's own routes and finishes by itself", () => {
  const g = src("GoogleCalendar.jsx");
  assert.match(g, /export const G_CAL = "Sign in with Google for the calendar";/);
  assert.match(g, /const base = `\/api\/connectors\/\$\{conn\.ConnectorId\}\/google\/calendar`;/);
  assert.match(g, /api\.post\(base\)/);
  assert.match(g, /api\.post\(`\$\{base\}\/poll`, \{ flow: flow\.flow \}\)/);
  assert.match(g, /api\.post\(`\$\{base\}\/cancel`, \{ flow: flow\.flow \}\)/);
  assert.match(g, /window\.open\(data\.url, "_blank", "noopener"\)/);
});

test("shown only while no Google calendar is on the card; a build with no Google client draws none", () => {
  const g = src("GoogleCalendar.jsx");
  assert.match(g, /const signedIn = saved\(conn, "google_refresh_token"\)/);
  assert.match(g, /if \(signedIn && !detail\) return null;/);
  assert.match(g, /export const G_CAL_NONE = "Google sign-in isn't available in this build yet";/);
  assert.match(g, /api\.get\(base\)\.then\(\(\{ data \}\) => \{ if \(alive\) setCan\(!!data\.available\); \}\)/);
  // ...and a build without one draws no step at all: a disabled button saying so was a dead box (the setup sweep, 2026-10-28)
  assert.match(g, /if \(!can && !flow && !detail\) return null;/);
  assert.doesNotMatch(g, /: can \? G_CAL : G_CAL_NONE\}/);
  assert.match(src("FileAccess.jsx"), /if \(!can && !cfg\.allow_files\) return null;/);
  assert.doesNotMatch(g, /Google Cloud|OAuth client of your own|client id and secret/);          // no instructions to make a client
  assert.match(g, /setDetail\(e\?\.response\?\.data\?\.detail \|\| "could not start the sign-in"\)/);   // the server's 409 is said as is
});

test("the card's own Google client folds behind Admin?, as Outlook's tenant app does", () => {
  const cv = src("ConnectorsView.jsx");
  assert.match(cv, /const G_APP_KEYS = \["google_client_id", "google_client_secret", "google_refresh_token"\];/);
  assert.match(cv, /const \[gOwn, setGOwn\] = useState\(!!cfg\.google_client_id\);/);
  assert.match(cv, /conn\.Type === "gmail" && !gOwn \? G_APP_KEYS : \[\]/);
  assert.match(cv, /Admin\? Use your own Google OAuth client instead →/);
  assert.match(src("FileAccess.jsx"), /const can = \(conn\.ConfigSaved \|\| \[\]\)\.includes\("google_refresh_token"\)/);
});

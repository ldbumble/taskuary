// SIGN IN WITH GOOGLE FOR THE CALENDAR (the owner, 2026-10-26: "yes" to the Gmail card offering it): one step on the Gmail card while
// no Google calendar is on it - it opens Google, finishes by itself, and with no OAuth client says what is needed (googlecal.py).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = (f) => fs.readFileSync(path.join(import.meta.dirname, "../src", f), "utf8");

test("the Gmail card carries the step, above Allow saving files", () => {
  const cv = src("ConnectorsView.jsx");
  assert.match(cv, /import \{ GoogleCalendar \} from "\.\/GoogleCalendar\.jsx";/);
  assert.match(cv, /conn\.Type === "gmail" && <GoogleCalendar conn=\{conn\} cfg=\{cfg\} reload=\{reload\} \/>\}\n\s+\{conn\.Type === "gmail" && <Box sx=\{\{ mb: 2 \}\}><GoogleFiles/);
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

test("shown only while no Google calendar is on the card, and plain about a missing client", () => {
  const g = src("GoogleCalendar.jsx");
  assert.match(g, /const signedIn = saved\(conn, "google_refresh_token"\)/);
  assert.match(g, /if \(signedIn && !detail\) return null;/);
  assert.match(g, /G_CAL_NEEDS = "Needs a Google OAuth client of your own first:[^"]*client id and secret[^"]*"/);
  assert.match(g, /\{!can && !flow && !detail && <Typography[^>]*>\{G_CAL_NEEDS\}<\/Typography>\}/);
  assert.match(g, /setDetail\(e\?\.response\?\.data\?\.detail \|\| "could not start the sign-in"\)/);   // the server's 409 is said as is
});

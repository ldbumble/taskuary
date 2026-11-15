// SIGN IN WITH GOOGLE on the Gmail card (the owner, 2026-11-15: mail and calendar through Google's own sign-in, beside the App Password):
// one box at the top of the card - it opens Google, finishes by itself - on the install's OWN Google client, as Microsoft: a card
// without one lists the steps to make it and holds its two boxes. Never a button that says it cannot.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = (f) => fs.readFileSync(path.join(import.meta.dirname, "../src", f), "utf8");

test("the Gmail card carries the box, above Allow saving files, with the client's two boxes inside it", () => {
  const cv = src("ConnectorsView.jsx");
  assert.match(cv, /import \{ GoogleCalendar \} from "\.\/GoogleCalendar\.jsx";/);
  assert.match(cv, /conn\.Type === "gmail" && <GoogleCalendar conn=\{conn\} cfg=\{cfg\} reload=\{reload\} flush=\{boxes\.flush\} onSignedIn=\{\(\) => setStep\(1\)\}>/);
  assert.match(cv, /m\.fields\.filter\(\(\[, key\]\) => G_APP_KEYS\.includes\(key\)\)\.map\(\(f\) => <ConfigField key=\{f\[1\]\} size="small" conn=\{conn\} field=\{f\}/);
  assert.match(src("GoogleCalendar.jsx"), /<Box data-tq-google-client=""[^>]*>\{children\}<\/Box>/);
  assert.match(cv, /<\/GoogleCalendar>\}\n\s+\{conn\.Type === "gmail" && <GoogleFiles/);
  // the client's boxes are the sign-in box's own: never under Credentials, and no "Admin?" fold in front of them
  assert.match(cv, /const G_APP_KEYS = \["google_client_id", "google_client_secret"\];/);
  assert.match(cv, /conn\.Type === "gmail" \? G_APP_KEYS : \[\]/);
  assert.doesNotMatch(cv, /gOwn|Use your own Google OAuth client instead|blank uses Taskuary's/);
  assert.doesNotMatch(cv, /\["Google refresh token/);                                  // nothing is pasted from a consent round made elsewhere
});

test("it signs in through the card's own routes and finishes by itself", () => {
  const g = src("GoogleCalendar.jsx");
  assert.match(g, /export const G_SIGNIN = "Sign in with Google";/);
  assert.match(g, /const base = `\/api\/connectors\/\$\{conn\.ConnectorId\}\/google\/calendar`;/);
  assert.match(g, /await flush\?\.\(\);/);                                              // the two boxes are saved before Google is asked with them
  assert.match(g, /api\.post\(base\)/);
  assert.match(g, /api\.post\(`\$\{base\}\/poll`, \{ flow: flow\.flow \}\)/);
  assert.match(g, /api\.post\(`\$\{base\}\/cancel`, \{ flow: flow\.flow \}\)/);
  assert.match(g, /window\.open\(data\.url, "_blank", "noopener"\)/);
  assert.match(g, /if \(data\.status === "ok"\) \{ reload\?\.\(\); onSignedIn\?\.\(\); \}/);
});

test("a card with no Google client lists the steps to make one - no dead button, no 'not in this build'", () => {
  const g = src("GoogleCalendar.jsx");
  assert.match(g, /\{st && !can && !typed && <>/);
  for (const step of [/New project/, /Gmail API/, /Google Calendar API/, /People API/, /Test users/, /<b>Desktop app<\/b>/, /Publish app/]) assert.match(g, step);
  assert.match(g, /disabled=\{busy \|\| !\(can \|\| typed\)\}/);                          // lit as soon as the two boxes hold a client
  assert.doesNotMatch(g, /isn't available in this build|G_CAL_NONE/);
  assert.match(g, /setDetail\(e\?\.response\?\.data\?\.detail \|\| "could not start the sign-in"\)/);   // the server's 409 is said as is
});

test("signed in it is one quiet line; a lapsed or read-only sign-in is the server's line with Sign in again", () => {
  const g = src("GoogleCalendar.jsx");
  assert.match(g, /const signedIn = saved\(conn, "google_refresh_token"\)/);
  assert.match(g, /const again = signedIn && !!st\?\.again, can = !!st\?\.available;/);
  assert.match(g, /if \(signedIn && !again && !flow && state !== "error"\) \{/);
  assert.match(g, /\{again \? <Typography variant="body2" role="alert" data-tq-google-again=""[^>]*>\{st\.said\}<\/Typography>/);
  assert.match(g, /: again \? "Sign in again" : G_SIGNIN\}/);
  // ...asked again when a poll's error comes or goes: the lapse a poll found reaches the box without a reload
  assert.match(g, /const read = \[signedIn, cfg\.google_client_id \|\| "", saved\(conn, "google_client_secret"\), conn\.HasSecret, conn\.LastError \|\| "", state\]\.join\("\|"\);/);
  assert.match(src("FileAccess.jsx"), /if \(!can && !cfg\.allow_files\) return null;/);
  assert.match(src("FileAccess.jsx"), /const can = \(conn\.ConfigSaved \|\| \[\]\)\.includes\("google_refresh_token"\)/);
});

test("a Gmail card signed in with Google ticks Credentials without an App Password", () => {
  assert.match(src("ConnectorsView.jsx"), /\(!!conn\.HasSecret \|\| \(conn\.Type === "gmail" && savedOn\(conn, "google_refresh_token"\)\)\) && !!conn\.LastSyncAt && !conn\.LastError\)/);
});

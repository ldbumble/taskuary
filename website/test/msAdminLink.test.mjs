import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const cv = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");
const flat = cv.replace(/\s+/g, " ");
// the Microsoft card's approval-link box, from its heading to the link itself
const box = () => { const i = flat.indexOf("Approval link for your Microsoft 365 admin"); return flat.slice(i, flat.indexOf("{adminUrl}</Typography>", i)); };

// an admin opened the approval link and Microsoft stopped on AADSTS900971 "No reply address provided": v2.0/adminconsent returns only to a
// Web reply URL and the app's one redirect is a desktop one. The link is now the authorize page with prompt=admin_consent, returning to
// http://localhost/api/ms/callback - so after Accept the admin's browser may not connect
test("the approval box tells the admin what to do and that a page that won't load afterwards is expected", () => {
  for (const w of ["They open the link, sign in, and click Accept", "If the page after Accept says it can't connect, that's expected: the approval is done.",
    "Grant admin consent on the app's API permissions page does the same."]) assert.ok(box().includes(w), w);
  assert.ok(!box().includes("nativeclient"));
});

test("the card says plainly what AADSTS900971 means, wherever it comes back", () => {
  assert.match(cv, /const NO_REPLY = \/AADSTS900971\/;/);
  const msSays = new Function(`const NO_REPLY = /AADSTS900971/; return ${cv.match(/export const msSays = ([\s\S]*?: d;)/)[1].replace(/;$/, "")};`)();
  const said = msSays("invalid_request: AADSTS900971: No reply address provided.");
  assert.match(said, /approval step/); assert.match(said, /your IT admin approves Taskuary once with the link below/);
  assert.equal(msSays("you declined the sign-in"), "you declined the sign-in", "anything else as it was");
  // a sign-in error carrying it draws the link even when the server sent none
  assert.match(cv, /setDetail\(msSays\(data\.detail \|\| "the sign-in did not complete"\)\);/);
  assert.match(cv, /if \(data\.admin_consent_url\) setAdminUrl\(data\.admin_consent_url\); else if \(NO_REPLY\.test\(data\.detail \|\| ""\)\) adminLink\(\);/);
  // ...and an admin who saw it on an approval link from an older Taskuary is told to use this one
  assert.ok(box().includes("Your admin saw error AADSTS900971 (\"No reply address provided\")? Their link came from an older Taskuary - send them this one."));
});

test("the own-registration steps no longer ask for the nativeclient redirect", () => {
  assert.ok(!cv.includes("oauth2/nativeclient"));
  assert.match(cv, /redirect URI \{code\(MS_REDIRECT\)\}/);
});

// THE COMPANY'S OWN APP (the owner, 2026-11-05: "i don't want it to go through my azure"): no app id ships, the card asks for the
// company's two ids and shows IT the steps, and both roads - the browser and the code - wait for them
const own = () => { const i = flat.indexOf("const MsOwnApp = "); return flat.slice(i, flat.indexOf("export const MsSignIn", i)); };
test("the Microsoft card asks for the company's own app, with the steps IT follows", () => {
  assert.match(cv, /export const MS_REDIRECT = "http:\/\/localhost\/api\/ms\/callback";/);
  for (const w of ["New registration", "single tenant", "Mobile and desktop applications", "Allow public client flows: <b>Yes</b>",
    "Microsoft Graph → Delegated: {code(conn.MsScopes || \"\")}", "<b>Grant admin consent</b>", "Application (client) ID", "Directory (tenant) ID",
    "in the browser, or with a code", "onClick={() => copy(MS_REDIRECT)}", "conn.MsRedirect"]) assert.ok(own().includes(w), w);
  assert.equal((own().match(/<li>/g) || []).length, 6, "one numbered list of six");
  assert.doesNotMatch(own(), /<Button|<Dialog/, "the fields, the Copy and the words - nothing more");
  assert.match(flat, /disabled=\{busy \|\| needsApp\} onClick=\{\(\) => start\(\)\}/, "the browser sign-in waits for the ids");
  assert.match(flat, /disabled=\{busy \|\| needsApp\} onClick=\{\(\) => start\(files, true\)\}/, "...and so does the code");
  assert.match(flat, /This card signed in through the Microsoft app Taskuary used to ship/, "a card from before says what to do");
});

// A REGULAR OUTLOOK.COM PERSON (the owner, 2026-11-09: "sign in with device in outlook does not work any more why?? for regular users
// not enterprise"): no shared app, so the card walks them through their own - the free directory Microsoft now requires first, the
// account type that takes personal accounts, and only the client id to paste: no tenant, no account-type switch
test("with no app yet, the card walks an Outlook.com person through registering their own", () => {
  const o = own();
  for (const w of ["<b>Outlook.com or Hotmail account?</b>", "<a href={MS_AZURE_FREE}", "free Azure account", "credit or debit card",
    "it charges nothing", "<a href={MS_REGISTER}", "<b>{MS_AUDIENCE}</b>", "Leave the Directory (tenant) ID blank",
    "copy the Application (client) ID into the box below", "Allow public client flows: <b>Yes</b>"]) assert.ok(o.includes(w), w);
  assert.match(cv, /export const MS_AUDIENCE = "Any Entra ID Tenant \+ Personal Microsoft accounts";/);
  assert.match(cv, /export const MS_AZURE_FREE = "https:\/\/azure\.microsoft\.com\/free";/);
  assert.match(cv, /export const MS_REGISTER = "https:\/\/entra\.microsoft\.com\/#view\/Microsoft_AAD_RegisteredApps\/ApplicationsListBlade";/);
  assert.ok(!/label="Directory \(tenant\) ID"[^/]*required=/.test(o), "the tenant box is not required");
  assert.doesNotMatch(o, /Account type|<Select|<RadioGroup|<Switch/, "no account-type choice: the server infers it");
});

test("the sign-in buttons wait for the client id alone", () => {
  const src = cv.match(/export const msNeedsApp = (\(conn, cfg\) => [^\n]*);/)[1];
  const needs = new Function(`return ${src}`)();
  assert.equal(needs({ MsApp: "" }, {}), true, "nothing yet: the steps and greyed buttons");
  assert.equal(needs({ MsApp: "" }, { client_id: "1b2c3d4e-0000-0000-0000-00000000000c" }), false, "an Outlook.com app: no tenant needed");
  assert.equal(needs({ MsApp: "" }, { client_id: "  " }), true);
  assert.equal(needs({ MsApp: "outlook" }, {}), false, "a Teams card borrowing the Outlook card's app");
  assert.match(flat, /title=\{needsApp \? "Enter your app's Application \(client\) ID first - the steps are above" : undefined\}/);
});

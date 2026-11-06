// ABOUT YOU IS THE FACE IN THE CORNER (the owner, 2026-11-06: "it should be profile in corner which is the profile picture that is the
// about you page in top right corner next to the power button"): a round avatar after Quit, its tooltip "About you", opening that page.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { PROFILE_TIP, initialsOf, profileFace } from "../src/profileAvatar.js";

const src = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the initials are the first and last word's, as About you's own monogram draws them", () => {
  assert.equal(initialsOf("Alex Doyle"), "AD");
  assert.equal(initialsOf("  alex  "), "A");
  assert.equal(initialsOf("Mary-Jane Erin Blake"), "MB");
  assert.equal(initialsOf(""), "T");
  assert.equal(initialsOf(null), "T");
});

test("the corner draws the avatar About you keeps, the initials where there is none", () => {
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160"><text>AD</text></svg>';
  const f = profileFace({ facts: { owner_name: "Alex Doyle" }, avatar: svg });
  assert.equal(f.initials, "AD");
  assert.ok(f.pic.startsWith("data:image/svg+xml;utf8,") && decodeURIComponent(f.pic.split(",")[1]) === svg);
  assert.deepEqual(profileFace({ facts: { owner_name: "Alex Doyle" }, avatar: "" }), { initials: "AD", name: "Alex Doyle", pic: "" });
  assert.equal(profileFace(null).initials, "T", "before the read lands");
  assert.equal(profileFace({ avatar: "not an svg" }).pic, "");
});

test("it is the top bar's last button, after Quit, on a phone too, and opens About you", () => {
  const page = src("TaskHubPage.jsx"), bar = page.slice(page.indexOf('<Box id="tqTopNav"'));
  const quit = bar.indexOf("<QuitButton "), face = bar.indexOf("<ProfileButton "), end = bar.indexOf("</Box>", face);
  assert.ok(quit > 0 && face > quit, "beside the power button, to its right");
  assert.match(bar.slice(face, end), /^<ProfileButton [^\n]*\/>\s*$/, "nothing after it in the bar");
  assert.match(bar, /\n\s*<ProfileButton onOpen=\{\(\) => go\("About"\)\} \/>/, "no phone gate");
  assert.match(page, /About: "about"/, "go(\"About\") opens the canvas's about area");
  const b = src("ProfileButton.jsx");
  assert.equal(PROFILE_TIP, "About you");
  assert.match(b, /<Tooltip title=\{PROFILE_TIP\}>/);
  assert.match(b, /aria-label=\{PROFILE_TIP\} data-tq-profile=""/);
  assert.match(b, /borderRadius: "50%"/, "round");
  assert.match(b, /api\.get\("\/api\/whoami"\)/);
  assert.doesNotMatch(b, /DEMO/, "the demo shows its own owner's face");
});

test("About you redraws the corner when the name or the avatar changes", () => {
  const a = src("AboutYou.jsx");
  assert.match(a, /window\.dispatchEvent\(new Event\(PROFILE_CHANGED\)\)/);
  assert.match(a, /api\.patch\("\/api\/whoami", fields\)\)\.data\); changed\(\);/);
  assert.match(a, /load\(\); changed\(\);/);
  assert.match(src("ProfileButton.jsx"), /window\.addEventListener\(PROFILE_CHANGED, read\)/);
});

test("the sidebar has no About you, and #about still opens the page", async () => {
  const { SIDE_NAV } = await import("../src/sideNav.js");
  assert.ok(!SIDE_NAV.some((n) => n.key === "about" || /About you/.test(n.label)));
  const { canvasRequestFromHash } = await import("../src/canvasLinks.js");
  for (const h of ["#about", "#about=you", "#about=docs", "#about=memory", "#settings=about"]) assert.equal(canvasRequestFromHash(h).area, "about", h);
});

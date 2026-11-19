// A SETTING'S ADDRESS, ONE WAY ON BOTH SIDES: the server's settings_schema.href and the page's settingHref are held to the same cases
// (settingHref.cases.json, which tests/test_connected_count.py reads too) - an inline quote() opened "Mail / routing" at the wrong anchor
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { settingHref, hashFor } from "../src/canvasLinks.js";

const { cases } = JSON.parse(readFileSync(new URL("./settingHref.cases.json", import.meta.url), "utf8"));

test("the page builds a setting's address as the server does", () => {
  for (const c of cases) {
    assert.equal(settingHref(c.group, c.key), c.href, c.group);
    assert.equal(hashFor("settings", { section: "config", open: c.group, knob: c.key }), c.href, "the canvas writes the same address");
  }
});

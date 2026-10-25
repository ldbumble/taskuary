// A document a message LINKS to (linkdocs.py) is drawn beside its files: its kind, its name, and a chip that opens it where it
// lives - never through our attachment door, which would hang the owner's token off a third party's address.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const src = fs.readFileSync(new URL("../src/Attachments.jsx", import.meta.url), "utf8");

// hrefOf and titleOf as the chip calls them, with our attachment door stubbed so the token's place shows
const doors = new Function(`const attUrl = (a) => a.url + "?token=T"; ${src.slice(src.indexOf("const kb ="), src.indexOf("const KIND ="))}
  ${src.slice(src.indexOf("const SAVE_MAX"), src.indexOf("// a mail whose body points"))}; return { hrefOf, titleOf };`)();

test("a linked document opens at its own address, without the token", () => {
  assert.equal(doors.hrefOf({ link: true, external_url: "https://docs.google.com/spreadsheets/d/x", url: "/api/x" }, "https://mail.example/m"),
    "https://docs.google.com/spreadsheets/d/x");
  assert.equal(doors.hrefOf({ url: "/api/attachments/4" }, "https://mail.example/m"), "/api/attachments/4?token=T");
  assert.match(src, /rel=\{a\.link \|\| !a\.url \? "noopener noreferrer" : "noopener"\}/);
});

// TQ-1197: a file kept without its bytes (a cloud link Outlook attaches, one over the size limit) was a greyed chip that did nothing
test("a file kept without its bytes opens the original message, and says why when there is none", () => {
  assert.equal(doors.hrefOf({ name: "Cash.xlsx", size: 900 }, "https://mail.example/m"), "https://mail.example/m");
  assert.equal(doors.hrefOf({ name: "Cash.xlsx", size: 900 }), undefined);
  assert.match(doors.titleOf({ size: 900 }, "https://mail.example/m"), /no copy came with the mail.*opens in the original message/);
  assert.match(doors.titleOf({ size: 20 * 1024 * 1024 }), /over 12\.0 MB, so not saved here.*from the mail in your mailbox/);
  assert.match(src, /a\.url \? kb\(a\.size\) : original \? "in the original" : "not saved"/, "the chip says it, not only its hover");
});

test("its chip says its kind and, on hover, whether it was read and why not", () => {
  assert.match(src, /\["sheet", "SHEET"\]/);
  assert.match(src, /not read: \$\{a\.note\}/);
});

test("the task's counter counts linked documents beside its files", async () => {
  const { filesLine } = await import("../src/timeWords.js");
  assert.equal(filesLine(6, 2), "6 attachments · 2 links");
  assert.equal(filesLine(1, 0), "1 attachment");
  assert.equal(filesLine(0, 1), "1 link");
  assert.equal(filesLine(0, 0), "");
  const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /label=\{filesLine\(detail\.attachments\?\.length \|\| 0, detail\.links\?\.length \|\| 0\)\}/);
});

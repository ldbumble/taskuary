// EVERY FILE BELONGS TO ITS MESSAGE (the owner, 2026-10-20): a voice note was drawn loose under the Came from card, outside the
// thread, named by the bridge's hash. Each message's attachments ride under its own row; a voice note is called one.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
const att = fs.readFileSync(new URL("../src/Attachments.jsx", import.meta.url), "utf8");

const rowsFn = page.slice(page.indexOf("function ConversationRows("), page.indexOf("// the repo is a filter like the others"));


test("a voice note named by the bridge's hash is called a voice note; a named file keeps its name", () => {
  const src = att.slice(att.indexOf("const HASHED"), att.indexOf("const kb ="));
  const { clipName } = new Function(`${src.replace(/export /g, "")}; return { clipName };`)();
  assert.equal(clipName({ name: "3EB0C431D5E6F7A8B9C0.ogg" }), "Voice note");
  assert.equal(clipName({ name: "board-call.m4a" }), "board-call.m4a");
  assert.equal(clipName({}), "Voice note");
  assert.match(att, /noWrap title=\{a\.name\}>\{clipName\(a\)\}<\/Typography>/, "the stored name stays on hover");
});

// IMAGES INLINE IN AN OPEN MESSAGE (the owner, 2026-10-29): a WhatsApp photo is saved inline and small, the shape of a mail signature's
// logo, and stood as a "JPG ...jpg 14 KB" chip in the open letter. The logo rule is mail's alone; only our own bytes are drawn.
test("an open message draws a chat's small photo; a mail's small inline logo stays a chip; nothing remote is drawn", () => {
  const src = att.slice(att.indexOf("const LOGO ="), att.indexOf("// A voice note is the message"));
  const { drawable } = new Function(`${src.replace(/export /g, "")}; return { drawable };`)();
  const photo = { is_image: true, inline: true, size: 14 * 1024, content_type: "image/jpeg", url: "/api/attachments/4", name: "3EB07A1B2C3D4E5F.jpg" };
  assert.equal(drawable({ ...photo, mail: false }), true, "a chat's photo is the message");
  assert.equal(drawable({ ...photo, mail: true }), false, "a mail's small inline picture is a signature");
  assert.equal(drawable(photo), false, "a row that does not say (the static demo) keeps the mail rule");
  assert.equal(drawable({ ...photo, mail: true, size: 200 * 1024 }), true, "a mail's screenshot is drawn");
  assert.equal(drawable({ ...photo, mail: false, url: "https://img.example/p.jpg" }), false, "never a remote address");
  assert.equal(drawable({ ...photo, mail: false, url: "data:image/png;base64,AA" }), true, "the demo's own bytes");
  assert.equal(drawable({ ...photo, mail: false, is_image: false }), false, "an image content type only");
  assert.equal(drawable({ ...photo, mail: false, url: null }), false, "nothing saved, nothing drawn");
  // the open letter draws them; a closed row stays the row alone
  assert.match(rowsFn, /open === r\.m\.MessageId && \([\s\S]*<Attachments messageId=\{r\.m\.MessageId\} canFetch=\{r\.m\.Channel === "email"/);
});

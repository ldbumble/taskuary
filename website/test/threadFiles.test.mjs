// EVERY FILE BELONGS TO ITS MESSAGE (the owner, 2026-10-20): a voice note was drawn loose under the Came from card, outside the
// thread, named by the bridge's hash. Each message's attachments ride under its own row; a voice note is called one.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { filesByMessage, rowText } from "../src/taskSources.js";

const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
const att = fs.readFileSync(new URL("../src/Attachments.jsx", import.meta.url), "utf8");
// ...Came from's facts and conversations, drawn once and placed by the layout (fromFacts, fromConvs - the three sections, 2026-10-27)
const cameFrom = page.slice(page.indexOf("const fromFacts = () =>"), page.indexOf("const fromSorted = () =>"));
const rowsFn = page.slice(page.indexOf("function ConversationRows("), page.indexOf("// the repo is a filter like the others"));

test("the detail's attachments are grouped by the message they came in", () => {
  const by = filesByMessage([{ MessageId: 7, Name: "3EB0C431D5E6F7A8.ogg" }, { MessageId: 9, Name: "a.png" }, { MessageId: 7, Name: "b.pdf" }, { Name: "orphan" }]);
  assert.deepEqual([...by.keys()], [7, 9]);
  assert.equal(by.get(7).length, 2);
  assert.equal(filesByMessage(undefined).size, 0);
});

test("a condensed row reads the transcript, says Voice note for a bare one, and never the attachment placeholder", () => {
  const ogg = [{ MessageId: 1, Name: "3EB0C431D5E6F7A8.ogg", ContentType: "audio/ogg" }];
  assert.equal(rowText({ excerpt: "Running late, start without me. (🎤 voice note (9s) from WhatsApp, transcribed by Groq (Whisper))" }, ogg),
    "Running late, start without me.");
  assert.equal(rowText({ excerpt: "(no text - see the attachment)" }, ogg), "Voice note");
  assert.equal(rowText({ excerpt: "(no text - see the attachment)" }, [{ Name: "plan.pdf", ContentType: "application/pdf" }]), "1 attachment");
  assert.equal(rowText({ excerpt: "" }), "(no text)");
  assert.equal(rowText({ excerpt: "see the deck", Subject: "Deck" }, []), "see the deck");
});

test("nothing is drawn loose under the card: each row draws its own message's files", () => {
  assert.doesNotMatch(cameFrom, /<Attachments messageId=\{inbound\[0\]/, "the opener's files are not drawn outside the thread");
  assert.match(cameFrom, /files=\{sourceFiles\} fetchFor=\{fetchFor\}/);
  assert.match(page, /const sourceFiles = filesByMessage\(detail\?\.attachments\);/);
  assert.match(rowsFn, /open !== r\.m\.MessageId && fetchFor === r\.m\.MessageId && \(/);   // a closed row draws no files (2026-10-28)
  assert.match(rowsFn, /<Attachments messageId=\{r\.m\.MessageId\} canFetch=\{fetchFor === r\.m\.MessageId\} dense original=\{r\.m\.SourceLink\} \/>/);
});

// TQ-1197: "1 attachment" under Came from looked pressable and did nothing, the file itself under a 420px letter below the fold
test("the files pill opens the message they came with and brings its letter's foot into view", () => {
  const pill = cameFrom.slice(cameFrom.indexOf("data-tq-files-pill"), cameFrom.indexOf("sx={{ height: 19"));
  assert.match(pill, /onClick=/);
  assert.match(pill, /detail\.attachments\?\.\[0\]\?\.MessageId/);
  assert.match(pill, /setOpenMsg\(mid\); setSeekLetter\(mid\);/);
  assert.match(pill, /setShowAll\(true\)/, "a message folded under Show older is shown first");
  assert.match(rowsFn, /data-tq-letter=\{r\.m\.MessageId\}/);
  assert.match(page, /querySelector\(`\[data-tq-letter="\$\{seekLetter\}"\]`\)\?\.scrollIntoView\(\{ block: "end"/);
  assert.match(rowsFn, /mentionsPicture\(r\.m\.BodyText\)\} dense original=\{r\.m\.SourceLink\} \/>/, "the open letter's files reach the original too");
});

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

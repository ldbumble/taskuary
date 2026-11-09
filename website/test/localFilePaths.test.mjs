// A LOCAL PATH IN AN AGENT'S WORDS IS THE FILE, where the app may serve it (the owner, 2026-11-09: a coding turn listed three screenshots as
// bare paths into its CLI's temp folder, then "opened them in the image viewer" on a computer nobody watched - "this should be link"). A path
// into the task's own outputs folder is a link, and a picture is drawn; any other path stays text. A file the agent SHOWS (show `files`) rides
// in the call's answer and is drawn in the turn. Invented names and folders.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { codeLocalPaths, localFile } from "../src/taskOutputs.js";
import { filesOf, FILES_MARK, MARK } from "../src/viewSpec.js";
import { turnParts } from "../src/chatStream.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
const OUT = "C:\\Users\\alex\\.taskuary\\scratch\\outputs\\TQ-0042";

test("a local picture in the task's folder is a link and a picture; another file a link; a path anywhere else plain text", () => {
  const pic = localFile(`${OUT}\\darkA.png`, 42);
  assert.deepEqual(pic, { rel: "darkA.png", name: "darkA.png", url: "/api/task-outputs/42/darkA.png", image: true });
  assert.equal(localFile("/home/alex/.taskuary/scratch/outputs/TQ-42/shots/light.webp", 42).url, "/api/task-outputs/42/shots/light.webp");
  const sheet = localFile(`${OUT}\\Vendor costs.xlsx`, 42);
  assert.equal(sheet.image, false); assert.equal(sheet.url, "/api/task-outputs/42/Vendor%20costs.xlsx");
  // a CLI's own temp scratchpad, another task's folder, a key file, a relative name: never served, never a link
  for (const p of ["C:\\Users\\alex\\AppData\\Local\\Temp\\claude\\0a1b\\scratchpad\\darkA.png", `${OUT.replace("42", "43")}\\darkA.png`,
    "C:\\Users\\alex\\.ssh\\id_ed25519", "scratch/outputs/TQ-0042/darkA.png", `${OUT}\\..\\TQ-0043\\a.png`]) assert.equal(localFile(p, 42), null, p);
});

test("a path named bare in the words becomes a code span for the chat to draw as the file; one outside the folder is left as written", () => {
  const tmp = "C:\\Users\\alex\\AppData\\Local\\Temp\\claude\\0a1b\\scratchpad\\darkB.png";
  const got = codeLocalPaths(`Both side by side:\n- ${OUT}\\darkA.png (now)\n- ${tmp} (lighter)\n- \`${OUT}\\light.png\`.`, 42);
  assert.equal(got, `Both side by side:\n- \`${OUT}\\darkA.png\` (now)\n- ${tmp} (lighter)\n- \`${OUT}\\light.png\`.`);
  assert.equal(codeLocalPaths(`Saved: ${OUT}\\report.pdf.`, 42), `Saved: \`${OUT}\\report.pdf\`.`);
});

test("the chat draws a local path as the file: a picture as <img> with a link that opens it whole, anything else a link", () => {
  const md = read("md.jsx");
  assert.match(md, /const Code = [\s\S]*?localFile\(kids\[0\], at\.tid\)/);
  assert.match(md, /f\.image && <span data-tq-local-picture[\s\S]*?<img src=\{src\}/);
  assert.match(md, /f\.image \? <a href=\{src\} data-tq-file-link=""[\s\S]*?: <A href=\{f\.url\}>/);
  assert.match(md, /code: Code/);
  assert.match(read("GeneralWorkspace.jsx"), /<LocalFiles\.Provider value=\{dock \? null : \{ tid: task\.TaskId \}\}>/);
});

const call = (id, name, args = {}) => ({ type: "tool_call", name, detail: { tool_call_id: id, args } });
const answer = (id, result, is_error = false) => ({ type: "tool_result", name: id, detail: { tool_call_id: id, result, is_error } });
const ROWS = [{ id: 7, name: "darkA.png", path: "shown:7", kind: "shown", content_type: "image/png", size: 9, url: "/api/task-artifacts/7" }];

test("a file the agent showed is drawn in the turn that showed it, from the call's own answer", () => {
  const said = `Shown in the owner's chat under your answer: darkA.png. ${FILES_MARK}${JSON.stringify(ROWS)}`;
  const parts = turnParts([call("c1", "mcp__taskuary__show", { files: ["C:\\tmp\\darkA.png"] }), answer("c1", said)]);
  assert.deepEqual(parts.map((p) => p.type), ["files"]);
  assert.deepEqual(parts[0].files[0], ROWS[0]);
  // ...with a view in the same call: both, the view's spec read whole after its own mark
  const view = { root: "a", elements: { a: { type: "text", props: { text: "Two palettes." } } } };
  const both = turnParts([call("c2", "show"), answer("c2", `${said} Shown in the owner's chat. ${MARK}${JSON.stringify(view)}`)]);
  assert.deepEqual(both.map((p) => p.type), ["files", "view"]);
  // ...never a row pointing anywhere but a task artifact, and never from a refused call
  const forged = [{ ...ROWS[0], url: "/api/task-outputs/43/secret.png" }, { ...ROWS[0], url: "https://vendor.example/x.png" }];
  assert.equal(filesOf(call("c3", "show"), answer("c3", `${FILES_MARK}${JSON.stringify(forged)}`)), null);
  assert.equal(filesOf(call("c4", "show"), answer("c4", said, true)), null);
  assert.equal(filesOf(call("c5", "Bash", {}), answer("c5", said)), null);
});

test("on a coding task the files part is drawn by TurnFiles; the general chat places its copy under the answer once", () => {
  const gw = read("GeneralWorkspace.jsx");
  assert.match(gw, /p\.type === "files" \? \(fromTrace \? <TurnFiles key=\{p\.id\} files=\{p\.files\} \/> : null\)/);
  assert.match(gw, /<TraceFilesCtx\.Provider value=\{coding\}>/);
});

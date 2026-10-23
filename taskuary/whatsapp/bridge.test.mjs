import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// The real bridge.mjs, run as its own process, with Baileys swapped for a fake by a resolve hook - no WhatsApp socket is ever
// opened and nothing in the bridge's folder changes (an extra .mjs there would change the code fingerprint Taskuary checks).
const BRIDGE = path.join(path.dirname(fileURLToPath(import.meta.url)), "bridge.mjs");

// What Baileys did on the owner's machine when the laptop woke (2026-10-22): the login completes, its un-awaited CB:success handler
// sends a query, and the socket closes under it - connection.update says "close" and the query rejects with the bare code 1006.
const FAKE = `
import { EventEmitter } from "node:events";
let n = 0;
export const DisconnectReason = { loggedOut: 401, connectionClosed: 428 };
export const useMultiFileAuthState = async () => ({ state: { creds: {}, keys: { set: async () => {} } }, saveCreds: async () => {} });
export const downloadMediaMessage = async () => Buffer.alloc(0);
export const decryptPollVote = () => { throw new Error("no polls here"); };
export default function makeWASocket() {
  const i = ++n, ev = new EventEmitter();
  const sock = { ev, user: { id: "1555000000" + i + ":1@s.whatsapp.net", name: "Fake " + i },
    groupFetchAllParticipating: async () => ({}), resyncAppState: async () => {} };
  const stray = () => new Promise((_, no) => setTimeout(() => no(1006), 5));     // nobody awaits it, as in Baileys
  setTimeout(() => {
    ev.emit("connection.update", { connection: "open" });
    if (i > 1) return;
    setTimeout(() => {
      stray();
      ev.emit("connection.update", { connection: "close",
        lastDisconnect: { error: Object.assign(new Error("Connection Terminated"), { output: { statusCode: 428 } }) } });
      stray();
    }, 50);
  }, 20);
  return sock;
}`;

const freePort = () => new Promise((ok) => { const s = net.createServer().listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => ok(p)); }); });
const status = (port, token) => new Promise((ok) => {
  http.get({ host: "127.0.0.1", port, path: "/status", headers: { "x-bridge-token": token } }, (r) => {
    let b = ""; r.on("data", (c) => (b += c)); r.on("end", () => { try { ok(JSON.parse(b)); } catch { ok(null); } });
  }).on("error", () => ok(null));
});

test("a connection that drops under a pending query reconnects, and the bridge stays up", { timeout: 30_000 }, async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wa-bridge-test-"));
  const fake = path.join(dir, "fake-baileys.mjs");
  fs.writeFileSync(fake, FAKE);
  const hooks = `export async function resolve(s, c, next) {
    return s === "@whiskeysockets/baileys" ? { url: ${JSON.stringify(pathToFileURL(fake).href)}, shortCircuit: true } : next(s, c); }`;
  const reg = `import { register } from "node:module"; register(${JSON.stringify("data:text/javascript," + encodeURIComponent(hooks))});`;
  const port = await freePort(), token = "test-token";
  const child = spawn(process.execPath, ["--import", "data:text/javascript," + encodeURIComponent(reg), BRIDGE],
    { cwd: dir, env: { ...process.env, WA_BRIDGE_PORT: String(port), WA_BRIDGE_TOKEN: token }, stdio: ["ignore", "pipe", "pipe"] });
  let out = "", exited = null;
  child.stdout.on("data", (c) => (out += c)); child.stderr.on("data", (c) => (out += c));
  child.on("exit", (code) => (exited = code ?? "signal"));
  try {
    let st = null;
    for (let i = 0; i < 100 && exited === null; i++) {          // the first reconnect waits 5s (policy.mjs)
      await new Promise((r) => setTimeout(r, 200));
      st = await status(port, token);
      if (st?.connected && st.me === "Fake 2") break;
    }
    assert.equal(exited, null, `the bridge exited on a dropped connection:\n${out}`);
    assert.equal(st?.me, "Fake 2", `the bridge never reconnected:\n${out}`);
    assert.equal(st.connected, true);
    assert.match(out, /reconnecting in 5s \(attempt 1\)/);
    assert.match(out, /1006/, "the stray rejection is logged, not swallowed");
  } finally {
    if (exited === null) { const gone = new Promise((r) => child.once("exit", r)); child.kill(); await gone; }
    fs.rmSync(dir, { recursive: true, force: true, maxRetries: 5 });     // Windows holds a dead process's cwd a moment
  }
});

// A Baileys that connects and stays up, writing every sendMessage it is handed to sent.jsonl in its folder - a document as its bytes.
const RECORDS = `
import { EventEmitter } from "node:events";
import fs from "node:fs";
export const DisconnectReason = { loggedOut: 401 };
export const useMultiFileAuthState = async () => ({ state: { creds: {}, keys: { set: async () => {} } }, saveCreds: async () => {} });
export const downloadMediaMessage = async () => Buffer.alloc(0);
export const decryptPollVote = () => { throw new Error("no polls here"); };
let n = 0;
export default function makeWASocket() {
  const ev = new EventEmitter();
  const sock = { ev, user: { id: "15550100100:1@s.whatsapp.net", name: "Alex Doyle" }, groupFetchAllParticipating: async () => ({}),
    resyncAppState: async () => {},
    sendMessage: async (jid, content) => {
      fs.appendFileSync("sent.jsonl", JSON.stringify({ jid, ...content, ...(content.document ? { document: content.document.toString("base64") } : {}) }) + "\\n");
      return { key: { id: "OUT" + ++n, remoteJid: jid, fromMe: true } };
    } };
  setTimeout(() => ev.emit("connection.update", { connection: "open" }), 20);
  return sock;
}`;

const post = (port, p, body, headers = {}) => new Promise((ok) => {
  const data = typeof body === "string" ? body : JSON.stringify(body);
  const r = http.request({ host: "127.0.0.1", port, path: p, method: "POST",
    headers: { "content-type": "application/json", "content-length": Buffer.byteLength(data), ...headers } }, (res) => {
    let b = ""; res.on("data", (c) => (b += c));
    res.on("end", () => { try { ok({ code: res.statusCode, body: JSON.parse(b) }); } catch { ok({ code: res.statusCode, body: b }); } });
  });
  r.on("error", (e) => ok({ code: e.code })); r.end(data);
});

test("/send-document sends the very bytes as a WhatsApp document - with the token, never from a page, never past the cap", { timeout: 30_000 }, async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wa-bridge-test-"));
  const fake = path.join(dir, "fake-baileys.mjs");
  fs.writeFileSync(fake, RECORDS);
  const hooks = `export async function resolve(s, c, next) {
    return s === "@whiskeysockets/baileys" ? { url: ${JSON.stringify(pathToFileURL(fake).href)}, shortCircuit: true } : next(s, c); }`;
  const reg = `import { register } from "node:module"; register(${JSON.stringify("data:text/javascript," + encodeURIComponent(hooks))});`;
  const port = await freePort(), token = "test-token", auth = { "x-bridge-token": token };
  const child = spawn(process.execPath, ["--import", "data:text/javascript," + encodeURIComponent(reg), BRIDGE],
    { cwd: dir, env: { ...process.env, WA_BRIDGE_PORT: String(port), WA_BRIDGE_TOKEN: token }, stdio: ["ignore", "pipe", "pipe"] });
  let out = "", exited = null;
  child.stdout.on("data", (c) => (out += c)); child.stderr.on("data", (c) => (out += c));
  child.on("exit", (code) => (exited = code ?? "signal"));
  try {
    for (let i = 0; i < 100 && exited === null && !(await status(port, token))?.connected; i++) await new Promise((r) => setTimeout(r, 100));
    const bytes = Buffer.from("Account,Debit,Credit\n4000,120.00,\n");
    const doc = { jid: "15550100100@s.whatsapp.net", data: bytes.toString("base64"), mimetype: "text/csv", fileName: "visitor-parking.csv",
      caption: "TQ-0017 · visitor-parking.csv" };
    assert.equal((await post(port, "/send-document", doc)).code, 401, "no token, no send");
    assert.equal((await post(port, "/send-document", doc, { ...auth, origin: "https://page.example" })).code, 403, "never from a web page");
    assert.equal((await post(port, "/send-document", { ...doc, data: "" }, auth)).code, 400);
    const big = await post(port, "/send-document", "{}", { ...auth, "content-length": String(200 * 2 ** 20) });
    assert.ok([413, "ECONNRESET", "EPIPE"].includes(big.code), `an oversized body is refused before it is read: ${JSON.stringify(big)}`);
    const sentOk = await post(port, "/send-document", doc, auth);
    assert.equal(sentOk.code, 200, JSON.stringify(sentOk.body) + out);
    assert.equal(sentOk.body.bytes, bytes.length);
    const sent = fs.readFileSync(path.join(dir, "sent.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l));
    assert.equal(sent.length, 1, "the refused ones sent nothing");
    assert.deepEqual([sent[0].jid, sent[0].fileName, sent[0].mimetype, sent[0].caption], [doc.jid, "visitor-parking.csv", "text/csv", doc.caption]);
    assert.equal(Buffer.from(sent[0].document, "base64").toString(), bytes.toString(), "the very bytes");
  } finally {
    if (exited === null) { const gone = new Promise((r) => child.once("exit", r)); child.kill(); await gone; }
    fs.rmSync(dir, { recursive: true, force: true, maxRetries: 5 });
  }
});

// THE CARD TELLS THE TRUTH (2026-10-23): /status said "connected" from an open socket while chats were turned away, a person written
// to by LID was never heard, and the contact-name sync failed every ten minutes. A Baileys that does what the owner's did: a 1:1 by
// LID from a person picked by NUMBER, a group and a stranger turned away, the owner's own LID heard, the address book's key missing.
const TRUTH = `
import { EventEmitter } from "node:events";
export const DisconnectReason = { loggedOut: 401 };
const me = { id: "15550100100:1@s.whatsapp.net", lid: "7000:1@lid", name: "Alex Doyle" };
export const useMultiFileAuthState = async () => ({ state: { creds: { me }, keys: { set: async () => {} } }, saveCreds: async () => {} });
export const downloadMediaMessage = async () => Buffer.alloc(0);
export const decryptPollVote = () => { throw new Error("no polls here"); };
const quiet = () => {};
export const DEFAULT_CONNECTION_CONFIG = { logger: { child: () => ({ info: quiet, warn: quiet, error: quiet, debug: quiet, trace: quiet }) } };
export default function makeWASocket(config) {
  const ev = new EventEmitter();
  const sock = { ev, user: me, groupFetchAllParticipating: async () => ({}), resyncAppState: async () => {},
    onWhatsApp: async (...jids) => jids.map((jid) => ({ jid, exists: true, lid: jid.startsWith("15550100200") ? "8000@lid" : undefined })) };
  setTimeout(() => {
    ev.emit("connection.update", { connection: "open" });
    config.logger.info({ name: "critical_unblock_low", error: "Error: failed to find key" }, "failed to sync state from version");
    for (const jid of ["120363000000000009@g.us", "9000@lid", "7000:1@lid"]) config.shouldIgnoreJid(jid);
    setTimeout(() => ev.emit("messages.upsert", { type: "notify", messages: [
      { key: { remoteJid: "8000@lid", fromMe: false, id: "IN1" }, message: { conversation: "the export is late" }, pushName: "Ray", messageTimestamp: 1750000000 },
      { key: { remoteJid: "9100@lid", fromMe: true, id: "IN2" }, message: { conversation: "to someone never picked" }, messageTimestamp: 1750000001 }] }), 150);
  }, 20);
  return sock;
}`;

const get = (port, p, token) => new Promise((ok) => {
  http.get({ host: "127.0.0.1", port, path: p, headers: { "x-bridge-token": token } }, (r) => {
    let b = ""; r.on("data", (c) => (b += c)); r.on("end", () => { try { ok(JSON.parse(b)); } catch { ok(null); } });
  }).on("error", () => ok(null));
});

test("/status says how many chats are let in and turned away, when the last message came and what failed; a LID is its number", { timeout: 30_000 }, async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wa-bridge-test-"));
  const fake = path.join(dir, "fake-baileys.mjs");
  fs.writeFileSync(fake, TRUTH);
  const hooks = `export async function resolve(s, c, next) {
    return s === "@whiskeysockets/baileys" ? { url: ${JSON.stringify(pathToFileURL(fake).href)}, shortCircuit: true } : next(s, c); }`;
  const reg = `import { register } from "node:module"; register(${JSON.stringify("data:text/javascript," + encodeURIComponent(hooks))});`;
  const port = await freePort(), token = "test-token";
  const child = spawn(process.execPath, ["--import", "data:text/javascript," + encodeURIComponent(reg), BRIDGE],
    { cwd: dir, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, WA_BRIDGE_PORT: String(port), WA_BRIDGE_TOKEN: token,
      WA_BRIDGE_FILTER: JSON.stringify({ allDirect: false, jids: ["15550100200@s.whatsapp.net"] }) } });
  let out = "", exited = null;
  child.stdout.on("data", (c) => (out += c)); child.stderr.on("data", (c) => (out += c));
  child.on("exit", (code) => (exited = code ?? "signal"));
  try {
    let st = null;
    for (let i = 0; i < 100 && exited === null && !((st = await status(port, token))?.lastInboundAt); i++) await new Promise((r) => setTimeout(r, 100));
    assert.equal(st?.connected, true, out);
    assert.equal(st.admitted, 1);
    assert.equal(st.turnedAway, 3, "the group, a stranger's LID, and the unpicked chat the owner wrote to - never the owner's own LID");
    assert.ok(st.lastInboundAt > 0, "the message from the picked person arrived");
    assert.deepEqual([st.contactSync.failures, st.contactSync.why, st.lastFailure.kind], [1, "missing key", "contacts"]);
    assert.equal(st.loggedOut, false);
    assert.ok(st.lidMapped >= 2, "the owner's pair and the looked-up number");
    const { messages } = await get(port, "/messages?after=0", token);
    assert.deepEqual(messages.map((m) => [m.jid, m.text]), [["15550100200@s.whatsapp.net", "the export is late"]],
      "the LID arrives as the number it was picked by; what the owner wrote to an unpicked chat stays out");
    const { chats } = await get(port, "/chats", token);
    assert.ok(chats.some((c) => c.jid === "9000@lid" && !c.group), "a turned-away LID can be picked");
  } finally {
    if (exited === null) { const gone = new Promise((r) => child.once("exit", r)); child.kill(); await gone; }
    fs.rmSync(dir, { recursive: true, force: true, maxRetries: 5 });
  }
});

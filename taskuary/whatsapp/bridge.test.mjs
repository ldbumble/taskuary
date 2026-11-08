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
import fs from "node:fs";
export const DisconnectReason = { loggedOut: 401 };
const me = { id: "15550100100:1@s.whatsapp.net", lid: "7000:1@lid", name: "Alex Doyle" };
export const useMultiFileAuthState = async () => ({ state: { creds: { me }, keys: { set: async () => {} } }, saveCreds: async () => {} });
export const downloadMediaMessage = async () => Buffer.alloc(0);
export const decryptPollVote = () => { throw new Error("no polls here"); };
const quiet = () => {};
export const DEFAULT_CONNECTION_CONFIG = { logger: { child: () => ({ info: quiet, warn: quiet, error: quiet, debug: quiet, trace: quiet }) } };
export default function makeWASocket(config) {
  fs.writeFileSync("socket-config.json", JSON.stringify({ fireInitQueries: config.fireInitQueries }));
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
    // ...and what waited out a dropped connection: WhatsApp hands it over on the reconnect, offline, and Baileys says "append"
    setTimeout(() => ev.emit("messages.upsert", { type: "append", messages: [
      { key: { remoteJid: "8000@lid", fromMe: false, id: "IN3" }, message: { conversation: "sent while the link was down" }, pushName: "Ray", messageTimestamp: 1750000002 }] }), 200);
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
    await new Promise((r) => setTimeout(r, 300));
    assert.equal(st?.connected, true, out);
    assert.equal(st.admitted, 1);
    assert.equal(st.turnedAway, 3, "the group, a stranger's LID, and the unpicked chat the owner wrote to - never the owner's own LID");
    assert.ok(st.lastInboundAt > 0, "the message from the picked person arrived");
    assert.deepEqual([st.contactSync.failures, st.contactSync.why, st.lastFailure.kind], [1, "missing key", "contacts"]);
    assert.equal(st.loggedOut, false);
    // the props/blocklist/privacy queries timed out (408) on every connect, and nothing reads them (TQ-1251)
    assert.equal(JSON.parse(fs.readFileSync(path.join(dir, "socket-config.json"), "utf8")).fireInitQueries, false);
    assert.ok(st.lidMapped >= 2, "the owner's pair and the looked-up number");
    const { messages, boot } = await get(port, "/messages?after=0", token);
    assert.match(boot, /^[0-9a-f-]{36}$/, "a start-up id: a restarted bridge counts from 0 again, and Taskuary reads all it holds (TQ-1251)");
    assert.deepEqual(messages.map((m) => [m.jid, m.text]), [["15550100200@s.whatsapp.net", "the export is late"],
      ["15550100200@s.whatsapp.net", "sent while the link was down"]],
      "the LID arrives as the number it was picked by; what the owner wrote to an unpicked chat stays out; what waited out a drop comes in");
    const { chats } = await get(port, "/chats", token);
    assert.ok(chats.some((c) => c.jid === "9000@lid" && !c.group), "a turned-away LID can be picked");
  } finally {
    if (exited === null) { const gone = new Promise((r) => child.once("exit", r)); child.kill(); await gone; }
    fs.rmSync(dir, { recursive: true, force: true, maxRetries: 5 });
  }
});

// A bridge that must never reach WhatsApp: the fake marks connected.txt the moment anything calls makeWASocket.
const MARKS = `
import { EventEmitter } from "node:events";
import fs from "node:fs";
export const DisconnectReason = { loggedOut: 401 };
export const useMultiFileAuthState = async () => ({ state: { creds: {}, keys: { set: async () => {} } }, saveCreds: async () => {} });
export const downloadMediaMessage = async () => Buffer.alloc(0);
export const decryptPollVote = () => { throw new Error("no polls here"); };
export default function makeWASocket() {
  fs.writeFileSync("connected.txt", "yes");
  const ev = new EventEmitter();
  setTimeout(() => ev.emit("connection.update", { connection: "open" }), 20);
  return { ev, user: { id: "15550100100:1@s.whatsapp.net", name: "Alex Doyle" }, groupFetchAllParticipating: async () => ({}), resyncAppState: async () => {} };
}`;

// Run bridge.mjs on `port` in `dir` with MARKS for Baileys; resolves {code, out} when it exits, or after `ms` (then killed, code null).
const runBridge = (dir, port, ms = 8000) => new Promise((ok) => {
  const fake = path.join(dir, "fake-baileys.mjs");
  fs.writeFileSync(fake, MARKS);
  const hooks = `export async function resolve(s, c, next) {
    return s === "@whiskeysockets/baileys" ? { url: ${JSON.stringify(pathToFileURL(fake).href)}, shortCircuit: true } : next(s, c); }`;
  const reg = `import { register } from "node:module"; register(${JSON.stringify("data:text/javascript," + encodeURIComponent(hooks))});`;
  const child = spawn(process.execPath, ["--import", "data:text/javascript," + encodeURIComponent(reg), BRIDGE],
    { cwd: dir, env: { ...process.env, WA_BRIDGE_PORT: String(port), WA_BRIDGE_TOKEN: "t" }, stdio: ["ignore", "pipe", "pipe"] });
  let out = "";
  child.stdout.on("data", (c) => (out += c)); child.stderr.on("data", (c) => (out += c));
  const t = setTimeout(() => { child.kill(); }, ms);
  child.on("exit", (code) => { clearTimeout(t); ok({ code, out }); });
});
const until = async (f, ms = 8000) => { for (let i = 0; i < ms / 100 && !f(); i++) await new Promise((r) => setTimeout(r, 100)); return f(); };

// Like Baileys, register the pre-decryption handler inside makeWASocket, before the bridge can
// register its metadata observer. No onWhatsApp lookup or roster happens to know this pair yet.
const INBOUND = `
import { EventEmitter } from "node:events";
export const DisconnectReason = { loggedOut: 401 };
export const useMultiFileAuthState = async () => ({ state: { creds: {}, keys: { set: async () => {} } }, saveCreds: async () => {} });
export const downloadMediaMessage = async () => Buffer.from("synthetic media");
export const decryptPollVote = () => { throw new Error("no polls here"); };
export const normalizeMessageContent = (m) => {
  for (let i = 0; m && i < 5; i++) {
    const inner = m.ephemeralMessage || m.documentWithCaptionMessage;
    if (!inner) break;
    m = inner.message;
  }
  return m;
};
export default function makeWASocket(config) {
  const ev = new EventEmitter(), ws = new EventEmitter();
  ws.on("CB:message", (node) => {
    if (config.shouldIgnoreJid(node.attrs.from)) return;
    ev.emit("messages.upsert", { type: "notify", messages: [{ key: { remoteJid: node.attrs.from, id: node.attrs.id },
      message: { conversation: "first message from the picked number" } }] });
  });
  const sock = { ev, ws, user: { id: "15550100100:1@s.whatsapp.net" },
    groupFetchAllParticipating: async () => ({}), resyncAppState: async () => {} };
  setTimeout(() => {
    ev.emit("connection.update", { connection: "open" });
    ws.emit("CB:message", { attrs: { from: "8000@lid", sender_pn: "15550100200@s.whatsapp.net", id: "FIRST" } });
    ws.emit("CB:message", { attrs: { from: "9000@lid", sender_pn: "15550100999@s.whatsapp.net", id: "STRANGER" } });
    const wrap = (message) => ({ ephemeralMessage: { message } });
    const make = (id, message, jid = "42@g.us") => ({ key: { remoteJid: jid, id }, message, messageTimestamp: 1750000000 });
    ev.emit("messages.upsert", { type: "append", messages: [
      make("TEXT", wrap({ extendedTextMessage: { text: "the group export is ready", contextInfo: { quotedMessage: wrap({ conversation: "which export?" }) } } })),
      make("VOICE", wrap({ audioMessage: { mimetype: "audio/ogg", ptt: true, seconds: 3 } })),
      make("PHOTO", wrap({ imageMessage: { caption: "the chart", mimetype: "image/png" } })),
      make("DOC", wrap({ documentWithCaptionMessage: { message: { documentMessage: { fileName: "export.csv", caption: "the figures", mimetype: "text/csv" } } } })),
      make("CLOSED", wrap({ conversation: "not authorized" }), "99@g.us")
    ] });
  }, 30);
  return sock;
}`;

const withInboundBridge = async (check) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wa-inbound-test-"));
  const fake = path.join(dir, "fake-baileys.mjs");
  fs.writeFileSync(fake, INBOUND);
  const hooks = `export async function resolve(s, c, next) {
    return s === "@whiskeysockets/baileys" ? { url: ${JSON.stringify(pathToFileURL(fake).href)}, shortCircuit: true } : next(s, c); }`;
  const reg = `import { register } from "node:module"; register(${JSON.stringify("data:text/javascript," + encodeURIComponent(hooks))});`;
  const port = await freePort(), token = "test-token";
  const child = spawn(process.execPath, ["--import", "data:text/javascript," + encodeURIComponent(reg), BRIDGE],
    { cwd: dir, env: { ...process.env, WA_BRIDGE_PORT: String(port), WA_BRIDGE_TOKEN: token,
      WA_BRIDGE_FILTER: JSON.stringify({ jids: ["15550100200@s.whatsapp.net", "42@g.us"] }) }, stdio: ["ignore", "pipe", "pipe"] });
  let out = "";
  child.stdout.on("data", (c) => (out += c)); child.stderr.on("data", (c) => (out += c));
  try {
    for (let i = 0; i < 100 && !(await status(port, token))?.connected; i++) await new Promise((r) => setTimeout(r, 50));
    assert.equal((await status(port, token))?.connected, true, out);
    for (let i = 0; i < 100 && (await get(port, "/messages", token))?.messages?.length < 4; i++) await new Promise((r) => setTimeout(r, 50));
    await check((await get(port, "/messages", token)).messages, dir);
  } finally {
    if (child.exitCode === null) { const gone = new Promise((r) => child.once("exit", r)); child.kill(); await gone; }
    fs.rmSync(dir, { recursive: true, force: true, maxRetries: 5 });
  }
};

test("the first LID stanza learns its phone number before Baileys decides to discard it", { timeout: 15_000 }, async () => {
  await withInboundBridge(async (messages) => {
    assert.equal(messages.find((m) => m.id === "FIRST")?.jid, "15550100200@s.whatsapp.net");
    assert.ok(!messages.some((m) => m.id === "STRANGER" || m.id === "CLOSED"), "unpicked chats stay closed");
  });
});

test("disappearing group messages retain text, quotes and media through nested envelopes", { timeout: 15_000 }, async () => {
  await withInboundBridge(async (messages, dir) => {
    const byId = Object.fromEntries(messages.map((m) => [m.id, m]));
    assert.equal(byId.TEXT.text, "the group export is ready");
    assert.equal(byId.TEXT.quoted, "which export?");
    assert.equal(byId.VOICE.voice, true); assert.equal(byId.VOICE.seconds, 3);
    assert.equal(byId.PHOTO.text, "the chart"); assert.equal(byId.DOC.text, "the figures");
    assert.equal(byId.DOC.docName, "export.csv");
    for (const [id, field] of [["VOICE", "audio"], ["PHOTO", "image"], ["DOC", "doc"]]) {
      assert.ok(byId[id][field], `${id} has its media`);
      assert.equal(path.dirname(byId[id][field]), path.join(dir, "wa-media"));
      assert.equal(fs.readFileSync(byId[id][field], "utf8"), "synthetic media");
    }
  });
});

test("a held port is said in one line and exits 98 before WhatsApp is touched", { timeout: 30_000 }, async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wa-bridge-test-"));
  const port = await freePort(), holder = net.createServer().listen(port, "127.0.0.1");
  await new Promise((r) => holder.once("listening", r));
  try {
    const { code, out } = await runBridge(dir, port);
    assert.equal(code, 98, out); assert.match(out, new RegExp(`EADDRINUSE: port ${port} is in use`));
    assert.ok(!fs.existsSync(path.join(dir, "connected.txt")), "a losing copy never connects with the shared pairing");
  } finally { holder.close(); fs.rmSync(dir, { recursive: true, force: true, maxRetries: 5 }); }
});

test("a pairing a live bridge holds is refused with 75; a lock whose bridge is gone is taken over", { timeout: 30_000 }, async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wa-bridge-test-"));
  try {
    fs.writeFileSync(path.join(dir, "wa-auth.lock"), String(process.pid));          // this test runner: alive, holding the pairing
    const held = await runBridge(dir, await freePort());
    assert.equal(held.code, 75, held.out); assert.match(held.out, new RegExp(`WA_AUTH_LOCKED: .* bridge pid ${process.pid}`));
    assert.ok(!fs.existsSync(path.join(dir, "connected.txt")), "two bridges never connect with one pairing");
    assert.equal(fs.readFileSync(path.join(dir, "wa-auth.lock"), "utf8"), String(process.pid), "the holder's lock is left alone");
    const gone = spawn(process.execPath, ["-e", ""]); await new Promise((r) => gone.once("exit", r));
    fs.writeFileSync(path.join(dir, "wa-auth.lock"), String(gone.pid));             // a bridge killed with no chance to clean up
    const run = runBridge(dir, await freePort());
    assert.ok(await until(() => fs.existsSync(path.join(dir, "connected.txt"))), "a stale lock does not keep the bridge off WhatsApp");
    assert.notEqual(fs.readFileSync(path.join(dir, "wa-auth.lock"), "utf8"), String(gone.pid));
    await run;
  } finally { fs.rmSync(dir, { recursive: true, force: true, maxRetries: 5 }); }
});

// "We lost the names" (2026-11-02): the group roster was asked for once per connect, and a bridge restarted by an update whose one
// ask timed out listed no group at all - every switched-on group a bare id until the next drop. The first ask fails here; the next names it.
const SLOW_GROUPS = `
import { EventEmitter } from "node:events";
export const DisconnectReason = { loggedOut: 401 };
export const useMultiFileAuthState = async () => ({ state: { creds: {}, keys: { set: async () => {} } }, saveCreds: async () => {} });
export const downloadMediaMessage = async () => Buffer.alloc(0);
export const decryptPollVote = () => { throw new Error("no polls here"); };
let asked = 0;
export default function makeWASocket() {
  const ev = new EventEmitter();
  setTimeout(() => ev.emit("connection.update", { connection: "open" }), 20);
  return { ev, user: { id: "15550100100:1@s.whatsapp.net", name: "Alex Doyle" }, resyncAppState: async () => {},
    groupFetchAllParticipating: async () => {
      if (++asked === 1) throw new Error("Timed Out");
      return { "120363000000000007@g.us": { id: "120363000000000007@g.us", subject: "Northwind ops", participants: [{ id: "15550100123@s.whatsapp.net" }] } };
    } };
}`;

test("a group roster ask that times out at connect is asked again, and the groups come back named", { timeout: 30_000 }, async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wa-bridge-test-"));
  const fake = path.join(dir, "fake-baileys.mjs");
  fs.writeFileSync(fake, SLOW_GROUPS);
  const hooks = `export async function resolve(s, c, next) {
    return s === "@whiskeysockets/baileys" ? { url: ${JSON.stringify(pathToFileURL(fake).href)}, shortCircuit: true } : next(s, c); }`;
  const reg = `import { register } from "node:module"; register(${JSON.stringify("data:text/javascript," + encodeURIComponent(hooks))});`;
  const port = await freePort(), token = "test-token";
  const child = spawn(process.execPath, ["--import", "data:text/javascript," + encodeURIComponent(reg), BRIDGE],
    { cwd: dir, env: { ...process.env, WA_BRIDGE_PORT: String(port), WA_BRIDGE_TOKEN: token, WA_GROUPS_RETRY_MS: "200" }, stdio: ["ignore", "pipe", "pipe"] });
  let out = "", exited = null;
  child.stdout.on("data", (c) => (out += c)); child.stderr.on("data", (c) => (out += c));
  child.on("exit", (code) => (exited = code ?? "signal"));
  try {
    let chats = [];
    for (let i = 0; i < 100 && exited === null && !chats.length; i++) {
      await new Promise((r) => setTimeout(r, 100));
      chats = (await get(port, "/chats", token))?.chats || [];
    }
    assert.deepEqual(chats.map((c) => [c.jid, c.name, c.group]), [["120363000000000007@g.us", "Northwind ops", true]], out);
    assert.match(out, /could not refresh WhatsApp group roster: Timed Out - asking again/);
  } finally {
    if (exited === null) { const gone = new Promise((r) => child.once("exit", r)); child.kill(); await gone; }
    fs.rmSync(dir, { recursive: true, force: true, maxRetries: 5 });
  }
});

// A REPLY QUOTES THE LINE IT ANSWERS (the owner, 2026-11-08): two lines came in on one chat, and each answer goes as a WhatsApp reply to its
// own - from the message the bridge kept, else (a restart) from the words Taskuary sends; a group's line it never saw goes unquoted.
const QUOTES = RECORDS.replace("sendMessage: async (jid, content) => {", "sendMessage: async (jid, content, opts) => {")
  .replace("JSON.stringify({ jid, ...content,", "JSON.stringify({ jid, quoted: opts?.quoted || null, ...content,")
  .replace(`setTimeout(() => ev.emit("connection.update", { connection: "open" }), 20);`, `setTimeout(() => {
    ev.emit("connection.update", { connection: "open" });
    ev.emit("messages.upsert", { type: "notify", messages: ["the export is late", "and the invoice too"].map((t, i) => (
      { key: { remoteJid: "15550100200@s.whatsapp.net", fromMe: false, id: "IN" + (i + 1) }, message: { conversation: t }, pushName: "Ray", messageTimestamp: 1750000000 + i })) });
  }, 20);`);

test("/send with a quote sends it as a reply to that message; an unknown one is quoted from its words, or not at all", { timeout: 30_000 }, async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wa-bridge-test-"));
  const fake = path.join(dir, "fake-baileys.mjs");
  fs.writeFileSync(fake, QUOTES);
  const hooks = `export async function resolve(s, c, next) {
    return s === "@whiskeysockets/baileys" ? { url: ${JSON.stringify(pathToFileURL(fake).href)}, shortCircuit: true } : next(s, c); }`;
  const reg = `import { register } from "node:module"; register(${JSON.stringify("data:text/javascript," + encodeURIComponent(hooks))});`;
  const port = await freePort(), token = "test-token", auth = { "x-bridge-token": token }, jid = "15550100200@s.whatsapp.net";
  const child = spawn(process.execPath, ["--import", "data:text/javascript," + encodeURIComponent(reg), BRIDGE],
    { cwd: dir, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, WA_BRIDGE_PORT: String(port), WA_BRIDGE_TOKEN: token,
      WA_BRIDGE_FILTER: JSON.stringify({ allDirect: false, jids: [jid] }) } });
  let out = "", exited = null;
  child.stdout.on("data", (c) => (out += c)); child.stderr.on("data", (c) => (out += c));
  child.on("exit", (code) => (exited = code ?? "signal"));
  try {
    for (let i = 0; i < 100 && exited === null && ((await get(port, "/messages", token))?.messages || []).length < 2; i++) await new Promise((r) => setTimeout(r, 100));
    for (const [quote, t] of [["IN2", "sent the invoice"], ["IN1", "export is on its way"], [{ id: "OLD9", text: "can you call me" }, "calling now"],
      [{ id: "OLD8" }, "no words to quote"], [{ id: "G1", text: "who has the keys" }, "I do"]])
      assert.equal((await post(port, "/send", { jid: quote.id === "G1" ? "120363000000000007@g.us" : jid, text: t, quote }, auth)).code, 200, out);
    assert.equal((await post(port, "/send", { jid, text: "plain" }, auth)).code, 200);
    const sent = fs.readFileSync(path.join(dir, "sent.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l));
    const q = sent.map((s) => s.quoted && [s.quoted.key.id, s.quoted.key.remoteJid, s.quoted.message.conversation]);
    assert.deepEqual(q, [["IN2", jid, "and the invoice too"], ["IN1", jid, "the export is late"], ["OLD9", jid, "can you call me"], null, null, null]);
  } finally {
    if (exited === null) { const gone = new Promise((r) => child.once("exit", r)); child.kill(); await gone; }
    fs.rmSync(dir, { recursive: true, force: true, maxRetries: 5 });
  }
});

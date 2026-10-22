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

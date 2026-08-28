// The WhatsApp bridge: Baileys (WhatsApp Web protocol) on one side, a tiny localhost HTTP
// API on the other. Taskuary polls GET /messages and posts replies to POST /send - it never
// loads Baileys itself, so the heavy dependency lives here, behind its own `npm install`.
//
//   cd taskuary/whatsapp
//   npm install
//   node bridge.mjs                 pair by QR (printed here), or:
//   node bridge.mjs --phone 15551234567   pair by code (enter it under Linked devices)
//
// Auth persists in ./wa-auth, so pairing is a one-time step. The bridge keeps the last
// MAX_KEPT messages in memory with a sequence number; Taskuary remembers where it got to.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import makeWASocket, { useMultiFileAuthState, DisconnectReason, downloadMediaMessage } from "@whiskeysockets/baileys";

// Voice notes are saved beside the bridge and handed to Taskuary as a PATH (same machine); it
// transcribes them if a voice connector exists and files them with the reason if not. A
// message with no text used to be dropped here, so a voice note simply never existed.
const MEDIA_DIR = path.resolve("wa-media");

const PORT = Number(process.env.WA_BRIDGE_PORT || 8977);
const PHONE = (process.argv.includes("--phone") && process.argv[process.argv.indexOf("--phone") + 1]) || "";
const MAX_KEPT = 500;

let sock = null, connected = false, me = "", qr = "", pairingCode = "", seq = 0;
const messages = [];                       // { seq, id, jid, chat, name, text, ts, fromMe }

const text = (m) => m.conversation || m.extendedTextMessage?.text
  || m.imageMessage?.caption || m.videoMessage?.caption || m.documentMessage?.caption || "";

async function connect() {
  const { state, saveCreds } = await useMultiFileAuthState("wa-auth");
  sock = makeWASocket({ auth: state, printQRInTerminal: false, markOnlineOnConnect: false });
  sock.ev.on("creds.update", saveCreds);
  sock.ev.on("connection.update", async (u) => {
    if (u.qr) {
      qr = u.qr;
      if (PHONE && !state.creds.registered) {
        pairingCode = await sock.requestPairingCode(PHONE.replace(/\D/g, ""));
        console.log(`pair by code: enter ${pairingCode} on your phone (Settings > Linked devices)`);
      } else {
        console.log("scan this QR from WhatsApp > Linked devices (also served at /status):\n");
        try { (await import("qrcode-terminal")).default.generate(qr, { small: true }); }
        catch { console.log(qr, "\n(npm install qrcode-terminal to render it as a scannable block)"); }
      }
    }
    if (u.connection === "open") {
      connected = true; qr = ""; pairingCode = "";
      me = sock.user?.name || sock.user?.id || "";
      console.log(`connected as ${me}`);
    }
    if (u.connection === "close") {
      connected = false;
      const code = u.lastDisconnect?.error?.output?.statusCode;
      if (code !== DisconnectReason.loggedOut) { console.log("reconnecting…"); connect(); }
      else console.log("logged out - delete ./wa-auth and pair again");
    }
  });
  sock.ev.on("messages.upsert", async ({ messages: ms, type }) => {
    if (type !== "notify") return;                       // history syncs are not new work
    for (const m of ms) {
      const body = text(m.message || {});
      if (!body && !m.message) continue;
      const am = m.message?.audioMessage;
      let audio = "", mime = "", seconds = 0;
      if (am && !m.key.fromMe) {
        try {
          const buf = await downloadMediaMessage(m, "buffer", {}, { reuploadRequest: sock.updateMediaMessage });
          fs.mkdirSync(MEDIA_DIR, { recursive: true });
          mime = String(am.mimetype || "audio/ogg").split(";")[0];
          audio = path.join(MEDIA_DIR, `${m.key.id}.${mime.includes("ogg") ? "ogg" : mime.includes("mp4") ? "m4a" : "bin"}`);
          fs.writeFileSync(audio, buf);
          seconds = Number(am.seconds) || 0;
        } catch (e) { console.log("voice note download failed:", e?.message || e); audio = ""; }
      }
      messages.push({ seq: ++seq, id: m.key.id, jid: m.key.remoteJid, group: m.key.remoteJid?.endsWith("@g.us"),
        name: m.pushName || "", text: body, ts: Number(m.messageTimestamp) || Math.floor(Date.now() / 1000),
        fromMe: !!m.key.fromMe, key: m.key,      // the whole key: read receipts need participant too
        audio, mime, seconds, voice: !!am?.ptt });
      while (messages.length > MAX_KEPT) messages.shift();
    }
  });
}

const json = (res, code, obj) => { res.writeHead(code, { "content-type": "application/json" }); res.end(JSON.stringify(obj)); };

http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  try {
    if (req.method === "GET" && url.pathname === "/status")
      return json(res, 200, { connected, me, qr, pairingCode, seq, kept: messages.length });
    if (req.method === "GET" && url.pathname === "/messages") {
      const after = Number(url.searchParams.get("after") || 0);
      return json(res, 200, { seq, messages: messages.filter((m) => m.seq > after) });
    }
    // blue ticks for what the hub has already taken in - ids come back from /messages, and
    // the key we kept with them is what Baileys needs. Unknown ids (rotated out of the
    // kept window) are simply skipped: a missed receipt is never worth a failed poll.
    if (req.method === "POST" && url.pathname === "/read") {
      const chunks = []; for await (const c of req) chunks.push(c);
      const { ids } = JSON.parse(Buffer.concat(chunks).toString() || "{}");
      if (!connected) return json(res, 503, { error: "not connected to WhatsApp" });
      const want = new Set(ids || []);
      const keys = messages.filter((m) => want.has(m.id) && m.key).map((m) => m.key);
      if (keys.length) await sock.readMessages(keys);
      return json(res, 200, { ok: true, marked: keys.length });
    }
    if (req.method === "POST" && url.pathname === "/send") {
      const chunks = []; for await (const c of req) chunks.push(c);
      const { jid, text: t } = JSON.parse(Buffer.concat(chunks).toString() || "{}");
      if (!connected) return json(res, 503, { error: "not connected to WhatsApp" });
      if (!jid || !t) return json(res, 400, { error: "jid and text are required" });
      await sock.sendMessage(jid, { text: t });
      return json(res, 200, { ok: true });
    }
    json(res, 404, { error: "unknown path" });
  } catch (e) { json(res, 500, { error: String(e?.message || e) }); }
}).listen(PORT, "127.0.0.1", () => console.log(`bridge listening on http://127.0.0.1:${PORT}`));

connect().catch((e) => { console.error("could not start:", e); process.exit(1); });

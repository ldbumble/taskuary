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
import { createChatGate, nextReconnect } from "./policy.mjs";
import { createChatRoster } from "./roster.mjs";

// Voice notes are saved beside the bridge and handed to Taskuary as a PATH (same machine); it
// transcribes them if a voice connector exists and files them with the reason if not. A
// message with no text used to be dropped here, so a voice note simply never existed.
const MEDIA_DIR = path.resolve("wa-media");

const PORT = Number(process.env.WA_BRIDGE_PORT || 8977);
// Taskuary mints this when it starts the bridge (wabridge.token) and sends it on every request.
// Without it any process on the machine could POST /send; with an Origin header, any web PAGE
// could - a cross-site POST to 127.0.0.1 is a "simple request" browsers let through.
const TOKEN = process.env.WA_BRIDGE_TOKEN || "";
const PHONE = (process.argv.includes("--phone") && process.argv[process.argv.indexOf("--phone") + 1]) || "";
const MAX_KEPT = 500;

let sock = null, connected = false, me = "", meJid = "", qr = "", pairingCode = "", seq = 0;
const messages = [];                       // { seq, id, jid, chat, name, text, ts, fromMe }
const taskuarySent = new Set();             // ids sent through localhost /send, never user prompts
const chatGate = createChatGate();
const chatRoster = createChatRoster();       // JIDs/names/recency only; never message bodies
try {
  if (process.env.WA_BRIDGE_FILTER) chatGate.configure(JSON.parse(process.env.WA_BRIDGE_FILTER));
} catch (e) { console.error("invalid WA_BRIDGE_FILTER; keeping every chat closed:", e?.message || e); }
let reconnectTimer = null, reconnectAttempt = 0, reconnectAt = 0, reconnectPaused = false;
let openedAt = 0, lastDisconnect = "";

const text = (m) => m.conversation || m.extendedTextMessage?.text
  || m.imageMessage?.caption || m.videoMessage?.caption || m.documentMessage?.caption || "";
const context = (m) => Object.values(m || {}).find((v) => v?.contextInfo)?.contextInfo;

const reconnectStatus = () => ({
  attempt: reconnectAttempt, paused: reconnectPaused, at: reconnectAt, reason: lastDisconnect
});

function scheduleReconnect(reason) {
  if (reconnectTimer || reconnectPaused) return;
  lastDisconnect = String(reason || "connection closed").slice(0, 160);
  const decision = nextReconnect(reconnectAttempt, openedAt ? Date.now() - openedAt : 0);
  openedAt = 0;
  if (decision.paused) {
    reconnectPaused = true;
    reconnectAt = 0;
    console.error(`automatic reconnect paused after ${reconnectAttempt} unstable attempts; restart the bridge when the connection is stable`);
    return;
  }
  reconnectAttempt = decision.attempt;
  reconnectAt = Date.now() + decision.delayMs;
  console.log(`reconnecting in ${Math.ceil(decision.delayMs / 1000)}s (attempt ${reconnectAttempt})...`);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    reconnectAt = 0;
    connect().catch((e) => {
      console.error("reconnect failed:", e?.message || e);
      scheduleReconnect(e?.message || e);
    });
  }, decision.delayMs);
}

async function connect() {
  const { state, saveCreds } = await useMultiFileAuthState("wa-auth");
  const thisSock = makeWASocket({
    auth: state,
    printQRInTerminal: false,
    markOnlineOnConnect: false,
    // Taskuary needs new messages, never a copy of the account. Specify both controls so a
    // Baileys upgrade cannot silently change its defaults and download chat history.
    syncFullHistory: false,
    shouldSyncHistoryMessage: () => false,
    // Ignored JIDs are acknowledged before decryption. Taskuary supplies the active source list.
    shouldIgnoreJid: chatGate.shouldIgnore
  });
  sock = thisSock;
  thisSock.ev.on("creds.update", saveCreds);
  thisSock.ev.on("connection.update", async (u) => {
    if (thisSock !== sock) return;
    if (u.qr) {
      qr = u.qr;
      if (PHONE && !state.creds.registered) {
        pairingCode = await thisSock.requestPairingCode(PHONE.replace(/\D/g, ""));
        console.log(`pair by code: enter ${pairingCode} on your phone (Settings > Linked devices)`);
      } else {
        console.log("scan this QR from WhatsApp > Linked devices (also served at /status):\n");
        try { (await import("qrcode-terminal")).default.generate(qr, { small: true }); }
        catch { console.log(qr, "\n(npm install qrcode-terminal to render it as a scannable block)"); }
      }
    }
    if (u.connection === "open") {
      connected = true; qr = ""; pairingCode = "";
      reconnectAt = 0; reconnectPaused = false; openedAt = Date.now();
      me = thisSock.user?.name || thisSock.user?.id || "";
      meJid = thisSock.user?.id || "";                   // 15551234567:12@s.whatsapp.net - the number is who the owner IS here
      console.log(`connected as ${me}`);
      // Baileys exposes every group this linked account is still participating in without a
      // message-history download. This gives compose a real account roster even when a group has
      // never been allowed into Taskuary's inbound timeline.
      thisSock.groupFetchAllParticipating().then((groups) => {
        if (thisSock !== sock) return;
        chatRoster.replaceGroups(Object.values(groups || {}));
      }).catch((e) => console.log("could not refresh WhatsApp group roster:", e?.message || e));
    }
    if (u.connection === "close") {
      connected = false;
      const code = u.lastDisconnect?.error?.output?.statusCode;
      const why = u.lastDisconnect?.error?.message || `WhatsApp closed the socket${code ? ` (${code})` : ""}`;
      if (code !== DisconnectReason.loggedOut) scheduleReconnect(why);
      else { reconnectPaused = true; lastDisconnect = "logged out"; console.log("logged out - delete ./wa-auth and pair again"); }
    }
  });
  thisSock.ev.on("contacts.upsert", (contacts) => {
    if (thisSock === sock) for (const contact of contacts || []) chatRoster.upsertContact(contact);
  });
  thisSock.ev.on("contacts.update", (contacts) => {
    if (thisSock === sock) for (const contact of contacts || []) chatRoster.upsertContact(contact);
  });
  thisSock.ev.on("chats.upsert", (chats) => {
    if (thisSock === sock) for (const chat of chats || []) chatRoster.upsertChat(chat);
  });
  thisSock.ev.on("chats.update", (chats) => {
    if (thisSock === sock) for (const chat of chats || []) chatRoster.upsertChat(chat);
  });
  thisSock.ev.on("chats.delete", (jids) => {
    if (thisSock === sock) chatRoster.remove(jids);
  });
  thisSock.ev.on("groups.upsert", (groups) => {
    if (thisSock === sock) for (const group of groups || []) chatRoster.upsertChat(group);
  });
  thisSock.ev.on("groups.update", (groups) => {
    if (thisSock === sock) for (const group of groups || []) chatRoster.upsertChat(group);
  });
  // Kept for Baileys configurations that permit a metadata/history sync. Taskuary's bridge has
  // history sync disabled, and even here only chat/contact metadata is observed.
  thisSock.ev.on("messaging-history.set", ({ chats = [], contacts = [] }) => {
    if (thisSock !== sock) return;
    for (const contact of contacts) chatRoster.upsertContact(contact);
    for (const chat of chats) chatRoster.upsertChat(chat);
  });
  thisSock.ev.on("messages.upsert", async ({ messages: ms, type }) => {
    if (thisSock !== sock) return;
    if (type !== "notify") return;                       // history syncs are not new work
    for (const m of ms) {
      chatRoster.observeMessage(m);
      const body = text(m.message || {}), quoted = text(context(m.message || {})?.quotedMessage || {});
      if (!body && !m.message) continue;
      const am = m.message?.audioMessage, im = m.message?.imageMessage;
      // ...and a DOCUMENT. Only audio and images were ever fetched, so a .docx dropped into
      // the chat had no text, no audio and no image - and messengers.py, which requires one
      // of those three, discarded the whole message. A file somebody sent you simply never
      // existed. (documentWithCaptionMessage is the same thing wearing a caption.)
      const dm = m.message?.documentMessage
        || m.message?.documentWithCaptionMessage?.message?.documentMessage;
      // A PHOTO is the message. Downloading only the audio meant a screenshot arrived as its
      // caption or as nothing at all - "on my laptop, words look weird" with the picture of the
      // broken words dropped on the floor, and triage ruling on a sentence about nothing.
      const grab = async (node, fallbackMime, ext) => {
        if (!node || m.key.fromMe) return ["", ""];
        try {
          const buf = await downloadMediaMessage(m, "buffer", {}, { reuploadRequest: thisSock.updateMediaMessage });
          fs.mkdirSync(MEDIA_DIR, { recursive: true });
          const mt = String(node.mimetype || fallbackMime).split(";")[0];
          const file = path.join(MEDIA_DIR, `${m.key.id}.${ext(mt)}`);
          fs.writeFileSync(file, buf);
          return [file, mt];
        } catch (e) { console.log("media download failed:", e?.message || e); return ["", ""]; }
      };
      const [audio, mime] = await grab(am, "audio/ogg",
        (mt) => (mt.includes("ogg") ? "ogg" : mt.includes("mp4") ? "m4a" : "bin"));
      const [image, imageMime] = await grab(im, "image/jpeg",
        (mt) => (mt.includes("png") ? "png" : mt.includes("webp") ? "webp" : "jpg"));
      // keep the sender's own extension where there is one: "Homepage Copy.docx" is the name the
      // owner will look for, and a .bin they cannot open is barely better than losing it
      const [doc, docMime] = await grab(dm, "application/octet-stream",
        () => (String(dm?.fileName || "").split(".").pop() || "bin").slice(0, 8).toLowerCase());
      messages.push({ seq: ++seq, id: m.key.id, jid: m.key.remoteJid,
        sender: m.key.participant || m.key.remoteJid, group: m.key.remoteJid?.endsWith("@g.us"),
        name: m.pushName || "", text: body, ts: Number(m.messageTimestamp) || Math.floor(Date.now() / 1000),
        fromMe: !!m.key.fromMe, quoted, key: m.key, // quote routes phone answers; key is for read receipts
        audio, mime, seconds: Number(am?.seconds) || 0, voice: !!am?.ptt, image, imageMime,
        doc, docMime, docName: dm?.fileName || "", taskuary: taskuarySent.has(m.key.id) });
      while (messages.length > MAX_KEPT) messages.shift();
    }
  });
}

const json = (res, code, obj) => { res.writeHead(code, { "content-type": "application/json" }); res.end(JSON.stringify(obj)); };

http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  try {
    if (req.headers.origin !== undefined) return json(res, 403, { error: "browsers may not call the bridge" });
    if (TOKEN && req.headers["x-bridge-token"] !== TOKEN) return json(res, 401, { error: "bridge token missing or wrong" });
    if (req.method === "GET" && url.pathname === "/status")
      return json(res, 200, { connected, me, jid: meJid, qr, pairingCode, seq, kept: messages.length,
        filter: chatGate.snapshot(), reconnect: reconnectStatus() });
    if (req.method === "POST" && url.pathname === "/filter") {
      const chunks = []; for await (const c of req) chunks.push(c);
      const policy = JSON.parse(Buffer.concat(chunks).toString() || "{}");
      return json(res, 200, { ok: true, filter: chatGate.configure(policy) });
    }
    if (req.method === "GET" && url.pathname === "/messages") {
      const after = Number(url.searchParams.get("after") || 0);
      return json(res, 200, { seq, messages: messages.filter((m) => m.seq > after),
        blockedChats: chatGate.blockedChats() });
    }
    if (req.method === "GET" && url.pathname === "/chats") {
      const blocked = chatGate.blockedChats();
      return json(res, 200, { chats: chatRoster.list(blocked).map((chat) => ({
        ...chat, snippet: blocked.some((x) => x.jid === chat.jid)
          ? "not opened - chat is not authorized" : ""
      })) });
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
      const sent = await sock.sendMessage(jid, { text: t });
      const id = sent?.key?.id || "";
      if (id) {
        taskuarySent.add(id);
        // Baileys may emit messages.upsert before sendMessage resolves. Mark that already-kept
        // echo as ours as well, closing the race without relying on visible magic text.
        const echo = messages.find((m) => m.id === id);
        if (echo) echo.taskuary = true;
        if (taskuarySent.size > MAX_KEPT * 2) taskuarySent.delete(taskuarySent.values().next().value);
      }
      return json(res, 200, { ok: true, id });
    }
    json(res, 404, { error: "unknown path" });
  } catch (e) { json(res, 500, { error: String(e?.message || e) }); }
}).listen(PORT, "127.0.0.1", () => console.log(`bridge listening on http://127.0.0.1:${PORT}`));

connect().catch((e) => {
  console.error("could not connect:", e?.message || e);
  scheduleReconnect(e?.message || e);
});

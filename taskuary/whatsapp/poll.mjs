// THE ASSISTANT'S CHOICES AS A WHATSAPP POLL. A chat has no buttons; a poll is the one tappable thing
// WhatsApp lets an account send, so the numbered choices go out as one too (the owner, 2026-09-25:
// "whatsapp, yes try polls"). A vote comes back encrypted, and this Baileys no longer decrypts it for
// us, so the poll's secret is ours to keep and the vote is opened here - then it re-enters the bridge
// as the chosen option's words, exactly as if the owner had typed them.
import crypto from "node:crypto";
import { decryptPollVote } from "@whiskeysockets/baileys";

export const MAX_OPTIONS = 12, MAX_LABEL = 100;      // WhatsApp's own limits

// the options a poll can carry: distinct, non-empty, cut to WhatsApp's length, at most twelve
export function pollValues(values) {
  const seen = new Set(), out = [];
  for (const v of values || []) {
    const s = String(v ?? "").trim().slice(0, MAX_LABEL);
    if (s && !seen.has(s)) { seen.add(s); out.push(s); }
  }
  return out.slice(0, MAX_OPTIONS);
}

const sha = (s) => crypto.createHash("sha256").update(Buffer.from(s)).digest("hex");
const bare = (j) => String(j || "").replace(/:\d+(?=@)/, "");      // "123:4@s.whatsapp.net" -> the user, not the device

// Only the NEWEST poll in a chat answers: a vote on one three turns back names choices that are gone,
// and the numbered list it was sent with has been replaced (a stale pick must never fire).
export function createPolls(max = 200, keep = 8) {
  const byChat = new Map();                                   // jid -> { id, secret, values }, the newest only
  // ...and the few before it in each chat - never to ANSWER (a stale pick must never fire), only to know that a tap on
  // one was a real pick on a list that is gone, so the owner is told so instead of hearing nothing (2026-09-29)
  const older = new Map();                                    // jid -> [{ id, secret, values }], newest first
  const open = (p, enc, creators, voters) => {
    const cs = [...new Set(creators.flatMap((j) => [j, bare(j)]).filter(Boolean))];
    const vs = [...new Set(voters.flatMap((j) => [j, bare(j)]).filter(Boolean))];
    for (const c of cs) for (const v of vs) {
      let got;
      try { got = decryptPollVote(enc, { pollCreatorJid: c, pollMsgId: p.id, pollEncKey: p.secret, voterJid: v }); }
      catch { continue; }
      const picked = (got?.selectedOptions || []).map((b) => Buffer.from(b).toString("hex"));
      return p.values.find((x) => picked.includes(sha(x))) || "";
    }
    return "";
  };
  return {
    remember(jid, id, secret, values) {
      const was = byChat.get(jid);
      if (was) older.set(jid, [was, ...(older.get(jid) || [])].slice(0, keep));
      byChat.delete(jid); byChat.set(jid, { id, secret, values });
      while (byChat.size > max) { const k = byChat.keys().next().value; byChat.delete(k); older.delete(k); }
    },
    latest: (jid) => byChat.get(jid) || null,
    // the chat of an OLDER poll of ours this update really picked an option on (a taken-back vote is no tap), or ""
    stale(update, { creators = [], voters = [] } = {}) {
      const key = update?.pollCreationMessageKey, enc = update?.vote;
      if (!key || !enc?.encPayload) return "";
      for (const [jid, list] of older) {
        const p = list.find((x) => x.id === key.id);
        if (p) return open(p, enc, creators, voters) ? jid : "";
      }
      return "";
    },
    // the chosen option's words, or "" (not our poll, not the newest, a vote taken back, or unreadable).
    // Found by the poll's id, not the chat: a vote can name the chat by its LID while we sent to the number.
    // Which jid signed the vote depends on the account (a phone number or a LID, with or without the
    // device), so each plausible pair is tried - the GCM tag says which one is right.
    // A POLL ANSWERS ONCE (the owner, 2026-10-02: "once a poll is answered it should never be allowed to be used again"):
    // WhatsApp cannot close a poll, so the first real pick spends it here - a re-tap or a changed vote answers nothing
    vote(update, { creators = [], voters = [] } = {}) {
      const key = update?.pollCreationMessageKey, enc = update?.vote;
      const p = key && [...byChat.values()].find((x) => x.id === key.id);
      if (!p || p.used || !enc?.encPayload) return "";
      const got = open(p, enc, creators, voters);
      if (got) p.used = true;
      return got;
    },
    // the chat of the NEWEST poll when this update is a real pick on it after it was already spent, or "" - told, never run
    spent(update, { creators = [], voters = [] } = {}) {
      const key = update?.pollCreationMessageKey, enc = update?.vote;
      if (!key || !enc?.encPayload) return "";
      for (const [jid, p] of byChat) if (p.id === key.id) return p.used && open(p, enc, creators, voters) ? jid : "";
      return "";
    },
  };
}

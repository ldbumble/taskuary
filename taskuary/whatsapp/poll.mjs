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
export function createPolls(max = 200) {
  const byChat = new Map();                                   // jid -> { id, secret, values }, the newest only
  return {
    remember(jid, id, secret, values) {
      byChat.delete(jid); byChat.set(jid, { id, secret, values });
      while (byChat.size > max) byChat.delete(byChat.keys().next().value);
    },
    latest: (jid) => byChat.get(jid) || null,
    // the chosen option's words, or "" (not our poll, not the newest, a vote taken back, or unreadable).
    // Found by the poll's id, not the chat: a vote can name the chat by its LID while we sent to the number.
    // Which jid signed the vote depends on the account (a phone number or a LID, with or without the
    // device), so each plausible pair is tried - the GCM tag says which one is right.
    vote(update, { creators = [], voters = [] } = {}) {
      const key = update?.pollCreationMessageKey, enc = update?.vote;
      const p = key && [...byChat.values()].find((x) => x.id === key.id);
      if (!p || !enc?.encPayload) return "";
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
    },
  };
}

// A CHAT READS AS A CHAT (the owner, 2026-10-15: "it should be my chat, their chat, like a chat history. this is unreadable ...
// same for teams"). A WhatsApp or Teams task stacked each message as its own block - a name and a time, then the words or an
// audio player - newest first, with the owner's own replies drawn apart, so a conversation read as a pile of unrelated notes.
// Here it is the thread itself: NEWEST AT THE TOP, as every message list in the app reads (the owner, 2026-10-14, and again
// 2026-10-15: "i thought all messages are newest first on top, same as in email - make sure it's consistent"), theirs on the
// left and yours on the right, one name over each run of messages, a day line over each day, and what they sent - a voice
// note, a photo - inside the bubble it came in.
import React from "react";
import { Box, Typography } from "@mui/material";
import { Attachments } from "./Attachments.jsx";
import { cleanText, tsMs } from "./ui.jsx";
import { dayLabel, fmtTime } from "./dates.js";
import { BORDER, FAINT, INK } from "./theme.jsx";

// the channels whose messages are a conversation, not letters
export const CHAT_CHANNELS = new Set(["whatsapp", "teams", "slack", "telegram", "imessage", "discord", "mattermost",
  "google_chat", "rocketchat", "matrix", "signal", "sms"]);
export const isChatTask = (messages = []) => {
  const inbound = messages.filter((m) => !mine(m));
  return inbound.length > 0 && inbound.every((m) => CHAT_CHANNELS.has(String(m.Channel || "").toLowerCase()));
};

// yours: a line you wrote on the platform (kept as context) or a reply Taskuary sent for you
export const mine = (m) => m.Status === "context" || m.Direction === "out" || !!m.ReviewSent;

const NO_TEXT = /^\(no text - see the attachment\)$/;
// "(🎤 voice note (17s) from WhatsApp, transcribed by Groq (Whisper))" - said once, small, under the words it carried
const VOICE = /\n*\(🎤 voice note[\s\S]*\)\s*$/i;
export const splitBody = (body) => {
  const text = cleanText(String(body || ""));
  const voice = VOICE.test(text);
  const words = text.replace(VOICE, "").trim();
  return { words: NO_TEXT.test(words) ? "" : words, voice };
};

const dayOf = (at) => { const d = new Date(tsMs(at)); return Number.isNaN(d.getTime()) ? "" : d.toDateString(); };
const timeOf = (at) => { const d = new Date(tsMs(at)); return Number.isNaN(d.getTime()) ? "" : fmtTime(d, undefined, { hour: "numeric", minute: "2-digit" }); };

// COMPACT (the task-view cleanup, owner-approved 2026-10-25: Show all on a six-message burst drew 476px, about 79px a message): the name
// INSIDE the bubble, once per run of one sender's messages, and the time at the end of the line - about 34px for a one-line message.
// Still the back-and-forth (2026-10-16), yours on the right, in its centred column with the line round it (2026-10-15). The first name
// only, the run being read down a column; the full name is the bubble's hover. A bubble may take 86% of the column (70% before): the
// thread is read in From's 300-520px now, where 70% broke a one-line message onto two.
const firstName = (m) => String(m.FromName || m.FromEmail || m.Channel || "").split(/[\s@]+/)[0];

export default function ChatThread({ messages = [], maxHeight = 460 }) {
  // newest first, like the rest of the app: the box opens at its top, which is the latest line
  const list = [...messages].sort((a, b) => tsMs(b.SentAt) - tsMs(a.SentAt));
  return (
    <Box data-tq-chat-thread="" sx={{ mt: 0.85, width: "100%", maxWidth: 800, mx: "auto", boxSizing: "border-box", maxHeight, overflowY: "auto", px: 1, py: 0.75,
      border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: "#f6f3ee", display: "flex", flexDirection: "column", gap: 0.35 }}>
      {list.map((m, i) => {
        const me = mine(m), prev = list[i - 1];
        const newDay = !prev || dayOf(prev.SentAt) !== dayOf(m.SentAt);
        const newRun = newDay || !prev || mine(prev) !== me || (!me && (prev.FromName || prev.FromEmail) !== (m.FromName || m.FromEmail));
        const { words, voice } = splitBody(m.ReadText ?? m.BodyText);
        const hasFiles = typeof m.MessageId === "number";
        return (
          <React.Fragment key={m.MessageId}>
            {newDay && <Typography sx={{ alignSelf: "center", fontSize: 10.5, color: FAINT, bgcolor: "#ece6dc", px: 1, py: 0.1,
              borderRadius: 99, my: 0.3 }}>{dayLabel(m.SentAt)}</Typography>}
            {/* the conversation is a centred column, its own line around it - theirs and yours a reading distance apart, not the two
                edges of a wide window (the owner, 2026-10-15: "center them in the chat ... make line around the chat that is centered
                to show it's contained") */}
            <Box data-tq-chat-msg={me ? "mine" : "theirs"} sx={{ display: "flex", flexDirection: "column", alignItems: me ? "flex-end" : "flex-start",
              mt: newRun && !newDay ? 0.4 : 0 }}>
              <Box title={me ? undefined : m.FromName || m.FromEmail || undefined}
                sx={{ maxWidth: { xs: "88%", md: "min(86%, 640px)" }, minWidth: 0, px: 1.1, py: 0.45, borderRadius: 2,
                borderTopLeftRadius: !me && newRun ? 4 : undefined, borderTopRightRadius: me && newRun ? 4 : undefined,
                bgcolor: me ? "#dfe9df" : "#fff", border: `1px solid ${me ? "#cddccd" : BORDER}`,
                color: INK, fontSize: 13.5, lineHeight: 1.45, overflowWrap: "anywhere" }}>
                <Box component="span" sx={{ whiteSpace: "pre-wrap" }}>
                  {newRun && !me && <Box component="span" sx={{ fontWeight: 600, mr: 0.75 }}>{firstName(m)}</Box>}
                  {words}</Box>
                {/* the time at the line's end, on the line: a one-line message stays one line */}
                <Box component="span" sx={{ display: "inline-block", color: FAINT, fontSize: 11, ml: 1.25, whiteSpace: "nowrap" }}>
                  {voice ? "🎤 transcribed · " : ""}{timeOf(m.SentAt)}</Box>
                {/* full reading size, as wide as the bubble - the small one was a thumbnail you had to click to read
                    (the owner, 2026-10-15: "images do look small in the chat") */}
                {hasFiles && <Attachments messageId={m.MessageId} />}
              </Box>
            </Box>
          </React.Fragment>
        );
      })}
    </Box>
  );
}

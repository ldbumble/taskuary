// SETTINGS > PHONE & CHATS (the owner, 2026-11-06: "it's not clear where that is"): every chat that reaches Taskuary from outside, on one
// page. The Assistant from your phone - the owner's private WhatsApp or Telegram chat, its knobs and the walk handed to it - and, in
// Developer mode only, the chats bound to coding agents (agentchannels.py), each with what it talks to, its repo, its people and Unbind.
import React from "react";
import { Box, Typography } from "@mui/material";
import { ChannelSetup } from "./AgentChannels.jsx";
import { ASSISTANT_LINE, RULES, SECTION_TITLE, bindingRow, phoneSections } from "./phoneChats.js";
import { DIM, FAINT, INK } from "./theme.jsx";

const link = { color: "#55697a", textDecoration: "none", "&:hover": { textDecoration: "underline" } };

// one binding: the channel and chat, then what it talks to, in which repo, with whom
const Binding = ({ c }) => {
  const b = bindingRow(c);
  return (
    <Box data-tq-binding={b.id}>
      <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }} noWrap title={`${b.channel} · ${b.chat}`}>{b.channel} · {b.chat}</Typography>
      <Typography variant="caption" sx={{ color: DIM, display: "block" }}>
        Talks to {b.href ? <Box component="a" href={b.href} sx={link}>{b.what}</Box> : b.what}
        {b.repo ? ` · ${b.repo}` : ""} · {b.people}</Typography>
    </Box>);
};

export default function PhoneChats({ devMode = false, head = (name) => name, assistant = null }) {
  const secs = phoneSections({ devMode });
  return (
    <Box data-tq-phone-chats="">
      <Box data-tq-phone-section="assistant" sx={{ mb: 4.5 }}>
        {head(SECTION_TITLE.assistant)}
        <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>{ASSISTANT_LINE}</Typography>
        {assistant}
      </Box>
      {secs.includes("agents") && (
        <Box data-tq-phone-section="agents" sx={{ mb: 4.5 }}>
          {head(SECTION_TITLE.agents)}
          <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>
            A WhatsApp, Telegram, Slack or Teams chat that talks straight to your coding agents - one task's agent, with teammates if you
            like, or all of them by their TQ number. Your Assistant chat above reaches the coding agents too, while Developer mode is on.</Typography>
          <Box component="ul" sx={{ m: 0, mb: 1.75, pl: 2.25, color: FAINT, fontSize: 12.5, lineHeight: 1.6 }}>
            {RULES.map((r) => <li key={r}>{r}</li>)}
          </Box>
          <ChannelSetup rowOf={(c) => <Binding c={c} />} />
        </Box>
      )}
    </Box>);
}

// THE CHAT PICKER (chatPicker.js): one dropdown for every chat Taskuary is reached on - the Assistant chat, a new agent channel on
// Settings > Phone & chats, and a coding task's "Talk to this agent from…". Names shown, the mark beside each (only you / group /
// direct), typing filters, Look again reads the list again; a row a binding cannot take is greyed with why, never hidden.
import React from "react";
import { Autocomplete, Box, Button, TextField, Typography } from "@mui/material";
import { chatId, chatName, chatTag, filterChats, isBlocked, pickedChat } from "./chatPicker.js";
import { DIM, FAINT, INK } from "./theme.jsx";

export default function ChatPicker({ options = [], value = "", onChange, onLook = null, looking = false, disabled = false, label, placeholder,
  noOptionsText, hint = "", minWidth = 260, attr = {} }) {
  return (
    <Box data-tq-chat-picker="" sx={{ flex: 1, minWidth }}>
      <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
        <Autocomplete size="small" sx={{ flex: 1 }} autoHighlight openOnFocus disabled={disabled}
          options={options} value={pickedChat(options, value)}
          getOptionLabel={(o) => (o ? chatName(o) : "")} isOptionEqualToValue={(o, v) => o.to === v.to}
          getOptionDisabled={isBlocked} filterOptions={(o, st) => filterChats(o, st.inputValue)}
          onChange={(_e, v) => onChange?.(v?.to || "")} noOptionsText={noOptionsText}
          renderOption={(props, o) => (
            <li {...props} key={o.to} data-tq-chat-option={o.to} style={{ display: "block", paddingTop: 4, paddingBottom: 4 }}>
              <Box sx={{ display: "flex", gap: 1, alignItems: "baseline" }}>
                <Typography variant="body2" sx={{ fontSize: 12.5, color: INK, fontWeight: 600 }}>{chatName(o)}</Typography>
                <Typography variant="caption" sx={{ color: DIM, fontSize: 10.5 }}>{chatTag(o)}</Typography>
              </Box>
              {o.blocked && <Typography variant="caption" sx={{ display: "block", color: "var(--tq-danger, #7a2f3c)", fontSize: 10.5 }}>{o.blocked}</Typography>}
              {chatId(o) && <Typography variant="caption" sx={{ display: "block", color: FAINT, fontSize: 10, fontFamily: "monospace" }}>{chatId(o)}</Typography>}
            </li>)}
          renderInput={(params) => <TextField {...params} label={label} placeholder={placeholder} sx={{ bgcolor: "var(--tq-panel, #fff)" }}
            inputProps={{ ...params.inputProps, ...attr }} />} />
        {onLook && <Button size="small" disabled={looking} onClick={onLook} sx={{ fontSize: 11.5, whiteSpace: "nowrap" }}
          title="Read the chats again - after you message yourself, make a group or add your bot">{looking ? "Looking…" : "Look again"}</Button>}
      </Box>
      {hint && <Typography variant="caption" data-tq-chat-hint="" sx={{ display: "block", color: FAINT, mt: 0.5 }}>{hint}</Typography>}
    </Box>);
}

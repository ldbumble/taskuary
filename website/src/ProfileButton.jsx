// The top bar's last button: the owner's avatar, round, beside Quit - About you opens from it (profileAvatar.js says why it is here).
// In the demo too: its owner is the demo world's, read from the same /api/whoami.
import React, { useEffect, useState } from "react";
import { Box, Tooltip } from "@mui/material";
import api from "./api";
import { BORDER, DIM, PANEL2 } from "./theme.jsx";
import { PROFILE_CHANGED, PROFILE_TIP, profileFace } from "./profileAvatar.js";

export default function ProfileButton({ onOpen }) {
  const [face, setFace] = useState(profileFace(null));
  useEffect(() => {
    let live = true;
    const read = () => api.get("/api/whoami").then(({ data }) => live && setFace(profileFace(data))).catch(() => {});
    read(); window.addEventListener(PROFILE_CHANGED, read);
    return () => { live = false; window.removeEventListener(PROFILE_CHANGED, read); };
  }, []);
  return (
    <Tooltip title={PROFILE_TIP}>
      <Box component="button" type="button" onClick={onOpen} aria-label={PROFILE_TIP} data-tq-profile=""
        sx={{ flexShrink: 0, width: 28, height: 28, p: 0, ml: 0.25, borderRadius: "50%", overflow: "hidden", cursor: "pointer",
          border: `1px solid ${BORDER}`, bgcolor: PANEL2, color: DIM, fontFamily: "inherit", fontSize: 11, fontWeight: 700,
          letterSpacing: 0.3, display: "grid", placeItems: "center", "&:hover": { borderColor: DIM }, "&:focus-visible": { outline: `2px solid ${DIM}`, outlineOffset: 1 } }}>
        {face.pic ? <Box component="img" src={face.pic} alt={face.initials} sx={{ width: "100%", height: "100%", display: "block" }} /> : face.initials}
      </Box>
    </Tooltip>
  );
}

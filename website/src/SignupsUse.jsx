// SIGN-UPS USE (Settings -> Agent permissions, signin.identity; the owner, 2026-11-24): real sites refuse a throwaway inbox, so an agent's
// sign-up fills its email, company, name, phone and address boxes from here - one of his connected mailboxes, the rest optional. Each such
// sign-up waits for his press, its card naming what it uses. Saved as he leaves a box (no Save button); empty, sign-ups are as before.
import React, { useEffect, useState } from "react";
import { Box, MenuItem, TextField, Typography } from "@mui/material";
import api from "./api";
import { FAINT, INK } from "./theme.jsx";

const BOXES = [["company", "Company"], ["name", "Your name"], ["phone", "Phone"], ["address", "Address"]];

export default function SignupsUse() {
  const [who, setWho] = useState(null), [kept, setKept] = useState({}), [boxes, setBoxes] = useState([]), [err, setErr] = useState(""), [said, setSaid] = useState("");
  const show = (d) => { const w = { mailbox: "", company: "", name: "", phone: "", address: "", ...d }; setWho(w); setKept(w); };
  useEffect(() => {
    api.get("/api/signins/as").then(({ data }) => { show(data.data); setBoxes(data.mailboxes || []); })
      .catch((e) => setErr(e?.response?.data?.detail || "What sign-ups use could not be read - Taskuary did not answer."));
  }, []);
  const save = async (next) => {
    setErr(""); setSaid("");
    try { show((await api.post("/api/signins/as", next)).data.data); setSaid("Saved."); }
    catch (e) { setErr(e?.response?.data?.detail || "That was not saved - try again."); }
  };
  if (!who) return err ? <Typography variant="body2" role="alert" sx={{ color: "var(--tq-danger, #a33b3b)", py: 1.5 }}>{err}</Typography> : null;
  const set = (k) => (e) => setWho({ ...who, [k]: e.target.value });
  const leave = (k) => (e) => e.target.value.trim() !== (kept[k] || "") && save({ ...kept, [k]: e.target.value.trim() });
  return (
    <Box data-tq-signups-use="" sx={{ py: 1.5, maxWidth: 560 }}>
      <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5, mb: 0.25 }}>Sign-ups use</Typography>
      <Typography sx={{ color: FAINT, fontSize: 12.5, mb: 1 }}>
        When an agent makes an account for you, it signs up with this mailbox and these details, and the site's code comes back to that
        mailbox. Each sign-up still waits for your press. Left empty, an agent uses an address it made or hands the step to you.</Typography>
      <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" } }}>
        <TextField select size="small" label="Mailbox" value={boxes.includes(who.mailbox) ? who.mailbox : ""} sx={{ gridColumn: "1 / -1" }}
          onChange={(e) => save({ ...kept, mailbox: e.target.value })} inputProps={{ "data-tq-signups-mailbox": "" }}
          helperText={boxes.length ? " " : "Connect a mailbox under Connections to pick it here."}>
          <MenuItem value="" sx={{ fontSize: 13 }}>None</MenuItem>
          {boxes.map((b) => <MenuItem key={b} value={b} sx={{ fontSize: 13 }}>{b}</MenuItem>)}
        </TextField>
        {BOXES.map(([k, l]) => (
          <TextField key={k} size="small" label={`${l} (optional)`} value={who[k]} onChange={set(k)}
            onBlur={leave(k)} autoComplete="off"
            inputProps={{ spellCheck: false, [`data-tq-signups-${k}`]: "" }} sx={k === "address" ? { gridColumn: "1 / -1" } : undefined} />
        ))}
      </Box>
      {(err || said) && <Typography role={err ? "alert" : "status"} sx={{ color: err ? "var(--tq-danger, #a33b3b)" : FAINT, fontSize: 12.5, mt: 0.5 }}>
        {err || said}</Typography>}
    </Box>
  );
}

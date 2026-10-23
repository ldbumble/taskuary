// SHARE A RESULT, on the row by the prompt (the owner, 2026-10-23: "let's have button on report on bottom named share"). The item on the
// table registers ONE verb, Share, and its press opens the row's own kind of ▾ menu at the button: Email it, Shared link, OneDrive /
// SharePoint, Google Drive - each greyed with the reason in its hover where it cannot work (a button that cannot work is greyed).
// The server does the work (taskuary/sharing.py); what went is the card's badge, "✓ Share", never a line.
//
// THE HOOK, for anything that can be shared - a report's result, an agent's Result, a workflow run, and a DASHBOARD when it lands:
//
//   const share = useShare("dashboard", { kind: "dashboard", title, html, data }, !!title);
//   return <>{...the dashboard...}{share}</>;
//
// `result` is a shareable result (share.js): name a `message` or a `task` and the server reads the words from the store; anything else
// brings its own `text` / `html` / `data` rows (the server cleans the HTML - nothing in it runs). Render the returned node where the
// badge belongs; the menu and the Email it dialog open from it. `on` false registers nothing.
import React, { useState } from "react";
import { Box, Button, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Menu, MenuItem, Typography } from "@mui/material";
import api from "./api";
import { useVerbs } from "./actionRow.js";
import { label } from "./buttons.js";
import { openAppLink } from "./appLinks.js";
import { EmailRecipients } from "./NewSheet.jsx";
import { DIM, FAINT } from "./theme.jsx";
import { SETTING_HREF, offersSetting, shareBody, shareVerb, shareable, sharedNote, waysOf } from "./share.js";

const failOf = (e) => e?.response?.data?.detail || e?.message || "It did not go - try again.";

export function useShare(owner, result, on = true, { onShared } = {}) {
  const [at, setAt] = useState(null), [ways, setWays] = useState(null), [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(""), [err, setErr] = useState(""), [done, setDone] = useState(null);
  const [mailOpen, setMailOpen] = useState(false), [people, setPeople] = useState([]), [to, setTo] = useState([]);
  const can = on && shareable(result);
  const open = (e, anchor) => {
    setAt(anchor || e?.currentTarget || null); setErr(""); setWays(null); setFailed(false);
    api.get("/api/shares/ways").then(({ data }) => setWays(data || {})).catch(() => setFailed(true));
  };
  useVerbs(`share:${owner}`, can ? [shareVerb(open, !!busy, busy ? "sharing…" : "")] : [], can);
  if (!can) return null;
  const go = async (how, extra = {}) => {
    setBusy(how); setErr("");
    try {
      const { data } = await api.post("/api/shares", shareBody(result, how, extra));
      let copied = false;
      if (data?.url) { try { await navigator.clipboard.writeText(data.url); copied = true; } catch { copied = false; } }
      setDone({ how, note: sharedNote(how, data, copied) }); setMailOpen(false);
      onShared?.(how, data);
    } catch (e) { setErr(failOf(e)); }
    finally { setBusy(""); }
  };
  const pick = (w) => {
    setAt(null);
    if (!w.ok) return;
    if (w.key !== "email") return go(w.key);
    setTo([]); setMailOpen(true);
    api.get("/api/send-targets").then(({ data }) => setPeople((data?.data || []).find((t) => t.channel === "email")?.to || [])).catch(() => setPeople([]));
  };
  const rows = waysOf(ways, failed);
  return (
    <>
      {done && <span className="tq-pressed" data-tq-pressed={label("share_result")} data-tq-shared={done.how} title={done.note}>✓ {label("share_result")}</span>}
      {err && !mailOpen && <Typography variant="caption" role="alert" sx={{ color: "#a33b3b", display: "block" }}>{err}</Typography>}
      <Menu open={!!at} anchorEl={at} onClose={() => setAt(null)} anchorOrigin={{ vertical: "top", horizontal: "center" }}
        transformOrigin={{ vertical: "bottom", horizontal: "center" }} slotProps={{ paper: { sx: { minWidth: 220, borderRadius: 2 } } }}>
        {rows.map((w) => (
          // greyed, its hover still says why: MUI's disabled item swallows the pointer, so this one only looks and reads disabled
          <MenuItem key={w.key} dense aria-disabled={!w.ok} title={w.why || undefined} data-tq-share={w.key} onClick={() => pick(w)}
            sx={{ fontSize: 13, ...(w.ok ? {} : { opacity: 0.45, cursor: "default", "&:hover": { bgcolor: "transparent" } }) }}>
            {busy === w.key ? "…" : w.word}</MenuItem>
        ))}
        {offersSetting(ways) && (
          <MenuItem dense data-tq-share="setting" onClick={() => { setAt(null); openAppLink(SETTING_HREF); }} sx={{ fontSize: 12, color: DIM }}>
            Share links on my network…</MenuItem>)}
      </Menu>
      <Dialog open={mailOpen} onClose={() => busy !== "email" && setMailOpen(false)} fullWidth maxWidth="sm" PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle>{rows[0]?.word} · {result.title || ""}</DialogTitle>
        <DialogContent sx={{ pt: "8px !important", display: "flex", flexDirection: "column", gap: 1.4 }}>
          <Typography variant="body2" sx={{ color: DIM }}>
            The result goes as the email, its title as the subject. It is drafted for you to read and change - nothing is sent until you press {label("approve")} on the draft.
          </Typography>
          <Box>
            <Typography sx={{ fontSize: 11.5, fontWeight: 600, color: DIM, mb: 0.5 }}>To</Typography>
            <EmailRecipients value={to} onChange={setTo} options={people} placeholder="Search contacts or type an email address" />
            <Typography variant="caption" sx={{ color: FAINT }}>The first is To, anyone after is copied in.</Typography>
          </Box>
          {err && <Typography variant="body2" role="alert" sx={{ color: "#a33b3b" }}>{err}</Typography>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMailOpen(false)} disabled={busy === "email"}>Cancel</Button>
          <Button variant="contained" disableElevation onClick={() => go("email", { to })} disabled={busy === "email" || !to.length}>
            {busy === "email" ? <CircularProgress size={15} /> : rows[0]?.word}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

// the same, for a card that would rather render a component than call a hook conditionally
export default function Share({ owner, result, on = true, onShared }) { return useShare(owner, result, on, { onShared }); }

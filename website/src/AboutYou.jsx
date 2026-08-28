// About you: what the system knows about its owner, gathered on one page - every identity a
// connector learned (with where it came from), the facts only you can add, what the agents are
// actually told, and a generated avatar. Backed by taskuary/whoami.py.
import React, { useCallback, useEffect, useState } from "react";
import { Box, Button, CircularProgress, TextField, Typography } from "@mui/material";
import ShuffleIcon from "@mui/icons-material/Shuffle";
import CheckIcon from "@mui/icons-material/Check";
import api from "./api";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, mono } from "./theme.jsx";
import { ChannelIcon } from "./ui.jsx";

const svgUri = (svg) => `data:image/svg+xml;utf8,${encodeURIComponent(svg || "")}`;
const CHANNEL_LABEL = { email: "Email", teams: "Microsoft Teams", telegram: "Telegram", whatsapp: "WhatsApp", slack: "Slack", github: "GitHub" };
// what a connector learned reads GREEN; what you typed here reads grey - honest about the source
const TYPED = "you typed it here";
const MANUAL = [["owner_phone", "phone (WhatsApp / SMS)", "+1 555 123 4567"], ["owner_telegram", "Telegram handle", "@you"],
  ["owner_slack", "Slack handle", "@you"], ["owner_github", "GitHub login", "you"]];
// which channel each manual field duplicates - if a connector already learned that identity above,
// don't ask for it again below (the field read as a copy of the card)
const FIELD_CHANNEL = { owner_phone: "whatsapp", owner_telegram: "telegram", owner_slack: "slack", owner_github: "github" };

// one editable fact: click-to-edit text, saved on blur or Enter, quiet otherwise
const Fact = ({ label, value, placeholder, onSave, mono: isMono, width = 260 }) => {
  const [v, setV] = useState(value || "");
  useEffect(() => setV(value || ""), [value]);
  const commit = () => { if ((v || "") !== (value || "")) onSave(v.trim()); };
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, py: 1, borderBottom: `1px solid ${BORDER}` }}>
      <Typography variant="body2" sx={{ color: DIM, width: 200, flexShrink: 0 }}>{label}</Typography>
      <TextField size="small" value={v} placeholder={placeholder} onChange={(e) => setV(e.target.value)} onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && e.target.blur()} sx={{ width, bgcolor: "#fff" }}
        inputProps={{ style: { fontSize: 12.5, padding: "6px 10px", ...(isMono ? mono : {}) } }} />
    </Box>
  );
};

export default function AboutYou() {
  const [p, setP] = useState(null);
  const [err, setErr] = useState("");
  const [preview, setPreview] = useState(null);       // {svg, style, seed} not yet kept
  const load = useCallback(async () => {
    try { setP((await api.get("/api/whoami")).data); setErr(""); }
    catch (e) { setErr(e?.response?.data?.detail || "could not load your profile"); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const save = async (fields) => { try { setP((await api.patch("/api/whoami", fields)).data); } catch (e) { setErr(e?.response?.data?.detail || "save failed"); } };
  const saveOwner = async (name, email) => {
    try { await api.put("/api/owner", { name: name || p.facts.owner_name || "the owner", email }); load(); }
    catch (e) { setErr(e?.response?.data?.detail || "save failed"); }
  };
  const shuffle = async (style) => {
    const seed = Math.random().toString(36).slice(2, 10);
    const { data } = await api.get("/api/whoami/avatar", { params: { style: style || preview?.style || p.facts.owner_avatar_style || "monogram", seed } });
    setPreview(data);
  };
  const keep = async () => { if (preview) { await save({ owner_avatar_style: preview.style, owner_avatar_seed: preview.seed }); setPreview(null); } };
  if (!p) return err ? <Typography sx={{ color: "#6b2733" }}>{err}</Typography> : <CircularProgress size={22} sx={{ m: 4 }} />;
  const f = p.facts;
  const byChannel = p.identities.reduce((acc, i) => { (acc[i.channel] = acc[i.channel] || []).push(i); return acc; }, {});
  return (
    <Box sx={{ maxWidth: 860 }}>
      {err && <Typography variant="body2" sx={{ color: "#6b2733", mb: 1 }}>{err}</Typography>}

      {/* the card: avatar, name, the line under it */}
      <Box sx={{ display: "flex", gap: 3, alignItems: "flex-start", p: 2.5, border: `1px solid ${BORDER}`, borderRadius: 3, bgcolor: PANEL2, mb: 3, flexWrap: "wrap" }}>
        <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1 }}>
          <Box component="img" alt="your avatar" src={svgUri(preview ? preview.svg : p.avatar)}
            sx={{ width: 128, height: 128, borderRadius: 4, boxShadow: "0 6px 18px rgba(40,30,20,.14)" }} />
          <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", justifyContent: "center", maxWidth: 170 }}>
            {p.styles.map((s) => (
              <Box key={s} onClick={() => shuffle(s)}
                sx={{ px: 0.9, py: 0.25, borderRadius: 99, cursor: "pointer", fontSize: 10.5, fontWeight: 600, userSelect: "none",
                  bgcolor: (preview?.style || f.owner_avatar_style || "monogram") === s ? "#eae4d8" : "#fff",
                  border: `1px solid ${BORDER}`, color: "#55697a" }}>{s}</Box>
            ))}
          </Box>
          <Box sx={{ display: "flex", gap: 0.5 }}>
            <Button size="small" startIcon={<ShuffleIcon sx={{ fontSize: 14 }} />} onClick={() => shuffle()} sx={{ fontSize: 11.5, textTransform: "none" }}>Generate another</Button>
            {preview && <Button size="small" variant="contained" disableElevation startIcon={<CheckIcon sx={{ fontSize: 14 }} />} onClick={keep} sx={{ fontSize: 11.5, textTransform: "none" }}>Keep</Button>}
          </Box>
        </Box>
        <Box sx={{ flex: 1, minWidth: 280 }}>
          <TextField variant="standard" value={f.owner_name} placeholder="Your name" onChange={(e) => setP({ ...p, facts: { ...f, owner_name: e.target.value } })}
            onBlur={(e) => saveOwner(e.target.value.trim(), f.owner_email)} onKeyDown={(e) => e.key === "Enter" && e.target.blur()}
            inputProps={{ style: { fontSize: 24, fontWeight: 700, color: INK, letterSpacing: "-.01em" } }} fullWidth />
          <Box sx={{ display: "flex", gap: 1, mt: 0.75, flexWrap: "wrap" }}>
            <TextField variant="standard" value={f.owner_title} placeholder="role or title" onChange={(e) => setP({ ...p, facts: { ...f, owner_title: e.target.value } })}
              onBlur={(e) => save({ owner_title: e.target.value.trim() })} inputProps={{ style: { fontSize: 13, color: DIM } }} sx={{ width: 220 }} />
            <TextField variant="standard" value={f.owner_company} placeholder="company" onChange={(e) => setP({ ...p, facts: { ...f, owner_company: e.target.value } })}
              onBlur={(e) => save({ owner_company: e.target.value.trim() })} inputProps={{ style: { fontSize: 13, color: DIM } }} sx={{ width: 220 }} />
          </Box>
          <TextField variant="standard" fullWidth multiline value={f.owner_bio} placeholder="a line about you — what you own, how you like things done; the agents read this"
            onChange={(e) => setP({ ...p, facts: { ...f, owner_bio: e.target.value } })} onBlur={(e) => save({ owner_bio: e.target.value.trim() })}
            inputProps={{ style: { fontSize: 13, color: INK, lineHeight: 1.5 } }} sx={{ mt: 1.5 }} />
        </Box>
      </Box>

      {/* who you are on each channel, with provenance */}
      <Typography sx={{ ...mono, fontSize: 10, letterSpacing: 1, color: FAINT, mb: 1 }}>WHO YOU ARE, PER CHANNEL</Typography>
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>
        Everything a connector has learned about you, and where it learned it. Nothing here is guessed from mail — it is what you signed in as,
        typed under Sources, or set as the chat that pings you.
      </Typography>
      {!p.identities.length && <Typography variant="body2" sx={{ color: FAINT, mb: 2 }}>Nothing yet — connect a mailbox or a chat and it shows up here.</Typography>}
      {/* one card per channel: the value leads, the kind is a small label, and where it came from
          is a quiet chip right beside it - green when read live off a connector, grey when typed */}
      {Object.entries(byChannel).map(([ch, rows]) => (
        <Box key={ch} sx={{ mb: 1.5, bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2.5, overflow: "hidden",
          boxShadow: "0 1px 2px rgba(30,50,38,.04)" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2, py: 1.1, borderBottom: `1px solid ${BORDER}`,
            background: "linear-gradient(180deg,#fffefc,#fbf9f6)" }}>
            <ChannelIcon channel={ch} sx={{ fontSize: 17 }} />
            <Typography sx={{ fontWeight: 700, fontSize: 13.5, color: INK }}>{CHANNEL_LABEL[ch] || ch}</Typography>
            <Box sx={{ flex: 1 }} />
            <Typography sx={{ ...mono, fontSize: 10.5, color: FAINT }}>{rows.length}</Typography>
          </Box>
          {rows.map((r, i) => {
            const live = r.source !== TYPED;
            return (
              <Box key={i} sx={{ display: "grid", gridTemplateColumns: "96px minmax(0,1fr) auto", gap: 1.75, alignItems: "center",
                px: 2, py: 1, borderTop: i ? "1px solid #efeae2" : 0 }}>
                <Typography sx={{ ...mono, fontSize: 10.5, letterSpacing: ".04em", textTransform: "uppercase", color: FAINT }}>{r.kind}</Typography>
                <Typography noWrap sx={{ ...mono, fontSize: 13, color: INK, fontWeight: r.primary ? 700 : 500 }}
                  title={r.value + (r.name ? ` · ${r.name}` : "")}>
                  {r.value}{r.name ? <Box component="span" sx={{ color: FAINT }}>{`  ·  ${r.name}`}</Box> : null}
                  {r.primary ? <Box component="span" sx={{ color: "#6b5f45", fontSize: 11, ml: 0.75 }}>★ owner</Box> : null}
                </Typography>
                <Typography title={r.source} sx={{ justifySelf: "end", fontSize: 11, whiteSpace: "nowrap", maxWidth: 220,
                  overflow: "hidden", textOverflow: "ellipsis", borderRadius: 99, px: 1, py: 0.25,
                  color: live ? "#4c6450" : FAINT, bgcolor: live ? "#eef3ec" : "#f4f1ec",
                  border: `1px solid ${live ? "#cddac9" : BORDER}` }}>{r.source}</Typography>
              </Box>
            );
          })}
        </Box>
      ))}

      {/* the facts nothing can infer */}
      {/* only what no connector already knows: a field a card above already fills would read as a copy */}
      <Typography sx={{ ...mono, fontSize: 10, letterSpacing: 1, color: FAINT, mt: 3, mb: 1 }}>ADD WHAT NOTHING CAN INFER</Typography>
      <Fact label="email (owner address)" value={f.owner_email} placeholder="you@yourdomain.com" mono onSave={(v) => saveOwner(f.owner_name, v)} />
      {MANUAL.filter(([k]) => !byChannel[FIELD_CHANNEL[k]]).map(([k, label, ph]) =>
        <Fact key={k} label={label} value={f[k]} placeholder={ph} mono onSave={(v) => save({ [k]: v })} />)}

      {/* honesty about the gap between "known here" and "told to the agents" */}
      <Typography sx={{ ...mono, fontSize: 10, letterSpacing: 1, color: FAINT, mt: 3, mb: 1 }}>WHAT THE AGENTS ARE TOLD ABOUT YOU</Typography>
      <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>
        Agents read SOUL.md, where your name and email are filled in as tokens. The lines below are what it currently says about you; edit it on the Docs page.
      </Typography>
      <Box component="pre" sx={{ ...mono, fontSize: 12, whiteSpace: "pre-wrap", color: INK, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 2, p: 1.5, m: 0 }}>
        {p.told_to_agents}
      </Box>
    </Box>
  );
}

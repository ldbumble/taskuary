// YOUR OWN TOOLS THAT SEND (Settings -> Agent permissions, sendfilter.py; the owner, 2026-10-25): agents keep the tools of the owner's own
// MCP servers, minus the ones that send mail, chat or comments, which go through Taskuary and wait for a press. One line per tool left
// out - its server, the tool, why - with a Keep switch; the kept ones fold underneath, each with Leave out. FAIL CLOSED: a tool nobody has
// judged and a server whose tools could not be read are left out, and the line says so. Test it (the one name for asking a
// connection again, buttons.json) lists and judges them anew; the claude.ai connectors are read again only then.
import React, { useEffect, useRef, useState } from "react";
import { Box, Button, FormControlLabel, Switch, Typography } from "@mui/material";
import api from "./api";
import { label } from "./buttons.js";
import { ago } from "./timeWords.js";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";
import { NOT_CHECKED, linesOf } from "./sendFilterLines.js";

function Line({ l, busy, onSet, both }) {
  const k = `${l.server}/${l.tool || "*"}`;
  const why = l.by === "owner" ? (l.blocked ? "You left it out." : "You kept it.") : l.unchecked ? NOT_CHECKED : l.why;
  return (
    <Box data-tq-sendfilter-row={k} data-kept={l.blocked ? undefined : ""}
      sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1, borderBottom: `1px solid ${BORDER}` }}>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography noWrap sx={{ fontSize: 13, color: INK }} title={k}>
          {l.server} · {l.tool || "all its tools"}</Typography>
        <Typography variant="caption" sx={{ color: FAINT, display: "block" }} title={l.unchecked ? l.why : undefined}>
          {why}{both && l.clis.length < 2 ? ` · ${l.clis[0] === "codex" ? "Codex" : "Claude"}` : ""}</Typography>
      </Box>
      {l.blocked
        ? <FormControlLabel label="Keep" labelPlacement="start" sx={{ mr: 0, "& .MuiFormControlLabel-label": { fontSize: 12.5, color: DIM } }}
            title="Agents may use this tool" control={<Switch size="small" checked={false} disabled={busy === k} onChange={() => onSet(l, "keep")} />} />
        : <Button size="small" variant="outlined" disabled={busy === k} onClick={() => onSet(l, "block")} sx={{ color: DIM, borderColor: BORDER }}
            title="Agents no longer get this tool">Leave out</Button>}
    </Box>
  );
}

export default function SendFilter() {
  const [data, setData] = useState(null), [err, setErr] = useState(""), [busy, setBusy] = useState(""), [open, setOpen] = useState(false);
  const timer = useRef(0);
  const load = () => api.get("/api/sendfilter").then(({ data }) => { setData(data); setErr(""); })
    .catch((e) => setErr(e?.response?.data?.detail || "Your MCP tools could not be read - Taskuary did not answer."));
  useEffect(() => { load(); return () => clearTimeout(timer.current); }, []);
  // a scan runs in the background: look again until it has finished, so the lines are the ones it judged
  useEffect(() => { if (data?.scanning) timer.current = setTimeout(load, 3000); }, [data]);
  const set = async (l, verdict) => {
    const k = `${l.server}/${l.tool || "*"}`;
    setBusy(k);
    try { setData((await api.post("/api/sendfilter/correct", { server: l.server, tool: l.tool || "*", verdict })).data); setErr(""); }
    catch (e) { setErr(e?.response?.data?.detail || "That was not saved - try again."); }
    finally { setBusy(""); }
  };
  const again = async () => {
    try { await api.post("/api/sendfilter/scan"); setData((d) => ({ ...d, scanning: true })); setErr(""); }
    catch (e) { setErr(e?.response?.data?.detail || "The check did not start - try again."); }
  };
  if (!data) return err ? <Typography variant="body2" role="alert" sx={{ color: "#a33b3b", py: 1.5 }}>{err}</Typography> : null;
  const { left, kept } = linesOf(data);
  const both = !!(data.claude?.length && data.codex?.length);            // which CLI a line is on, said only when there are two
  if (!left.length && !kept.length) return null;
  const when = data.scanning ? "Checking…" : data.scanned_at ? `Checked ${ago(data.scanned_at * 1000)}` : "Not checked yet";
  return (
    <Box data-tq-sendfilter="" sx={{ py: 1.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 0.5 }}>
        <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5, flex: 1 }}>Your own tools that send</Typography>
        <Typography variant="caption" sx={{ color: FAINT }}>{when}</Typography>
        <Button size="small" disabled={!!data.scanning} onClick={again} sx={{ fontSize: 11.5 }}
          title="Lists your MCP servers and claude.ai connectors again and judges what changed">{label("test_connection")}</Button>
      </Box>
      <Typography variant="body2" sx={{ color: DIM, mb: 0.5 }}>
        Agents keep the tools of your own MCP servers in Claude and Codex, except the ones that send mail, chat or comments. Those are left
        out, and agents send through Taskuary instead, where it waits for your press. Keep one to let agents use it.
      </Typography>
      {left.map((l) => <Line key={`${l.server}/${l.tool}`} l={l} busy={busy} onSet={set} both={both} />)}
      {!left.length && <Typography variant="body2" sx={{ color: DIM, py: 1 }}>No tool is left out.</Typography>}
      {!!kept.length && (
        <>
          <Button size="small" onClick={() => setOpen((o) => !o)} sx={{ mt: 0.5, fontSize: 11.5, color: DIM }} aria-expanded={open}>
            {open ? "▾" : "▸"} Kept for agents ({kept.length})</Button>
          {open && kept.map((l) => <Line key={`${l.server}/${l.tool}`} l={l} busy={busy} onSet={set} both={both} />)}
        </>
      )}
      {err && <Typography variant="body2" role="alert" sx={{ color: "#a33b3b", mt: 1 }}>{err}</Typography>}
    </Box>
  );
}

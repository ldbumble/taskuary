// MEMORY, AS SENTENCES (the owner, 2026-11-06): what Taskuary has learned about how you work, one plain sentence per LEARNED.md line,
// each with Keep / Wrong / Forget (POST /api/learned/mark, memoryedit.mark) - the file stays the store underneath, its tags never shown.
// Under each, faint, when it was learned and from what (memorySentences.provenance). Grouped by subject (learnedGroups.groupLines).
import React, { useCallback, useEffect, useState } from "react";
import { Box, Typography } from "@mui/material";
import api from "./api";
import { BORDER, DIM, FAINT, INK, PANEL, ROLES } from "./theme.jsx";
import { groupLines, marksFor } from "./learnedGroups.js";
import { MarkRow } from "./LearnedView.jsx";
import { provenance, sentence } from "./memorySentences.js";
import ConnectAi from "./ConnectAi.jsx";

export default function MemoryLines() {
  const [g, setG] = useState(null), [err, setErr] = useState("");
  const [busy, setBusy] = useState(""), [said, setSaid] = useState(null);      // said: {key, msg} - why a mark did not take, by its line
  const load = useCallback(async () => {
    try { setG((await api.get("/api/learned/graph")).data); setErr(""); } catch (e) { setErr(e?.response?.data?.detail || "Could not read what was learned"); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const mark = async (key, how) => {
    setBusy(key); setSaid(null);
    try { await api.post("/api/learned/mark", { key, how }); await load(); }
    catch (e) { setSaid({ key, msg: e?.response?.data?.detail || "That did not go through - nothing was changed." }); if (e?.response?.status === 404) await load(); }
    finally { setBusy(""); }
  };
  if (err) return <Typography variant="body2" sx={{ color: ROLES.you.ink, p: 1 }}>{err}</Typography>;
  if (!g) return <Typography variant="caption" sx={{ color: FAINT, p: 1, display: "block" }}>Reading what was learned…</Typography>;
  const groups = groupLines(g).filter((s) => s.lines.length);
  return (
    <Box data-tq-memory="" sx={{ display: "flex", flexDirection: "column", gap: 2, p: 2, bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2 }}>
      {g.ai === false && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }} data-tq-learn-no-ai="">
          <Typography variant="body2" sx={{ fontSize: 12.5, color: INK, flex: 1 }}>Connect an AI to learn how you work. What you write is read either way.</Typography>
          <ConnectAi />
        </Box>
      )}
      <Typography variant="caption" sx={{ color: DIM, lineHeight: 1.5 }}>
        What Taskuary has learned about how you work. Keep makes a line yours, Wrong takes it out for good, Forget takes it out for now.
      </Typography>
      {!groups.length && <Typography variant="body2" sx={{ color: FAINT, fontSize: 13 }}>Nothing learned yet.</Typography>}
      {groups.map((sec) => (
        <Box key={sec.slug} data-tq-memory-section={sec.slug} sx={{ display: "flex", flexDirection: "column" }}>
          <Typography sx={{ fontSize: 12, fontWeight: 600, color: "var(--tq-link, #55697a)", mb: 0.5 }}>{sec.title}</Typography>
          {sec.lines.map((l) => {
            const words = sentence(l.text), from = provenance(l);
            if (!words) return null;
            return (
              <Box key={l.key} data-tq-memory-line={l.key} sx={{ display: "flex", alignItems: "flex-start", gap: 1, py: 0.9, borderTop: `1px solid ${BORDER}` }}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography sx={{ fontSize: 13.5, lineHeight: 1.45, color: INK }}>{words}</Typography>
                  {(from || l.kept) && <Typography sx={{ fontSize: 11, color: FAINT, mt: 0.2 }}>{[from, l.kept && !l.own ? "kept" : ""].filter(Boolean).join(" · ")}</Typography>}
                  {said?.key === l.key && <Typography variant="caption" role="alert" sx={{ color: ROLES.you.ink, display: "block", mt: 0.3 }}>{said.msg}</Typography>}
                </Box>
                <MarkRow marks={marksFor(l)} busy={busy === l.key} onMark={(how) => mark(l.key, how)} />
              </Box>
            );
          })}
        </Box>
      ))}
    </Box>
  );
}

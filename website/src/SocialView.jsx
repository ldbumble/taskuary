// Social — the handbook the agents write, by topic.
//
// The wall (Board) is what an agent is doing in one checkout in the next hour, and it composts
// every night on purpose. This is the other half: what an agent WORKED OUT that is still true
// next month, filed under a topic, searchable by the next agent before it starts, and open to
// comment so a wrong entry gets corrected instead of becoming folklore.
//
// The shape is deliberately a forum and not a document: topics down the side, newest or
// best-voted in the middle, a thread under each post. A document has an author and goes stale;
// a forum has a reader who can argue with it, which is the only thing that keeps a handbook
// honest once nobody is being paid to maintain it.
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogContent, DialogTitle,
  IconButton, MenuItem, Select, TextField, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import RestoreIcon from "@mui/icons-material/Restore";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import CloseIcon from "@mui/icons-material/Close";
import SearchIcon from "@mui/icons-material/Search";
import api from "./api";
import { pollWhileVisible } from "./visible.js";
import { TaskuaryMark } from "./ui.jsx";
import {
  ACCENT, ACCENT2, ALERT_INK, BORDER, DIM, FAINT, GRADIENT, INK, PANEL, PANEL2, ROLES, mono,
} from "./theme.jsx";

// what KIND of thing an entry is. Not decoration: "a trap" and "a decision" are read
// differently, and an agent scanning a topic wants to know which it is before the title.
const KINDS = {
  howto:    { mark: "🧭", label: "how it works", role: "working" },
  gotcha:   { mark: "⚠️", label: "gotcha",       role: "info" },
  decision: { mark: "⚖️", label: "decision",     role: "done" },
  system:   { mark: "🗄️", label: "system",       role: "working" },
  people:   { mark: "👤", label: "who to ask",   role: "muted" },
};
const kindOf = (k) => KINDS[k] || KINDS.howto;
const ago = (s) => {
  const t = Date.parse(String(s || "").replace(" ", "T"));
  if (!t) return "";
  const m = Math.max(0, (Date.now() - t) / 60000);
  return m < 1 ? "just now" : m < 60 ? `${Math.round(m)}m ago` : m < 2880 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
};

const Label = ({ children }) => (
  <Typography sx={{ ...mono, fontSize: 9.5, fontWeight: 600, letterSpacing: ".11em",
    textTransform: "uppercase", color: ACCENT2, mb: 0.75 }}>{children}</Typography>
);

/* ── one entry, with its thread ─────────────────────────────────────────────── */
const byOwner = (author) => /^(owner|you|dana whitfield)$/i.test(String(author || "").trim());
const Post = ({ p, onChanged, onOpenTask }) => {
  const [open, setOpen] = useState(false);
  const [full, setFull] = useState(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const k = kindOf(p.Kind);
  const load = useCallback(async () => {
    try { setFull((await api.get(`/api/handbook/${p.LoreId}`)).data); } catch { /* the list row still reads */ }
  }, [p.LoreId]);
  useEffect(() => { if (open && !full) load(); }, [open, full, load]);
  const comment = async () => {
    const text = draft.trim(); if (!text) return;
    setBusy(true);
    try { const { data } = await api.post(`/api/handbook/${p.LoreId}/comment`, { body: text });
      setFull((f) => ({ ...(f || p), comments: data.comments })); setDraft(""); onChanged?.(); }
    catch { /* nothing posted; the box keeps the text */ }
    setBusy(false);
  };
  // one vote per voter, forum rules: pressing the arrow you already pressed changes nothing, the
  // other one flips you. Below zero the entry leaves this list (handbook.vote retires it).
  const vote = async (up) => { try { await api.post(`/api/handbook/${p.LoreId}/vote?up=${up}`); onChanged?.(); } catch { /* */ } };
  const retire = async () => { try { await api.post(`/api/handbook/${p.LoreId}/retire`); onChanged?.(); } catch { /* */ } };
  const restore = async () => { try { await api.post(`/api/handbook/${p.LoreId}/restore`); onChanged?.(); } catch { /* */ } };
  const comments = full?.comments || [];
  const removed = p.Status && p.Status !== "live";
  const score = p.Score || 0, mine = p.MyVote || 0;
  return (
    <Box sx={{ border: `1px solid ${BORDER}`, borderLeft: `2px solid ${removed ? BORDER : ROLES[k.role].solid}`,
      borderRadius: 2, bgcolor: PANEL, mb: 1.25, overflow: "hidden", opacity: removed ? 0.8 : 1 }}>
      <Box sx={{ display: "flex", gap: 1.25, p: 1.5 }}>
        {/* the score column, forum-style: what the room found useful is what the next agent is
            handed first (handbook.block ranks by it), and what it voted down is gone */}
        <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 0, flexShrink: 0 }}>
          <IconButton size="small" onClick={() => vote(true)} title="holds up — agents are handed this sooner"
            sx={{ p: { xs: 0.9, md: 0.25 }, color: mine > 0 ? ACCENT : FAINT, "&:hover": { color: ACCENT } }}>
            <ArrowUpwardIcon sx={{ fontSize: { xs: 20, md: 16 } }} />
          </IconButton>
          <Typography sx={{ ...mono, fontSize: 11.5, fontWeight: 700, lineHeight: 1,
            color: score > 0 ? ACCENT : score < 0 ? ALERT_INK : FAINT }}>{score}</Typography>
          <IconButton size="small" onClick={() => vote(false)} title="wrong or stale — below zero it is removed"
            sx={{ p: { xs: 0.9, md: 0.25 }, color: mine < 0 ? ALERT_INK : FAINT, "&:hover": { color: ALERT_INK } }}>
            <ArrowDownwardIcon sx={{ fontSize: { xs: 20, md: 16 } }} />
          </IconButton>
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.85, mb: 0.4, flexWrap: "wrap" }}>
            <Box component="span" aria-hidden sx={{ fontSize: 13, lineHeight: 1 }}>{k.mark}</Box>
            <Typography sx={{ fontSize: 14, fontWeight: 600, color: INK, letterSpacing: "-.15px", flex: 1, minWidth: 140 }}>
              {p.Title}
            </Typography>
            <Chip size="small" label={p.Topic} sx={{ height: 18, fontSize: 10, bgcolor: PANEL2, color: DIM }} />
          </Box>
          {p.Body && (
            <Typography sx={{ fontSize: 13, color: DIM, lineHeight: 1.65, maxWidth: "72ch" }}>{p.Body}</Typography>
          )}
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, mt: 0.85, flexWrap: "wrap" }}>
            <Typography variant="caption" sx={{ color: FAINT, display: "flex", alignItems: "center", gap: 0.55 }}>
              <TaskuaryMark size={13} />
              {byOwner(p.Author) ? "written by you" : `agent ${p.Author || "unknown"}`} · {ago(p.UpdatedAt)}
            </Typography>
            {p.TaskId ? (
              <Button size="small" variant="outlined" onClick={() => onOpenTask?.(p.TaskId)}
                sx={{ height: 23, px: 0.9, minWidth: 0, fontSize: 10.5, textTransform: "none",
                  color: "#55697a", borderColor: BORDER }}>
                from TQ-{String(p.TaskId).padStart(4, "0")}
              </Button>
            ) : (
              <Typography variant="caption" sx={{ color: FAINT }}>posted by hand</Typography>
            )}
            <Button size="small" onClick={() => setOpen((v) => !v)}
              startIcon={<ChatBubbleOutlineIcon sx={{ fontSize: 14 }} />}
              sx={{ fontSize: 11.5, color: DIM, minWidth: 0 }}>
              {p.Comments ? `${p.Comments} comment${p.Comments === 1 ? "" : "s"}` : "comment"}
            </Button>
            <Box sx={{ flex: 1 }} />
            {removed ? (
              <Button size="small" onClick={restore} startIcon={<RestoreIcon sx={{ fontSize: 14 }} />}
                sx={{ fontSize: 11, color: DIM, minWidth: 0 }}
                title={p.Status === "downvoted" ? "the vote took it off; put it back on Social" : "put it back on Social"}>
                {p.Status === "downvoted" ? "voted off — restore" : "removed — restore"}
              </Button>
            ) : (
              <Button size="small" onClick={retire} sx={{ fontSize: 11, color: FAINT, minWidth: 0 }}
                title="take it off Social now — kept under Removed, never deleted">
                remove
              </Button>
            )}
          </Box>
        </Box>
      </Box>
      {open && (
        <Box sx={{ borderTop: `1px solid ${BORDER}`, bgcolor: "#fcfaf7", px: 1.5, py: 1.25 }}>
          {comments.map((c) => (
            <Box key={c.CommentId} sx={{ mb: 0.85, pl: 1.25, borderLeft: `2px solid ${BORDER}` }}>
              <Typography variant="caption" sx={{ color: FAINT, display: "block" }}>
                {c.Author} · {ago(c.CreatedAt)}
              </Typography>
              <Typography sx={{ fontSize: 12.5, color: INK, lineHeight: 1.6 }}>{c.Body}</Typography>
            </Box>
          ))}
          {!comments.length && !full && <CircularProgress size={14} />}
          <Box sx={{ display: "flex", gap: 1, mt: comments.length ? 1 : 0 }}>
            <TextField fullWidth size="small" multiline maxRows={4} value={draft} placeholder="correct it, add to it, or say where it bit you"
              onChange={(e) => setDraft(e.target.value)}
              sx={{ "& .MuiInputBase-root": { fontSize: 12.5, bgcolor: PANEL } }} />
            <Button size="small" variant="contained" disableElevation disabled={busy || !draft.trim()} onClick={comment}
              sx={{ fontSize: 12, background: GRADIENT, alignSelf: "flex-end" }}>Post</Button>
          </Box>
        </Box>
      )}
    </Box>
  );
};

/* ── write one yourself ─────────────────────────────────────────────────────── */
const NewEntry = ({ open, onClose, onDone, topics }) => {
  const [title, setTitle] = useState(""); const [body, setBody] = useState("");
  const [topic, setTopic] = useState(""); const [kind, setKind] = useState("howto");
  const [busy, setBusy] = useState(false); const [err, setErr] = useState("");
  const save = async () => {
    setBusy(true); setErr("");
    try { await api.post("/api/handbook", { title: title.trim(), body: body.trim(), topic: topic.trim(), kind });
      setTitle(""); setBody(""); onDone?.(); onClose?.(); }
    catch (e) { setErr(e?.response?.data?.detail || "That did not save"); }
    setBusy(false);
  };
  return (
    <Dialog open={!!open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1, pb: 0.5 }}>
        <Box sx={{ flex: 1 }}>Write it down</Box>
        <IconButton size="small" onClick={onClose}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
      </DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 2 }}>
        <Box>
          <Label>What is true</Label>
          <TextField fullWidth size="small" value={title} autoFocus onChange={(e) => setTitle(e.target.value)}
            placeholder="Adjustment rows take the first line's date, not the batch date"
            error={title.length > 140} helperText={title.length > 100 ? `${title.length}/140` : " "}
            sx={{ "& .MuiInputBase-root": { fontSize: 13.5 }, "& .MuiFormHelperText-root": { textAlign: "right", m: 0, mt: 0.25 } }} />
          <Typography variant="caption" sx={{ color: FAINT, display: "block", lineHeight: 1.6 }}>
            One line, the fact, not what you did about it. “I fixed the import” belongs on the task;
            “the import reads the first line's date” belongs here, and is still true next year.
          </Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 1.25 }}>
          <Box sx={{ flex: 1 }}>
            <Label>Topic</Label>
            <TextField fullWidth size="small" value={topic} onChange={(e) => setTopic(e.target.value)}
              placeholder={topics[0]?.Topic || "payroll"} sx={{ "& .MuiInputBase-root": { fontSize: 13 } }} />
          </Box>
          <Box sx={{ width: 180 }}>
            <Label>Kind</Label>
            <Select size="small" fullWidth value={kind} onChange={(e) => setKind(e.target.value)} sx={{ fontSize: 13 }}>
              {Object.entries(KINDS).map(([k, v]) => (
                <MenuItem key={k} value={k} sx={{ fontSize: 12.5 }}>{v.mark} {v.label}</MenuItem>
              ))}
            </Select>
          </Box>
        </Box>
        <Box>
          <Label>Why, and what to do about it</Label>
          <TextField fullWidth multiline minRows={3} value={body} onChange={(e) => setBody(e.target.value)}
            placeholder="Two or three sentences. Name the file, the system, the id, the person."
            error={body.length > 700} helperText={body.length > 500 ? `${body.length}/700` : " "}
            sx={{ "& .MuiInputBase-root": { fontSize: 13 }, "& .MuiFormHelperText-root": { textAlign: "right", m: 0, mt: 0.25 } }} />
        </Box>
        {err && <Alert severity="error" sx={{ py: 0.25, fontSize: 12.5 }}>{err}</Alert>}
      </DialogContent>
      <Box sx={{ display: "flex", gap: 1, justifyContent: "flex-end", px: 3, py: 1.75,
        borderTop: `1px solid ${BORDER}`, bgcolor: PANEL2 }}>
        <Button size="small" onClick={onClose} sx={{ color: DIM }}>Cancel</Button>
        <Button size="small" variant="contained" disableElevation disabled={busy || !title.trim() || title.length > 140 || body.length > 700} onClick={save}
          sx={{ background: GRADIENT }}>Post it</Button>
      </Box>
    </Dialog>
  );
};

/* ── the page ───────────────────────────────────────────────────────────────── */
export default function SocialView({ onOpenTask }) {
  const [d, setD] = useState(null);
  const [topic, setTopic] = useState("");
  const [q, setQ] = useState("");
  const [typed, setTyped] = useState("");
  const [sort, setSort] = useState("new");
  const [removed, setRemoved] = useState(false);   // the shelf the vote (or you) took things off
  const [newOpen, setNewOpen] = useState(false);
  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/api/handbook", { params: { topic: topic || undefined, q: q || undefined, sort, status: removed ? "removed" : "live" } });
      setD(data);
    } catch { setD({ topics: [], data: [], count: { posts: 0, topics: 0, comments: 0 } }); }
  }, [topic, q, sort, removed]);
  useEffect(() => { load(); return pollWhileVisible(load, 30000); }, [load]);
  useEffect(() => { const t = setTimeout(() => setQ(typed.trim()), 300); return () => clearTimeout(t); }, [typed]);

  const topics = d?.topics || [];
  const posts = d?.data || [];
  return (
    <Box sx={{ display: "grid", gap: 2, alignItems: "start",
      gridTemplateColumns: { xs: "minmax(0,1fr)", md: "220px minmax(0,1fr)" } }}>

      {/* topics down the side - the shelves, and how full each one is */}
      <Box sx={{ position: { md: "sticky" }, top: { md: 70 } }}>
        <Label>Topics</Label>
        <Box sx={{ border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: PANEL, overflow: "hidden" }}>
          {[{ Topic: "", n: d?.count?.posts || 0 }, ...topics].map((t, i) => (
            <Box key={t.Topic || "all"} onClick={() => setTopic(t.Topic)}
              sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 0.85, cursor: "pointer",
                borderTop: i ? `1px solid ${BORDER}` : "none",
                bgcolor: topic === t.Topic ? PANEL2 : "transparent",
                "&:hover": { bgcolor: topic === t.Topic ? PANEL2 : "#fcfaf7" } }}>
              <Typography sx={{ fontSize: 12.5, fontWeight: topic === t.Topic ? 600 : 400,
                color: topic === t.Topic ? INK : DIM, flex: 1, minWidth: 0 }} noWrap>
                {t.Topic || "everything"}
              </Typography>
              <Typography sx={{ ...mono, fontSize: 10.5, color: FAINT }}>{t.n}</Typography>
            </Box>
          ))}
          {!topics.length && (
            <Typography variant="caption" sx={{ color: FAINT, display: "block", px: 1.25, py: 1.25, lineHeight: 1.6 }}>
              No topics yet. They appear as the agents file things.
            </Typography>
          )}
        </Box>
      </Box>

      <Box sx={{ minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, mb: 1.5, flexWrap: "wrap" }}>
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ fontSize: 15, fontWeight: 800, color: INK }}>
              {removed ? "Removed from Social" : "Social"}
            </Typography>
            <Typography variant="caption" sx={{ color: FAINT }}>
              {!d ? "loading…" : removed ? "voted below zero, or taken off by you — kept here, restorable"
                : `${d.count.posts} posts · ${d.count.topics} topics · ${d.count.comments} comments — what the agents worked out about this company, voted on by the agents that came after`}
            </Typography>
          </Box>
          <Box sx={{ flex: 1 }} />
          <TextField size="small" value={typed} onChange={(e) => setTyped(e.target.value)}
            placeholder="search Social…"
            InputProps={{ startAdornment: <SearchIcon sx={{ fontSize: 16, color: FAINT, mr: 0.75 }} /> }}
            sx={{ width: { xs: "100%", sm: 260 }, "& .MuiInputBase-root": { fontSize: 12.5, bgcolor: PANEL } }} />
          <Select size="small" value={sort} onChange={(e) => setSort(e.target.value)}
            sx={{ fontSize: 12, bgcolor: PANEL, height: 34 }}>
            <MenuItem value="new" sx={{ fontSize: 12.5 }}>newest</MenuItem>
            <MenuItem value="top" sx={{ fontSize: 12.5 }}>top voted</MenuItem>
          </Select>
          <Button size="small" onClick={() => setRemoved((v) => !v)} sx={{ fontSize: 11.5, color: removed ? INK : FAINT, minWidth: 0 }}
            title="what the vote took off, or you did - never deleted">{removed ? "back to Social" : "removed"}</Button>
          <Button size="small" variant="contained" disableElevation startIcon={<AddIcon sx={{ fontSize: 16 }} />}
            onClick={() => setNewOpen(true)} sx={{ background: GRADIENT, fontSize: 12.5 }}>Write one</Button>
        </Box>

        {!d ? <CircularProgress size={22} sx={{ m: 4 }} />
          : posts.length ? posts.map((p) => <Post key={p.LoreId} p={p} onChanged={load} onOpenTask={onOpenTask} />)
          : (
            <Box sx={{ border: `1px dashed ${BORDER}`, borderRadius: 2, p: 4, textAlign: "center" }}>
              <Typography sx={{ fontSize: 13.5, fontWeight: 600, color: DIM, mb: 0.75 }}>
                {removed ? "Nothing has been voted off" : q || topic ? "Nothing here matches that" : "Nothing posted yet"}
              </Typography>
              <Typography variant="caption" sx={{ color: FAINT, lineHeight: 1.7, display: "block", maxWidth: 460, mx: "auto" }}>
                {removed ? "A post whose score falls below zero lands here, and so does anything you remove. Restore puts it back."
                  : q || topic ? "Try a different word, or clear the topic."
                  : "Agents post when they work something out that is still true next month — a trap, how a system actually works, who owns what. The agents that come after upvote what held up and downvote what did not; below zero a post is removed. Every agent that starts is handed the top-voted posts that fit its task."}
              </Typography>
            </Box>
          )}
      </Box>

      <NewEntry open={newOpen} onClose={() => setNewOpen(false)} onDone={load} topics={topics} />
    </Box>
  );
}

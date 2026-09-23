// The Assistant Game's item inspector: one thing from the pile, opened in the room it stands in, with
// the same depth the chat's cards give it - the whole message or report, the agent's last words and
// a way to answer them, the draft with a redraft instruction, meeting prep, the fix for a broken
// connection - in the game's own look. Every button is the chat's own road (the same endpoint, the
// same proposal-then-confirm for anything consequential), and the extra words come from the server's
// chips_for via /api/concierge/chips, so an item offers here exactly what it offers in the chat.
import React, { useEffect, useState } from "react";
import { Box, Typography } from "@mui/material";

import api from "./api";
import { mono } from "./theme.jsx";
import { cleanText } from "./ui.jsx";
import { Md, looksMd } from "./md.jsx";
import { RepoPicker } from "./RepoPicker.jsx";
import { cardFor, laneMeta } from "./funnelPile.js";
import { afterExecute, proposalOf } from "./proposalCard.js";
import { needsYou, matchFor, CHIP_MOVE } from "./assistantGame.js";

export const G = { bg: "rgba(20,24,30,.9)", line: "rgba(255,255,255,.1)", ink: "#f3f1ec", dim: "#aeb6bf", faint: "#7c8590",
  gold: "#f0c05a", mint: "#7fd1c6", red: "#e0697d", green: "#8fcf8f", card: "rgba(255,255,255,.05)" };
export const glass = { bgcolor: G.bg, color: G.ink, border: `1px solid ${G.line}`, borderRadius: "14px",
  boxShadow: "0 18px 50px rgba(10,14,20,.35)", backdropFilter: "blur(10px)" };
export const errText = (e) => e?.response?.data?.detail || e?.message || "that did not go through";
const field = { width: "100%", boxSizing: "border-box", bgcolor: "rgba(0,0,0,.25)", color: G.ink, border: `1px solid ${G.line}`,
  borderRadius: "8px", p: 0.9, fontSize: 12.5, fontFamily: "inherit", resize: "vertical" };

export function Btn({ children, onClick, disabled, kind = "ghost", title }) {
  const bg = { gold: G.gold, mint: G.mint, ghost: G.card, red: "rgba(224,105,125,.15)" }[kind];
  return (
    <Box component="button" type="button" onClick={(e) => { e.stopPropagation(); onClick?.(e); }} disabled={disabled} title={title}
      sx={{ border: `1px solid ${kind === "ghost" ? G.line : "transparent"}`, bgcolor: bg, color: kind === "gold" || kind === "mint" ? "#1c1f24" : G.ink,
        borderRadius: "9px", px: 1.1, py: 0.55, fontSize: 11.5, fontWeight: 800, cursor: disabled ? "default" : "pointer", opacity: disabled ? 0.5 : 1,
        "&:hover": { filter: disabled ? "none" : "brightness(1.12)" } }}>{children}</Box>
  );
}
const Row = ({ children }) => <Box sx={{ display: "flex", gap: 0.5, mt: 0.8, flexWrap: "wrap" }} onClick={(e) => e.stopPropagation()}>{children}</Box>;
const Label = ({ children }) => <Typography sx={{ fontSize: 9.5, fontWeight: 800, letterSpacing: 1.1, color: G.faint, mt: 1, mb: 0.4 }}>{children}</Typography>;

// something to read, in a box that caps its height: markdown when it is markdown, text when not
function Reading({ text, cap = 150 }) {
  const [all, setAll] = useState(false);
  if (!text) return null;
  const long = text.length > 420;
  return (
    <Box onClick={(e) => e.stopPropagation()} sx={{ mt: 0.7 }}>
      <Box sx={{ maxHeight: all ? 380 : cap, overflowY: all ? "auto" : "hidden", position: "relative", px: 1, py: 0.8, borderRadius: "8px",
        bgcolor: "rgba(0,0,0,.22)", fontSize: 12.5, lineHeight: 1.55, color: G.ink, whiteSpace: looksMd(text) ? "normal" : "pre-wrap",
        "& a": { color: G.mint }, "& p": { my: 0.5 }, "& table": { fontSize: 11.5 }, "& h1,& h2,& h3": { fontSize: 13.5, my: 0.6 },
        ...(!all && long ? { maskImage: "linear-gradient(#000 70%, transparent)" } : {}) }}>
        {looksMd(text) ? <Md text={text} /> : text}
      </Box>
      {long && <Box component="button" type="button" onClick={() => setAll((v) => !v)}
        sx={{ border: 0, bgcolor: "transparent", color: G.mint, fontSize: 11.5, fontWeight: 700, cursor: "pointer", p: 0, mt: 0.4 }}>
        {all ? "Less" : "Read it all"}</Box>}
    </Box>
  );
}

// what they wrote (ReadText: no chain, signature or banner), the whole email one press away
function MessageText({ mid }) {
  const [doc, setDoc] = useState(null);
  const [whole, setWhole] = useState(false);
  useEffect(() => {
    let live = true;
    if (mid == null || mid === "") { setDoc({}); return () => { live = false; }; }
    api.get(`/api/messages/${mid}`).then(({ data }) => live && setDoc(data || {})).catch((e) => live && setDoc({ error: errText(e) }));
    return () => { live = false; };
  }, [mid]);
  if (!doc) return <Typography sx={{ fontSize: 11.5, color: G.faint, mt: 0.6 }}>opening it…</Typography>;
  if (doc.error) return <Typography sx={{ fontSize: 11.5, color: G.red, mt: 0.6 }}>{doc.error}</Typography>;
  const raw = cleanText(doc.BodyText || ""), read = doc.ReadText != null ? cleanText(doc.ReadText) : raw;
  const body = whole ? raw : read, cut = body.indexOf("\n--- raw data ---");
  return <>
    <Reading text={(cut >= 0 ? body.slice(0, cut) : body).trim() || "(empty)"} />
    {read !== raw && <Box component="button" type="button" onClick={(e) => { e.stopPropagation(); setWhole((v) => !v); }}
      sx={{ border: 0, bgcolor: "transparent", color: G.faint, fontSize: 11, cursor: "pointer", p: 0, mt: 0.3 }}>
      {whole ? "Just what they wrote" : "Show the whole email"}</Box>}
    {doc.SourceLink && <Box component="a" href={doc.SourceLink} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
      sx={{ display: "block", fontSize: 11, color: G.mint, mt: 0.3 }}>open the original ↗</Box>}
  </>;
}

// the agent's own last words (the question it is parked on lives there), fetched from the worker
function AgentSaid({ tid }) {
  const [said, setSaid] = useState(null);
  useEffect(() => {
    let live = true;
    api.get(`/api/tasks/${tid}/worker`).then(({ data }) => live && setSaid(String(data?.said || "").trim())).catch(() => live && setSaid(""));
    return () => { live = false; };
  }, [tid]);
  return said ? <><Label>WHAT IT SAID LAST</Label><Reading text={said} cap={120} /></> : null;
}

// an agent's filed report, from the task's comments - what it found, in its own words
function FinalReport({ tid }) {
  const [text, setText] = useState(null);
  useEffect(() => {
    let live = true;
    api.get(`/api/tasks/${tid}`).then(({ data }) => {
      const rep = (data?.comments || []).slice().reverse().find((c) => /^(CODER REPORT|HANDOVER NOTE)/.test(String(c.Body || "")));
      if (live) setText(rep ? rep.Body.replace(/^(CODER REPORT|HANDOVER NOTE)\s*/, "") : "No report was filed on this task.");
    }).catch((e) => live && setText(errText(e)));
    return () => { live = false; };
  }, [tid]);
  return text == null ? null : <><Label>ITS FINAL REPORT</Label><Reading text={text} /></>;
}

// the draft behind "reply ready": edit it, send it, or tell the assistant how to rewrite it
function Draft({ item, busy, play }) {
  const [rv, setRv] = useState(null);
  const [text, setText] = useState(null);
  const [how, setHow] = useState("");
  const [err, setErr] = useState("");
  const load = () => api.get("/api/reviews", { params: { status: "pending" } })
    .then(({ data }) => setRv((data.data || []).find((x) => x.ReviewId === item.rid) || { gone: true })).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, [item.rid]);
  if (!rv) return <Typography sx={{ fontSize: 11.5, color: G.faint, mt: 0.6 }}>fetching the draft…</Typography>;
  if (rv.gone) return <Typography sx={{ fontSize: 11.5, color: G.faint, mt: 0.6 }}>Already handled - nothing is waiting here.</Typography>;
  const action = rv.Kind === "action";
  const parsed = () => { try { const p = JSON.parse(rv.DraftText || ""); return p.text || `${p.action}${p.why ? ` — ${p.why}` : ""}`; } catch { return rv.DraftText || ""; } };
  const value = text ?? (action ? parsed() : rv.DraftText || "");
  const who = rv.FromName || rv.FromEmail || "them";
  const send = () => play("approve", item.key, async () => {
    const { data } = await api.post(`/api/reviews/${item.rid}/decide`, { verb: "approve", final_text: action ? null : value, note: null });
    if (data?.send_error) throw new Error(data.send_error);
    return data;
  });
  const redraft = async () => {
    const out = await play("draft", null, async () => (await api.post(`/api/messages/${item.mid}/reply`,
      { draft: true, redraft: true, instruction: how.trim() || null })).data);
    if (out) { setHow(""); setText(null); if (out.draft) setRv((r) => ({ ...r, DraftText: out.draft, Stale: false })); else load(); }
  };
  return (
    <Box onClick={(e) => e.stopPropagation()}>
      <Label>{action ? "WHAT THE AGENT WANTS TO DO" : `THE DRAFT TO ${who.toUpperCase()} - EDIT, THEN SEND`}</Label>
      <Box component="textarea" rows={5} value={value} readOnly={action} onChange={(e) => setText(e.target.value)}
        placeholder="No draft yet - rewrite it below, or type your own" sx={field} />
      {(rv.Stale ?? item.stale) && <Typography sx={{ fontSize: 11.5, color: G.gold, mt: 0.4 }}>New messages came in after this draft - rewrite it before sending.</Typography>}
      <Row>
        <Btn kind="gold" disabled={!!busy || (!action && !value.trim())} onClick={send} title={action ? "Runs what the agent proposed" : `Sends it to ${who}`}>
          {action ? "▶ Run it · +40" : "📨 Send it · +40"}</Btn>
      </Row>
      {!action && item.mid && <>
        <Box sx={{ display: "flex", gap: 0.5, mt: 0.8 }}>
          <Box component="input" value={how} onChange={(e) => setHow(e.target.value)} placeholder="Rewrite it… (shorter, warmer, say no)"
            onKeyDown={(e) => { if (e.key === "Enter") redraft(); }} sx={{ ...field, py: 0.6 }} />
          <Btn disabled={!!busy} onClick={redraft} title="The assistant rewrites the draft - nothing is sent">✍ Redraft</Btn>
        </Box>
      </>}
      {err && <Typography sx={{ fontSize: 11.5, color: G.red, mt: 0.5 }}>{err}</Typography>}
    </Box>
  );
}

// the extra words: the chat's own vocabulary for this item, each run the chat's way (a proposal you confirm).
// `given` is a set the Core's answer already carried; `initial` a proposal it already made.
export function Moves({ item, covers = [], busy, play, onRepo, given = null, initial = null }) {
  const [chips, setChips] = useState(given);
  const [prop, setProp] = useState(initial);
  useEffect(() => {
    if (given) return undefined;
    let live = true;
    api.get("/api/concierge/chips", { params: { key: item.key } }).then(({ data }) => live && setChips(data.chips || [])).catch(() => live && setChips([]));
    return () => { live = false; };
  }, [item.key, given]);
  const run = async (p) => {
    const out = await play(CHIP_MOVE[p.verb] || "done", item.key, async () => {
      let res;
      try { res = (await api.post(`/api/operations/${p.id}/execute`, { version: p.version })).data; }
      catch (e) { res = { status: e?.response?.status === 409 ? "stale" : "error", error: errText(e) }; }
      const done = afterExecute(p, res);
      if (done.repo) onRepo?.(done.repo);
      if (done.status !== "done") throw new Error(done.receipt);
      return done;
    });
    setProp(null);
    return out;
  };
  const pick = async (c) => {
    // the words that are the page's own actions rather than proposals - exactly as the chat runs them
    if (c.ask) return null;
    if (c.verb === "followup") return play("followup", item.key, () => api.post("/api/concierge/act", { key: item.key, verb: "followup" }));
    if ((c.verb === "reply" || c.verb === "redraft") && item.mid)
      return play("draft", null, () => api.post(`/api/messages/${item.mid}/reply`, { draft: true, redraft: c.verb === "redraft", instruction: null }));
    if (c.verb === "prep" && item.event)
      return play("prep", item.key, () => api.post("/api/calendar/prep", { ...item.event, instruction: "Get me ready for this meeting: who is in it, what came before it, what I should say." }));
    const p = await play(null, null, async () => (await api.post("/api/concierge/propose", { verb: c.verb, key: item.key, table: true })).data);
    if (!p) return null;
    const got = proposalOf({ proposal: p }) || p;
    if (got.auto) return run({ ...got, verb: c.verb });
    setProp({ ...got, verb: c.verb });
    return null;
  };
  const shown = (chips || []).filter((c) => c.verb !== "next" && !covers.includes(c.verb));
  if (!shown.length && !prop) return null;
  return (
    <Box onClick={(e) => e.stopPropagation()}>
      <Label>MORE MOVES</Label>
      <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
        {shown.map((c) => <Btn key={c.verb} disabled={!!busy || !!prop} onClick={() => pick(c)} title={c.hint}>{c.label}</Btn>)}
      </Box>
      {prop && (
        <Box sx={{ mt: 0.8, p: 1, borderRadius: "9px", border: `1px dashed ${G.gold}`, bgcolor: "rgba(240,192,90,.07)" }}>
          <Typography sx={{ fontSize: 12, color: G.ink }}>{prop.say || prop.label}</Typography>
          <Row>
            <Btn kind="gold" disabled={!!busy} onClick={() => run(prop)}>Confirm - {prop.label}</Btn>
            <Btn onClick={() => { api.delete(`/api/operations/${prop.id}`).catch(() => {}); setProp(null); }}>Cancel</Btn>
          </Row>
        </Box>
      )}
    </Box>
  );
}

export function Who({ item }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.7 }}>
      <Typography noWrap sx={{ fontSize: 11, fontWeight: 800, color: G.dim }}>{item.who || "—"}</Typography>
      {item.channel && <Typography sx={{ fontSize: 10, color: G.faint }}>· {item.channel}</Typography>}
      {item.ref && <Typography sx={{ ...mono, fontSize: 10, color: G.faint }}>{item.ref}</Typography>}
      <Typography sx={{ fontSize: 10, fontWeight: 800, color: needsYou(item) ? G.red : G.faint, ml: "auto", letterSpacing: 0.5, whiteSpace: "nowrap" }}>{laneMeta(item.lane).word}</Typography>
    </Box>
  );
}

// ONE item, opened: what it is, what to read, and every move it carries
export function ItemInspector({ item, agents, busy, play, onOpenTask, onNavigate, onNext }) {
  const [answer, setAnswer] = useState("");
  const [mine, setMine] = useState(null);           // "write it myself": the text you will send instead of a draft
  const [repo, setRepo] = useState(null);
  const card = cardFor(item) || "message", m = matchFor(item, agents);
  const coding = item.coding || item.kind === "coding" || m.kind === "coding";
  const dispatch = (kind) => play("dispatch", item.key, async () => {
    const { data } = await api.post(`/api/messages/${item.mid}/dispatch`, { kind });
    if (data?.dispatch === "needs_repo") { setRepo({ taskId: data.taskId, agent: data.agent || "coder" }); throw new Error("pick the repository it works in first"); }
    return data;
  });
  const sendMine = () => play("approve", item.key, async () => {
    const { data } = await api.post(`/api/messages/${item.mid}/reply`, { draft: true, instruction: null });
    if (!data?.reviewId) throw new Error("no draft slot came back - try Draft a reply");
    const sent = (await api.post(`/api/reviews/${data.reviewId}/decide`, { verb: "approve", final_text: mine, note: null })).data;
    if (sent?.send_error) throw new Error(sent.send_error);
    return sent;
  });
  const tell = () => play("answer", item.key, () => api.post(`/api/tasks/${item.tid}/waitroom`, { text: answer })).then((ok) => ok && setAnswer(""));
  const open = (tid) => onOpenTask?.(tid, { start: false });

  let body = null, covers = [];
  if (item.kind === "connection") {
    body = <>
      {item.why && <Reading text={item.why} cap={80} />}
      <Row><Btn kind="gold" onClick={() => { window.location.hash = `connector=${item.channel}`; onNavigate?.("Connections"); }}>🔌 Open the connection</Btn></Row>
      <Typography sx={{ fontSize: 11, color: G.faint, mt: 0.5 }}>Once it answers again this clears by itself.</Typography>
    </>;
  } else if (card === "reply") {
    covers = ["approve", "redraft"];
    body = <>{item.mid && <MessageText mid={item.mid} />}<Draft item={item} busy={busy} play={play} /></>;
  } else if (card === "agent") {
    covers = ["answer_agent"];
    const working = item.lane === "working";
    body = <>
      <Typography sx={{ fontSize: 12, color: G.dim, mt: 0.5 }}>{item.paused ? "Saved when Taskuary stopped - ready to pick up where it was."
        : working ? "Back at it - nothing for you until it stops." : item.why}</Typography>
      {item.tid && !working && <AgentSaid tid={item.tid} />}
      {!item.paused && !!item.request_id && (item.choices || []).length > 0 && <>
        <Label>ITS QUESTION - PICK ONE</Label>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }} onClick={(e) => e.stopPropagation()}>
          {item.choices.map((c) => <Btn key={c} kind="mint" disabled={!!busy}
            onClick={() => play("answer", item.key, () => api.post(`/api/tasks/${item.tid}/worker/answer`, { request_id: item.request_id, text: c }))}>{c} · +60</Btn>)}
        </Box>
      </>}
      {!item.paused && !working && item.tid && <Box sx={{ display: "flex", gap: 0.5, mt: 0.8 }} onClick={(e) => e.stopPropagation()}>
        <Box component="input" value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder={item.asking ? "Or answer in your own words…" : "Tell it what to do next…"}
          onKeyDown={(e) => { if (e.key === "Enter" && answer.trim()) tell(); }} sx={{ ...field, py: 0.6 }} />
        <Btn kind="gold" disabled={!!busy || !answer.trim()} onClick={tell}>Answer · +60</Btn>
      </Box>}
      <Row>
        {item.paused && <Btn kind="gold" disabled={!!busy} onClick={() => play("resume", item.key, () => api.post(`/api/tasks/${item.tid}/resume`)).then((ok) => ok && open(item.tid))}>▶ Continue this session · +15</Btn>}
        {item.tid && <Btn onClick={() => open(item.tid)}>⌨ Jump into the code space</Btn>}
      </Row>
    </>;
  } else if (card === "meeting") {
    const e = item.event || {};
    covers = ["prep"];
    body = <>
      <Typography sx={{ fontSize: 12, color: G.dim, mt: 0.5 }}>{[e.start && `starts ${String(e.start).slice(11, 16)}`, e.who?.length && `with ${e.who.slice(0, 6).join(", ")}`, e.where].filter(Boolean).join(" · ")}</Typography>
      {e.about && <Reading text={e.about} cap={90} />}
      <Row>
        <Btn kind="gold" disabled={!!busy} onClick={() => play("prep", item.key, async () => {
          const { data } = await api.post("/api/calendar/prep", { ...e, instruction: "Get me ready for this meeting: who is in it, what came before it, what I should say." });
          if (data?.taskId) open(data.taskId);
          return data;
        })}>🎯 Prep me · +20</Btn>
        {e.join && <Box component="a" href={e.join} target="_blank" rel="noreferrer" onClick={(ev) => ev.stopPropagation()}
          sx={{ px: 1.1, py: 0.55, borderRadius: "9px", bgcolor: G.mint, color: "#1c1f24", fontSize: 11.5, fontWeight: 800, textDecoration: "none" }}>Join ↗</Box>}
      </Row>
    </>;
  } else if (card === "report") {
    body = <>{item.bad && <Typography sx={{ fontSize: 12, color: G.red, mt: 0.5 }}>The run failed - the cause is in the report.</Typography>}{item.mid && <MessageText mid={item.mid} />}</>;
  } else if (card === "agentdone" || card === "wrapup") {
    covers = card === "agentdone" && item.mid ? ["reply"] : [];
    body = <>
      {item.sent && <Reading text={`You sent: ${item.sent}`} cap={80} />}
      {item.summary && <Reading text={item.summary} cap={100} />}
      {item.tid && <FinalReport tid={item.tid} />}
      <Row>
        {card === "agentdone" && item.mid && <Btn kind="gold" disabled={!!busy} onClick={() => play("draft", item.key, () => api.post(`/api/messages/${item.mid}/reply`, { draft: true, instruction: null }))}
          title="Drafts an answer to the sender from what the agent found - nothing is sent">✍ Reply from this · +20</Btn>}
        {item.tid && <Btn onClick={() => open(item.tid)}>Open {item.ref}</Btn>}
      </Row>
    </>;
  } else if (card === "fyis") {
    covers = ["done"];
    body = <>
      {(item.items || []).map((x) => <Typography key={x.key} sx={{ fontSize: 12, color: G.dim, mt: 0.4 }}>• <b style={{ color: G.ink }}>{x.who}</b> - {x.title}{x.summary ? ` - ${x.summary}` : ""}</Typography>)}
      <Row><Btn kind="mint" disabled={!!busy} onClick={() => play("read", item.key, () => api.post("/api/funnel/settle", { key: item.key, verb: "done" }))}>☕ All read · +8</Btn></Row>
    </>;
  } else if (card === "idea") {
    covers = [];
    body = <>{item.why && <Reading text={item.why} cap={90} />}{item.mid && <MessageText mid={item.mid} />}</>;
  } else {
    // a person wrote something (asked / on your list / fyi / triage failed), or a task on you
    const asks = item.kind !== "fyi" && item.lane !== "fyi";
    covers = ["reply", "coder", "regular_agent"];
    body = <>
      {item.mid ? <MessageText mid={item.mid} /> : item.preview && <Reading text={item.preview} cap={90} />}
      {item.lane === "unjudged" && <Row><Btn kind="gold" disabled={!!busy} onClick={() => play("sort", item.key, () => api.post(`/api/messages/${item.mid}/retriage`, {}))}>🔁 Try triage again · +10</Btn></Row>}
      {asks && item.mid && <Row>
        <Btn kind={m.verb === "draft" ? "gold" : "ghost"} disabled={!!busy} onClick={() => play("draft", item.key, () => api.post(`/api/messages/${item.mid}/reply`, { draft: true, instruction: null }))}>✍ Draft a reply · +20</Btn>
        <Btn kind={m.verb === "dispatch" ? "gold" : "ghost"} disabled={!!busy} onClick={() => dispatch(coding ? "coding" : "general")}>🤖 Hand to {coding ? "a coding agent" : "an agent"} · +45</Btn>
        <Btn disabled={!!busy} onClick={() => setMine((v) => v == null ? "" : null)}>✎ Write it myself</Btn>
      </Row>}
      {mine != null && <Box onClick={(e) => e.stopPropagation()}>
        <Box component="textarea" rows={4} value={mine} onChange={(e) => setMine(e.target.value)} placeholder="Your reply, sent as you write it" sx={{ ...field, mt: 0.8 }} />
        <Row><Btn kind="gold" disabled={!!busy || !mine.trim()} onClick={sendMine}>📨 Send mine · +40</Btn></Row>
      </Box>}
      {!item.mid && item.tid && <Row><Btn onClick={() => open(item.tid)}>Open {item.ref}</Btn></Row>}
    </>;
  }
  return (
    <Box>
      {body}
      {repo && <Box onClick={(e) => e.stopPropagation()} sx={{ mt: 1, p: 1, borderRadius: "9px", bgcolor: "#f6f2ea", color: "#262521" }}>
        <Typography sx={{ fontSize: 12, fontWeight: 700, mb: 0.5 }}>Which repository should the coding agent use?</Typography>
        <RepoPicker taskId={repo.taskId} agent={repo.agent} onDone={(d) => { if (d?.repo) { setRepo(null); dispatch("coding"); } }} />
      </Box>}
      <Moves item={item} covers={covers} busy={busy} play={play} onRepo={setRepo} />
      <Row>
        {/* Next, as in the chat: it is read, and the next thing comes up - reading what only wanted knowing scores */}
        {onNext && <Btn kind="mint" disabled={!!busy} onClick={() => onNext(item)} title="Read - on to the next thing (N)">
          Next ▶ · +{(item.lane === "fyi" || item.lane === "report" || item.kind === "fyis") && !item.bad ? 8 : 2}</Btn>}
        <Btn disabled={!!busy} onClick={() => play("later", item.key, () => api.post("/api/funnel/settle", { key: item.key, verb: "later" }))}>⏭ Later</Btn>
        {item.tid && card !== "agent" && card !== "agentdone" && card !== "wrapup" && item.mid && <Btn onClick={() => open(item.tid)}>Open {item.ref}</Btn>}
      </Row>
    </Box>
  );
}

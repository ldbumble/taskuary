// ONE CARD FOR EVERY ACT A CONNECTOR DECLARES (the owner, 2026-11-05: "each connector should have settings what the action view looks like
// no?"): the agent's run_tool on a tool the catalogue gives an action view (taskuary/connectorcatalog.json `actions`, read by actionCard.js) -
// a LinkedIn post with its picture, who sees it and post now or save as a draft; a Bluesky or Mastodon post; a comment on a tracker item;
// a new GitHub issue - its repository, title and labels, its words editable, Create issue (2026-11-06). Its
// words are editable while it waits, its choices too where declared, pre-filled from the connection's defaults (Connections). The press is the
// one decide road every proposal takes (/api/reviews/{id}/decide, verdicts.decide -> proposals.execute): nothing goes before it. Live for as
// long as it waits, on the turn that set it up - a line typed after it left it read-only with no way to send. Once it went it says so, with the link.
import React, { useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import api from "./api.js";
import { openAppLink } from "./appLinks.js";
import { attUrl } from "./fileSave.js";
import { FileDialog } from "./PublishedPages.jsx";
import { actionFor, changed, choiceOf, faceOf, fieldsOf, pressable, stateOf, textKey, valuesOf, viaBrowserSaid, wordsOf } from "./actionCard.js";
import { outputRow } from "./taskOutputs.js";
import { hint, label as btn } from "./buttons.js";
import { failLine, landed, press } from "./press.js";
import { asLive, MovedPast } from "./PassedCard.jsx";
import { MdLine } from "./md.jsx";
import { ACCENT, ALERT_INK, BORDER, DIM, FAINT, INK } from "./theme.jsx";

// ...a post's picture is a preview at a glance, not half the screen (the owner, 2026-11-05): its press opens it whole (FileDialog)
const IMG_MAX = 180;
// ...as wide as the pick it shows, its chevron beside it - sized to its longest choice, "Anyone" stood a word's gap from its own arrow - and
// a ring when the keyboard is on it (the scenario run, 2026-11-06: no outline at all)
const PICK = { font: "inherit", fontSize: 11.5, color: INK, border: 0, background: "transparent", padding: 0, cursor: "pointer", outline: 0,
  fieldSizing: "content", borderRadius: "4px", "&:focus-visible": { outline: `2px solid ${ACCENT}`, outlineOffset: 1 } };

// `past`: the chat moved past it - drawn as it stood while it waited, its buttons greyed (MovedPast)
export default function ActionCard({ row: was, tid, live = true, onChanged, past = false }) {
  const given = past ? asLive(was) : was;
  // ...A PRESS ANSWERED IS THE CARD'S STATE AT ONCE (the card round, 2026-11-18: Dismiss lit Post and Dismiss again for a beat before "dismissed",
  // a failed post lit them again before its error was kept - the press was over, the row it reads not yet read again): the status the server
  // answered with stands over a row that still says pending, until that row says it too
  const [settled, setSettled] = useState(null);
  // ...one answered elsewhere (`already`: another window, the phone) holds greyed instead, until the row says what that press did - its words
  // are not this card's to say (the card round, 2026-11-18: this window's unsent edit was said as posted)
  const answered = !!settled && given?.Status === "pending", row = answered && settled.mine ? { ...given, Status: settled.Status, ActError: settled.ActError || given.ActError } : given;
  const held = answered && !settled.mine ? "held" : "";
  const p = row?.post || {}, act = actionFor(p.type), st = stateOf(row, live), tk = textKey(act);
  const [text, setText] = useState(String(p[tk] || "")), [vals, setVals] = useState(() => valuesOf(act, p)), [copied, setCopied] = useState(false);
  const [pressing, setBusy] = useState(""), [err, setErr] = useState(""), [viewing, setViewing] = useState(null);
  // ...gone by THIS card's press: said in the words of what he picked ("Saved as a draft"), with its link, until the row says what went. One
  // gone from another window (`already`) is never said in this window's words: that edit was not what went (the card round, 2026-11-18)
  const done = answered && settled.mine && ["approved", "edited"].includes(settled.Status) ? settled : null;
  const busy = pressing || held;
  if (!act) return null;
  // ...and gone by it, it reads what he pressed - his words, his picks - not the proposal's until the row comes back with them (a landed draft
  // said "Post now" over the agent's words for a beat, then "Save as draft" over his: the card round, 2026-11-18)
  const shown = done ? { ...p, ...vals, [tk]: text } : p;
  const fields = fieldsOf(act, shown, !!st.live && !done), post = act.kind === "post", w = wordsOf(act, done || st.live ? vals : p);
  // ...EVERY POST CARRIES ITS PICTURE (the owner, 2026-11-20): one its network takes no upload for is shown all the same, to save and add by hand
  const img = fields.find((f) => f.type === "image" && f.value) || (p.image ? { key: "image", value: p.image, manual: true } : null);
  const pic = img ? outputRow(tid ?? row?.TaskId, img.value) : null;
  const max = fields.find((f) => f.key === tk)?.max, over = max && text.length > max;
  const go = done?.url || st.url, gone = !!done || st.done;
  // ...a press that failed before this card was drawn is still said on it: the review keeps it (store.review_act_failed), not the press
  const failed = err || (!busy && !gone && ["pending", "superseded"].includes(row?.Status) && row?.ActError) || "";
  const decide = async (verb) => {
    setBusy(verb); setErr("");
    // ...the one press (press.js): it said "nothing was posted. Try again" after two minutes with no answer, over a post still going up;
    // and one decided in another window was an error on a card that only had to read itself again
    const o = await press(api, row.ReviewId, { verb, final_text: verb === "approve" ? text : null,
      ...(verb === "approve" && Object.keys(changed(act, p, vals)).length ? { fields: changed(act, p, vals) } : {}) }, 2);
    const line = landed(o) || o.kind === "already" ? "" : failLine(o, post ? "posted" : "sent"), status = o.data?.status;
    if (status && status !== "pending") setSettled({ Status: status, ActError: line, url: o.data.result?.url || "", mine: o.kind !== "already" });
    else setErr(line);
    if (o.kind !== "error") onChanged?.();
    setBusy("");
  };
  const viaBrowser = async () => {
    setBusy("browser"); setErr("");
    try { const { data } = await api.post(`/api/reviews/${row.ReviewId}/via-browser`, { final_text: text });
      if (data?.ok) setSettled({ Status: data.status || "approved", mine: true, browser: true }); else setErr(data?.why || "It could not be handed over.");
      onChanged?.(); }
    catch (e) { setErr(e?.response?.data?.detail || e?.message || "It could not be handed over."); }
    setBusy("");
  };
  // ...a choice reads as its label; while it waits, the label is the pick itself - no box around it
  const choice = (f) => f.editable
    ? <Box component="select" key={f.key} data-tq-act-choice={f.key} aria-label={f.label} value={String(vals[f.key])} disabled={!!busy}
        onChange={(e) => setVals((v) => ({ ...v, [f.key]: e.target.value }))} sx={PICK}>
        {f.choices.map((c) => <option key={String(c.value)} value={String(c.value)}>{c.label}</option>)}</Box>
    : <span key={f.key} data-tq-act-choice={f.key}>{choiceOf(f, f.value)?.label || String(f.value)}</span>;
  const meta = [row?.network, ...fields.filter((f) => f.type === "choice").map(choice)].filter(Boolean);
  // ...a `heading` line is the act's own title, drawn bold over its words (a GitHub issue's title), never "Title ..." in the header
  const lines = fields.filter((f) => f.type === "line" && f.value && !f.heading), heads = fields.filter((f) => f.heading && f.value);
  return (<MovedPast on={past}>
    <Box data-tq-act={row?.ReviewId} data-tq-act-kind={act.kind} data-tq-act-state={gone ? "done" : st.live ? "waiting" : "not-done"}
      sx={{ mt: 1, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: "var(--tq-panel, #fff)", overflow: "hidden" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.5, pt: 1.25, pb: 0.75 }}>
        {post && <Box aria-hidden sx={{ width: 34, height: 34, borderRadius: "50%", bgcolor: "var(--tq-inset, #dfe6ec)", color: "var(--tq-link, #55697a)", display: "grid", placeItems: "center", fontWeight: 700, fontSize: 13 }}>
          {faceOf(row)}</Box>}
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontSize: 13.5, fontWeight: 700, color: INK, lineHeight: 1.2 }}>
            {post ? row?.as || `Your ${row?.network || ""} account` : lines.map((f) => `${f.label} ${f.value}`).join(" · ") || row?.network}</Typography>
          <Typography component="div" sx={{ fontSize: 11.5, color: FAINT }}>{meta.map((m, i) => <React.Fragment key={i}>{i ? " · " : ""}{m}</React.Fragment>)}</Typography>
        </Box>
      </Box>
      {post && lines.map((f) => <Typography key={f.key} sx={{ px: 1.5, fontSize: 12, color: DIM }}>{f.label}: {f.value}</Typography>)}
      {heads.map((f) => <Typography key={f.key} data-tq-act-heading={f.key} sx={{ px: 1.5, pt: 0.25, fontSize: 14, fontWeight: 700, color: INK, overflowWrap: "anywhere" }}>{f.value}</Typography>)}
      {st.live && !gone
        ? <Box component="textarea" data-tq-act-text="" value={text} onChange={(e) => setText(e.target.value)} disabled={!!busy} rows={Math.min(14, Math.max(3, text.split("\n").length + 1))}
            sx={{ display: "block", width: "100%", boxSizing: "border-box", resize: "vertical", border: 0, outline: 0, px: 1.5, py: 0.5, font: "inherit", fontSize: 13.5, lineHeight: 1.5, color: INK, bgcolor: "transparent" }} />
        : <Typography data-tq-act-text="" sx={{ px: 1.5, py: 0.5, fontSize: 13.5, lineHeight: 1.5, color: gone ? INK : DIM, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{shown[tk]}</Typography>}
      {pic && <Box component="img" data-tq-act-image={img.value} src={attUrl(pic)} alt={p.alt || pic.name} onClick={() => setViewing(pic)}
        sx={{ display: "block", width: "100%", height: IMG_MAX, objectFit: "contain",   /* its room from the first frame: a picture landing grew the card 2 -> 180 px (2026-11-12) */ bgcolor: "var(--tq-canvas, #f6f4f1)", mt: 0.75, cursor: "zoom-in", borderTop: `1px solid ${BORDER}`, borderBottom: `1px solid ${BORDER}` }} />}
      {pic && img.manual && !gone && <Typography data-tq-act-image-manual="" sx={{ px: 1.5, pt: 0.5, fontSize: 11.5, color: FAINT }}>
        {`${row?.network || "This network"} gets the words from here - open the picture to save it, and add it yourself`}</Typography>}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.5, py: 1, flexWrap: "wrap" }}>
        {gone ? <Typography data-tq-act-done="" sx={{ fontSize: 13, color: "var(--tq-success, #47654a)", fontWeight: 600 }}>✓ {done ? (done.browser ? viaBrowserSaid(row?.network) : w.done) : st.said}
          {go && <> · <a href={go} target="_blank" rel="noopener noreferrer" style={{ color: "var(--tq-link, #55697a)" }}>See it on {row?.network}<OpenInNewIcon sx={{ fontSize: 12, ml: 0.25, verticalAlign: "-1px" }} /></a></>}</Typography>
          : st.live && row?.connect ? <>
            {/* ...a post on a network not connected goes up through the agent's browser at his press (the owner, 2026-11-22: "card first, sign-in
                at the press"); Connect beside it opens that card instead (outbound.connect_fix, 2026-11-08) */}
            {post && <Button size="small" variant="contained" disableElevation data-tq-act-browser="" disabled={!!busy || !text.trim() || !!over} onClick={viaBrowser}
              startIcon={busy === "browser" ? <CircularProgress size={12} color="inherit" /> : null}>{busy === "browser" ? "Handing it over…" : "Post via the browser"}</Button>}
            <Button size="small" variant={post ? "text" : "contained"} disableElevation data-tq-act-connect="" onClick={() => openAppLink(row.connect.href)}>{row.connect.label}</Button>
            {/* ...and the draft copy-ready beside it: never a press that can only fail (the judge's look, 2026-11-20) */}
            <Button size="small" data-tq-act-copy="" disabled={!text.trim()} title={hint("copy")}
              onClick={() => { try { navigator.clipboard?.writeText(text); setCopied(true); } catch { /* the words stay on the card */ } }}>
              {copied ? `✓ ${btn("copy", "done") || "Copied"}` : btn("copy")}</Button>
            {/* ...and its Dismiss, as every card has (walk 8, 2026-11-20: a Connect card had none, and the cards queued behind it never came) */}
            <Button size="small" disabled={!!busy} onClick={() => decide("reject")} data-tq-act-dismiss="">Dismiss</Button>
            {/* ...a post's line says the press above it, never "copy it to post it yourself" under Post via the browser (the goal walk, 2026-11-22) */}
            <Typography data-tq-not-connected="" sx={{ fontSize: 11.5, color: FAINT }}>{row.connect.says}{post ? ` - Post via the browser has the agent put it up there, and its last Post waits for you`
              : row.connect.waits ? ` - ${row.connect.waits}` : ""}</Typography></>
          : st.live ? <>
            <Button size="small" variant="contained" disableElevation data-tq-act-press="" disabled={!!busy || !pressable(act, p, text) || !!over} onClick={() => decide("approve")}
              title={act.note || hint("approve", post ? "post" : "action")} startIcon={busy === "approve" ? <CircularProgress size={12} color="inherit" /> : null}>
              {busy === "approve" ? w.busy : w.press}</Button>
            <Button size="small" disabled={!!busy} onClick={() => decide("reject")} data-tq-act-dismiss="">Dismiss</Button>
            {/* ...its note ("Nothing is posted until you press it") is the button's hover, not a grey line under every card (the owner, 2026-11-09) */}
            {over && <Typography sx={{ fontSize: 11.5, color: ALERT_INK }}>{text.length} of {max} characters</Typography>}</>
          : <Typography sx={{ fontSize: 12.5, color: FAINT }}>{st.said}</Typography>}
      </Box>
      {/* ...with the way past it pressable (connectorcatalog.not_signed_in: "[open its card](#connector=linkedin)") - design round 6, D8 */}
      {failed && <Typography role="alert" sx={{ px: 1.5, pb: 1, fontSize: 12.5, color: ALERT_INK }}><MdLine text={failed} /></Typography>}
      <FileDialog file={viewing} onClose={() => setViewing(null)} />
    </Box></MovedPast>
  );
}

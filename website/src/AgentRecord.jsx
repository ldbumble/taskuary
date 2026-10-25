// THE AGENT WORK CARD: everything a session did and thought, in one shape for every CLI and the general agent (the owner,
// 2026-10-10: "make sure the agent work section carries enough info to let user know everything the agent did and thought
// about. You can do short the long version with more button maybe but make sure it's full and complete record but don't
// duplicate sections"). In reading order (the owner, 2026-10-10): what happened - with what it decided and changed, and
// the pages it made - and behind ONE More its last message, the files it saved in the project, the run's timeline, every step
// (told, thought, tool, said) and earlier sessions.
import React, { useEffect, useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api";
import { Md } from "./md.jsx";
import PublishedPages from "./PublishedPages.jsx";
import { BORDER, DIM, FAINT, INK, PANEL, PANEL2, mono } from "./theme.jsx";
import { cardParts, hasMore, lastWords, moreParts, plain, recordFacts, recordHead, recordSteps, resultParts, runCost, runsOf, sourceLabel, splitFiles } from "./agentRecord.js";
import AgentStory, { StoryLine, Timeline } from "./AgentStory.jsx";
import { plural } from "./timeWords.js";

const head = { fontSize: 11, fontWeight: 600, color: FAINT, letterSpacing: ".04em", textTransform: "uppercase", mb: 0.35 };

const link = { fontSize: 11, minHeight: 0, p: 0, minWidth: 0 };

const Step = ({ s }) => {
  const [open, setOpen] = useState(false);
  if (s.k === "tool") return (
    <Box>
      <Box onClick={s.detail ? () => setOpen(!open) : undefined} title={s.detail || s.text}
        sx={{ display: "flex", gap: 1, ...mono, fontSize: 11.5, color: DIM, minWidth: 0, cursor: s.detail ? "pointer" : "default" }}>
        <Box component="span" sx={{ color: INK, fontWeight: 600, flexShrink: 0 }}>{s.name}</Box>
        <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", ...(s.detail ? { fontFamily: "inherit" } : {}) }}>
          {s.text}{s.detail && <Box component="span" sx={{ color: FAINT }}>{open ? " ▾" : " ▸"}</Box>}</Box>
      </Box>
      {open && s.detail && <Box sx={{ ...mono, fontSize: 11, whiteSpace: "pre-wrap", overflowWrap: "anywhere", bgcolor: PANEL2, p: 0.75, borderRadius: 1, mt: 0.3, color: INK }}>{s.detail}</Box>}
    </Box>);
  if (s.k === "plan") return (
    <Box sx={{ fontSize: 12, color: DIM }}>
      <Box component="span" sx={{ fontWeight: 600 }}>Plan</Box>
      {s.items.map((i, n) => <Box key={n} sx={{ pl: 1 }}>{i.status === "completed" ? "✓" : i.status === "in_progress" ? "▸" : "○"} {i.text}</Box>)}
    </Box>);
  if (s.k === "result") return <Typography sx={{ fontSize: 12, color: FAINT, fontStyle: "italic" }}>Its answer — shown above.</Typography>;
  if (s.k === "error") return <Typography sx={{ fontSize: 12, color: "#8a3646" }}>⚠ {s.text}</Typography>;
  if (s.k === "gap") return <Typography sx={{ fontSize: 11.5, color: FAINT }}>… {s.text}</Typography>;
  if (s.k === "screen") return (
    <Box sx={{ ...mono, fontSize: 11, whiteSpace: "pre-wrap", bgcolor: PANEL2, p: 1, borderRadius: 1, maxHeight: 420, overflow: "auto", color: INK }}>{s.text}</Box>);
  // told / thought / said: a label, the words folded to a few lines until clicked
  const label = { you: "Told", thought: "Thought", said: "Said" }[s.k] || s.k;
  const long = s.text.length > 320;
  return (
    <Box sx={{ display: "flex", gap: 1, fontSize: 12.5, minWidth: 0 }}>
      <Typography sx={{ fontSize: 11, fontWeight: 600, color: FAINT, width: 52, flexShrink: 0, pt: "2px" }}>{label}</Typography>
      <Box onClick={long ? () => setOpen(!open) : undefined} sx={{ flex: 1, minWidth: 0, cursor: long ? "pointer" : "default",
        color: s.k === "thought" ? DIM : INK, fontStyle: s.k === "thought" ? "italic" : "normal",
        ...(long && !open ? { maxHeight: 64, overflow: "hidden", maskImage: "linear-gradient(#000 55%, transparent)" } : {}) }}>
        {s.k === "said" ? <Md text={s.text} /> : <Box sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{s.text}</Box>}
      </Box>
    </Box>);
};

// its plan and every step, the one part kept behind a button
const Steps = ({ s }) => {
  const steps = recordSteps(s);
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.2 }}>
      {!!s.plan?.length && <Box><Typography sx={head}>Its plan</Typography><Step s={{ k: "plan", items: s.plan }} /></Box>}
      {!!s.refused?.length && <Box><Typography sx={head}>Refused by the floor</Typography>
        {s.refused.map((r, i) => <Typography key={i} sx={{ fontSize: 12, color: DIM, overflowWrap: "anywhere" }}>{r.text}</Typography>)}</Box>}
      {!!steps.length && <Box sx={{ display: "flex", flexDirection: "column", gap: 0.6, maxHeight: 640, overflow: "auto", pr: 0.5 }}>
        {steps.map((x, i) => <Step key={i} s={x} />)}
      </Box>}
    </Box>);
};

const sec = { mt: 1.1, pt: 1, borderTop: `1px solid ${BORDER}` };
const rowsSx = { display: "grid", gridTemplateColumns: "72px minmax(0, 1fr)", columnGap: 1.25, rowGap: 0.6, mt: 0.9, fontSize: 12.5, lineHeight: 1.45,
  color: DIM, overflowWrap: "anywhere", "& > :nth-of-type(odd)": { color: FAINT, fontSize: 11, pt: "1px" } };

// one session, in reading order: what happened, then ONE More for everything else - its last message in full, what it saved,
// the run's timeline, what ended it since, every step, earlier sessions (the owner, 2026-10-12: "main summary, then details
// behind more"). It was what happened + a folded last message + files + its own "Every step" button, under a second section
// that told the same run again.
export const SessionRecord = ({ s, pages = [], draft = "", startOpen = false, timeline = [], since = null, earlier = [], inChat = false }) => {
  const [more, setMore] = useState(startOpen);
  const { lead, rows, message, isReply } = cardParts(s, draft), { mine, other } = splitFiles(s.files, s.cwd);
  const parts = moreParts(s, { draft, timeline, since, earlier: earlier.length });
  return (
    <Box>
      <Typography sx={{ fontSize: 11.5, color: FAINT, mb: 0.5 }}>{recordFacts(s).join(" · ")}</Typography>
      {inChat ? null : lead ? <Box><Typography sx={head}>What happened</Typography><Box sx={{ fontSize: 14, lineHeight: 1.45, color: INK }}><Md text={lead} /></Box></Box>
        : <Typography sx={{ fontSize: 12.5, color: DIM }}>It ended without a written result{parts.length ? " - More has what it did." : "."}</Typography>}
      {!!rows.length && <Box sx={rowsSx}>{rows.map(([k, v]) => <React.Fragment key={k}><Box>{k}</Box><Box><Md text={v} /></Box></React.Fragment>)}</Box>}
      {/* what it made to be LOOKED AT belongs with what happened (the owner, 2026-10-10: "it's important to see it") */}
      {!!pages.length && <Box sx={{ mt: 0.9 }}><PublishedPages pages={pages} /></Box>}
      {!!parts.length && <Box sx={sec}>
        <Button size="small" sx={{ ...link, textAlign: "left" }} onClick={() => setMore(!more)}>More · {parts.join(", ")} {more ? "▾" : "▸"}</Button>
        {more && <Box sx={{ display: "flex", flexDirection: "column", gap: 1.3, mt: 1 }}>
          {message && <Box>
            <Typography sx={head}>Its last message{isReply && <Box component="span" sx={{ textTransform: "none", fontWeight: 400 }}> · the reply it drafted, also in Close out</Box>}</Typography>
            <Box sx={{ fontSize: 13, color: INK }}><Md text={message} /></Box>
          </Box>}
          {s.files?.length > 0 && <Box>
            <Typography sx={head}>Files it saved</Typography>
            {mine.map((f) => <Typography key={f} noWrap title={f} sx={{ ...mono, fontSize: 11.5, color: INK }}>{f}</Typography>)}
            {!!other.length && <Typography title={other.join("\n")} sx={{ fontSize: 12, color: FAINT, mt: mine.length ? 0.4 : 0 }}>
              {mine.length ? "and " : ""}{plural(other.length, "scratch file")} it used while working</Typography>}
          </Box>}
          {!!timeline.length && <Box><Typography sx={head}>The run</Typography><Timeline steps={timeline} /></Box>}
          {/* what ended it upstream (a merge, a close) - ADDED to what the agent did, never in its place (the owner, 2026-10-12) */}
          {since?.text && <Box>
            <Typography sx={head}>Since then{since.at && <Box component="span" sx={{ textTransform: "none", fontWeight: 400 }}> · {String(since.at).slice(0, 16)}</Box>}</Typography>
            <Typography sx={{ fontSize: 12.5, color: INK }}>{since.text}</Typography>
          </Box>}
          {hasMore(s) && <Box>
            <Typography sx={head}>{s.source === "conversation" ? "The working behind its answers" : "Every step"}
              {s.source && <Box component="span" sx={{ textTransform: "none", fontWeight: 400 }}> · from {sourceLabel(s.source)}</Box>}</Typography>
            <Steps s={s} />
          </Box>}
          {!!earlier.length && <Box>
            <Typography sx={head}>Earlier sessions · {earlier.length}</Typography>
            {earlier.map((x) => <Earlier key={x.sid} s={x} />)}
          </Box>}
        </Box>}
      </Box>}
    </Box>);
};

// THE ONE BLOCK on the Agent work step for a session that is not running: the state in a sentence (`story`, from
// funnel.agent_story: ended by you, cut off by a restart, stopped), what happened, and More. With no record to show it is the
// story alone.
// `result`: the agent has stopped and saved, and the work column shows its RESULT (the redesign, owner-approved 2026-10-21) - what it
// found, how it resolved it, its write-up whole, what it made, and the session as one "Replay the session" line. `diff`: the run's own
// diff counted (agentRecord.diffStat), where a run kept one.
// `onDiff`: the run's diff is folded on the page, and the stat line opens it (`diffOpen`, TaskPage)
export const AgentRecord = ({ taskId, pages = [], draft = "", stamp, story = null, folded = false, inChat = false, result = false, diff = null, diffOpen = false, onDiff = null }) => {
  const [rec, setRec] = useState(null);
  useEffect(() => {
    let live = true;
    api.get(`/api/tasks/${taskId}/record`).then(({ data }) => live && setRec(data)).catch(() => live && setRec({ sessions: [] }));
    return () => { live = false; };
  }, [taskId, stamp]);
  // ...and the files it made for the task (outputs.py) - the chat lists them under its answers; a result lists them with its work
  // (null until read, and on a failed read: the result shows what it has, never "no files" it could not know)
  const [outputs, setOutputs] = useState(null);
  useEffect(() => {
    if (!result || inChat) { setOutputs(null); return undefined; }
    let live = true;
    api.get(`/api/task-outputs/${taskId}`).then(({ data }) => live && setOutputs(data?.data || null)).catch(() => live && setOutputs(null));
    return () => { live = false; };
  }, [taskId, stamp, result, inChat]);
  const [now, ...before] = rec?.sessions || [];
  // FOLDED, the step is its state and what happened, two lines - the rest is the open step's (storyPlace)
  if (folded) {
    const lead = now ? plain(cardParts(now, draft).lead) : "";
    return story ? <Box sx={{ mt: 1, pl: { xs: 0, sm: 4 } }}>
      <StoryLine kind={story.kind} line={story.line} />
      {lead && <Typography sx={{ mt: 0.4, pl: 3, fontSize: 13, lineHeight: 1.45, color: DIM, overflow: "hidden",
        display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>{lead}</Typography>}
    </Box> : null;
  }
  if (!rec) return <CircularProgress size={12} />;
  if (!now && !pages.length) return story ? <AgentStory story={story} /> : null;
  const { state, since } = recordHead(story, rec.ended);
  // the run's last words stand in for a session whose own log kept none; a conversation's answers are the chat under the card,
  // so there it is only the working behind them (a card over the chat said the answer a second time)
  const chat = inChat && now?.source === "conversation";
  const s = chat ? { ...now, result: "", report: {} } : now && !String(now.result || "").trim() && story?.said ? { ...now, result: story.said } : now;
  if (chat && !state && !pages.length && !moreParts(s, { earlier: before.length }).length) return null;
  return (
    <Box sx={{ width: "100%", bgcolor: PANEL, px: 1.35, py: 1.15, border: `1px solid ${BORDER}`, borderRadius: 1.5 }}>
      {state && <Box sx={{ mb: 1, pb: 1, borderBottom: `1px solid ${BORDER}` }}><StoryLine kind={state.kind} line={state.line} /></Box>}
      {s && !chat && result ? <ResultView s={s} before={before} pages={[...pages, ...(outputs || [])]} diff={diff} since={since} draft={draft} story={story} diffOpen={diffOpen} onDiff={onDiff} />
        : s && !chat ? <RunSummaries sessions={[s, ...before]} pages={pages}
          full={<SessionRecord s={s} draft={draft} startOpen timeline={story?.steps || []} since={since} earlier={before} />} />
        : s ? <SessionRecord s={s} pages={pages} draft={draft} timeline={story?.steps || []} since={since} earlier={before} inChat={chat} />
        : <PublishedPages pages={pages} />}
    </Box>);
};

// THE RESULT (the redesign, owner-approved 2026-10-21): the write-up's own parts, each only where it recorded one - what it found, how
// it resolved it, the summary and its last words whole - then what it made (the files it saved, the pages and files it made for the
// task, the run's diff counted), and the terminal as ONE line that replays the session step by step. Never the raw log on top.
const ResultView = ({ s, before, pages, diff, since, draft, story, diffOpen = false, onDiff = null }) => {
  const [replay, setReplay] = useState(false);
  const { rows, summary, writeup } = resultParts(s), { mine } = splitFiles(s.files, s.cwd);
  const made = !!(mine.length || pages.length || diff);
  return (
    <Box data-tq-result="" sx={{ display: "flex", flexDirection: "column", gap: 1.1 }}>
      {!rows.length && !summary && !writeup && <Typography sx={{ fontSize: 12.5, color: DIM }}>It ended without a written result - the replay has what it did.</Typography>}
      {rows.map(([k, v]) => <Box key={k} data-tq-result-part={k}><Typography sx={head}>{k}</Typography><Box sx={{ fontSize: 13.5, lineHeight: 1.5, color: INK }}><Md text={v} /></Box></Box>)}
      {summary && <Box data-tq-result-part="Summary"><Typography sx={head}>Summary</Typography><Box sx={{ fontSize: 13.5, lineHeight: 1.5, color: INK }}><Md text={summary} /></Box></Box>}
      {writeup && <Box data-tq-result-part="write-up"><Typography sx={head}>{rows.length || summary ? "Its write-up" : "What it did"}</Typography>
        <Box sx={{ fontSize: 13.5, lineHeight: 1.5, color: INK }}><Md text={writeup} /></Box></Box>}
      {made && <Box data-tq-result-files="" sx={sec}>
        <Typography sx={head}>What it made</Typography>
        {diff && <Typography data-tq-diff-stat="" sx={{ ...mono, fontSize: 11.5, color: DIM, mb: 0.4 }}>
          {plural(diff.files, "file")} changed <Box component="span" sx={{ color: "#47654a" }}>+{diff.added}</Box> <Box component="span" sx={{ color: "#6b2733" }}>−{diff.removed}</Box>
          {onDiff && <Box component="span" data-tq-diff-toggle="">{" · "}<Button size="small" aria-expanded={diffOpen} onClick={onDiff}
            sx={{ ...link, fontSize: 11.5, verticalAlign: "baseline", textTransform: "none" }}>{diffOpen ? "Hide diff" : "Show diff"}</Button></Box>}</Typography>}
        {mine.map((f) => <Typography key={f} noWrap title={f} sx={{ ...mono, fontSize: 11.5, color: INK }}>{f}</Typography>)}
        {!!pages.length && <Box sx={{ mt: mine.length || diff ? 0.75 : 0 }}><PublishedPages pages={pages} /></Box>}
      </Box>}
      {since?.text && <Box sx={sec}><Typography sx={head}>Since then</Typography><Typography sx={{ fontSize: 12.5, color: INK }}>{since.text}</Typography></Box>}
      <Box sx={sec}>
        <Button size="small" data-tq-replay="" aria-expanded={replay} sx={{ ...link, textAlign: "left" }} onClick={() => setReplay(!replay)}>
          {replay ? "▾" : "▶"} Replay the session{before.length ? ` · ${before.length + 1} runs` : ""}{s.at ? ` · ${String(s.at).slice(11, 16)}` : ""}
          {runCost(s).map((x) => ` · ${x}`).join("")}</Button>
        {replay && <Box sx={{ mt: 1 }}><SessionRecord s={s} draft={draft} startOpen timeline={story?.steps || []} earlier={before} /></Box>}
      </Box>
    </Box>);
};

// EVERY RUN BY ITS LAST WORDS (the owner, 2026-10-15: "you don't see the last message from the agent from prior runs ... it should
// summary from run 1|2|3 ... the step by step thing should be hidden behind clear door of full script"): newest first, each run's
// last message; what happened, files, the timeline and every step - the run's record as it was - behind one Full transcript.
const RunSummaries = ({ sessions, pages, full }) => {
  const [open, setOpen] = useState(false);
  const runs = runsOf(sessions);
  return (
    <Box>
      {runs.map(({ s, n, said }, i) => (
        <Box key={s.sid || n} sx={i ? { mt: 1.1, pt: 1, borderTop: `1px solid ${BORDER}` } : undefined}>
          <Typography sx={head}>Run {n}{i === 0 && runs.length > 1 ? " · latest" : ""}
            <Box component="span" sx={{ textTransform: "none", fontWeight: 400 }}> · {recordFacts(s).slice(0, 2).join(" · ")}</Box></Typography>
          {said ? <Box sx={{ fontSize: 13.5, lineHeight: 1.5, color: INK }}><Md text={said} /></Box>
            : <Typography sx={{ fontSize: 12.5, color: DIM }}>It ended without a written result.</Typography>}
        </Box>))}
      {!!pages.length && <Box sx={{ mt: 1 }}><PublishedPages pages={pages} /></Box>}
      <Box sx={{ mt: 1.1, pt: 1, borderTop: `1px solid ${BORDER}` }}>
        <Button size="small" sx={{ ...link, textAlign: "left" }} onClick={() => setOpen(!open)}>Full transcript {open ? "▾" : "▸"}</Button>
        {open && <Box sx={{ mt: 1 }}>{full}</Box>}
      </Box>
    </Box>);
};

const Earlier = ({ s }) => {
  const [open, setOpen] = useState(false);
  const line = plain(String(s.result || "").split(/\n\s*\n/)[0]);
  return (
    <Box sx={{ py: 0.5, borderBottom: `1px dashed ${BORDER}`, "&:last-of-type": { borderBottom: 0 } }}>
      <Box onClick={() => setOpen(!open)} sx={{ display: "flex", gap: 1, cursor: "pointer", fontSize: 12.5, minWidth: 0 }}>
        <Box component="span" sx={{ color: FAINT, width: 12 }}>{open ? "▾" : "▸"}</Box>
        <Box component="span" sx={{ color: DIM, flexShrink: 0 }}>{s.cli || s.by} · {String(s.at || "").slice(0, 16)}</Box>
        {!open && <Box component="span" sx={{ color: INK, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{line || "no written result"}</Box>}
      </Box>
      {open && <Box sx={{ pl: 2.5, pt: 0.5 }}><SessionRecord s={s} /></Box>}
    </Box>);
};

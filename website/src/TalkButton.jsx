// THE TALK BUTTON (live interaction, liveTalk.js): beside a task's box, and on New. One press starts a live voice session with the task's
// agent, the next stops it; while it runs the button says whether it listens, thinks or speaks. A start that cannot happen says why, once,
// with the way to Connections.
import React, { useEffect, useState } from "react";
import { Tooltip } from "@mui/material";
import GraphicEqIcon from "@mui/icons-material/GraphicEq";
import * as live from "./liveTalk.js";

const SAYS = { off: "Talk", connecting: "Starting…", listening: "Listening", thinking: "Thinking…", speaking: "Speaking" };

export default function TalkButton({ taskId = null, onNew = null }) {
  const [s, setS] = useState(live.snapshot());
  useEffect(() => live.watch(setS), []);
  // ...a session begun on New goes on with the task New just opened
  useEffect(() => { if (taskId && s.waiting && s.state !== "off") live.bind(taskId); }, [taskId, s.waiting, s.state]);
  const mine = s.state !== "off" && (s.tid === taskId || (!taskId && !s.tid) || (s.waiting && !!taskId));
  const busy = s.state !== "off" && !mine;
  const title = busy ? "A live session is talking on another task - stop it there first"
    : mine ? "Stop talking - the agent keeps working" : s.why ? `${s.why}` : "Talk with this task's agent out loud";
  return <><Tooltip title={title}><span>
    <button type="button" className="tq-aui-talk" data-tq-talk={mine ? s.state : "off"} aria-pressed={mine} disabled={busy}
      onClick={() => (mine ? live.stop() : live.start({ taskId, onNew }))}
      style={{ display: "inline-flex", alignItems: "center", gap: 4, height: 30, padding: "0 9px", borderRadius: 15, cursor: busy ? "default" : "pointer",
        border: "1px solid var(--tq-edge-brass, #ddd2b9)", font: "inherit", fontSize: 12.5, whiteSpace: "nowrap",
        background: mine ? (s.state === "speaking" ? "#47654a" : "#55697a") : "var(--tq-panel, #fffdfb)",
        color: mine ? "#fff" : "var(--tq-warning, #6b5f45)", opacity: busy ? 0.5 : 1 }}>
      <GraphicEqIcon sx={{ fontSize: 16 }} />
      {mine ? SAYS[s.state] || "Talk" : "Talk"}
    </button></span></Tooltip>
    {/* ...a start that could not happen says why, in one line by the button, until the next press */}
    {!mine && !busy && !!s.why && <span role="alert" data-tq-talk-why="" title={s.why}
      style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 11.5, color: "var(--tq-danger, #8a3646)" }}>{s.why}</span>}</>;
}

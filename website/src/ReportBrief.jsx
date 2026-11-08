// A BRIEF ON THE TABLE (the owner, 2026-11-07, of the End of day checkup: "This is terrible"): its two roll-ups first, side by side on a
// white card - what got done, what is next - then each group of bullets on a card of its own, one row per item: the source's mark, who
// it is and what it is about, and the gist under it. A meeting says so in words; done and next are what the group's own title says.
// The shape is read by reportBrief.js; a report without it stays markdown (assistantCards FullText).
import React from "react";
import "./dashboard/dashboard.css";
import "./reportRows.css";
import EventIcon from "@mui/icons-material/Event";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import TerminalIcon from "@mui/icons-material/Terminal";
import { MdLine } from "./md.jsx";
import { Attachments } from "./Attachments.jsx";
import { ChannelIcon } from "./ui.jsx";

// the source's mark (evening.py: channels.CH_ICON, a task's 📌, an agent's 🤖) drawn as the rail draws that source; one it does not
// know stays as written
const CH = { "✉": "email", "👥": "teams", "🔧": "github", "📋": "asana", "🚨": "sentry", "📌": "assistant" }, ICON = { fontSize: 16, color: "#6e685f" };
const Mark = ({ m }) => {
  const k = m.replace(/\uFE0F/g, "");
  return k === "🗓" ? <EventIcon sx={ICON} /> : k === "💬" ? <ChatBubbleOutlineIcon sx={ICON} /> : k === "🤖" ? <TerminalIcon sx={ICON} />
    : CH[k] ? <ChannelIcon channel={CH[k]} sx={{ fontSize: 16 }} /> : m;
};

export default function ReportBrief({ brief, mid }) {
  const { notes, rollups, groups, closing } = brief;
  return (
    <div className="tq-dash tq-brief" data-tq-report-brief="">
      {notes.map((n, i) => <p key={i} className="tq-brief-note" role="note">{n}</p>)}
      <section className="tq-brief-sum" aria-label="Summary">
        {rollups.map(([k, v]) => <div key={k}><h3>{k}</h3><p><MdLine text={v} /></p></div>)}
      </section>
      <div className="tq-brief-groups">
        {groups.map((g, gi) => (
          <section key={gi} className="tq-brief-group" aria-label={g.title || undefined}>
            {g.title && <header><h3>{g.title}</h3><span>{g.items.length}</span></header>}
            <ul>{g.items.map((it, i) => (
              <li key={i}>
                <span className="src" aria-hidden="true">{it.src && <Mark m={it.src} />}</span>
                <div className="body">
                  <div className="line">
                    {it.who && <b><MdLine text={it.who} /></b>}
                    {it.what && <span className="what"><MdLine text={it.what} /></span>}
                    {it.status.includes("meeting") && <span className="tag">Meeting</span>}
                  </div>
                  {it.gist && <div className="gist"><MdLine text={it.gist} /></div>}
                </div>
              </li>))}</ul>
          </section>
        ))}
      </div>
      {closing.length > 0 && <p className="tq-brief-close">{closing.join(" ")}</p>}
      {mid != null && <Attachments messageId={mid} dense />}
    </div>
  );
}

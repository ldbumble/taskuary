// Markdown, rendered. An agent-written report arrives as markdown - headings, a table of repos,
// bold star counts - and showing the SOURCE of that made a 106-line report unreadable. Report
// bodies only: an email that happens to contain an asterisk is not a document.
import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Box } from "@mui/material";
import { BORDER, DIM, INK, PANEL, mono } from "./theme.jsx";

// what an emoji-sectioned digest does NOT have: markdown headings, tables, bold, list markers
export const looksMd = (s) => /^#{1,6} |^\s*\|.*\|\s*$|\*\*[^*]+\*\*|^\s*[-*] |^\s*\d+\. /m.test(String(s || ""));

const TASK_LINK = /#task=(\d+)/;
const A = ({ href, children }) => {
  const m = TASK_LINK.exec(href || "");
  return (
    <a href={href} target={m ? undefined : "_blank"} rel="noreferrer" style={{ color: "#55697a", fontWeight: 600, textDecoration: "none" }}
      onClick={(e) => { if (m) { e.preventDefault(); window.location.hash = `task=${m[1]}`; } }}>
      {m ? `open TQ-${String(m[1]).padStart(4, "0")} →` : children}
    </a>
  );
};

const sx = {
  textAlign: "left", color: INK, fontSize: 13.5, lineHeight: 1.55,
  "& h1, & h2, & h3, & h4": { fontWeight: 700, color: INK, lineHeight: 1.3, mt: 1.4, mb: 0.5 },
  "& h1": { fontSize: 17 }, "& h2": { fontSize: 15, pb: 0.35, borderBottom: `1px solid ${BORDER}` }, "& h3, & h4": { fontSize: 13.5 },
  "& p": { m: 0, mb: 0.75 }, "& ul, & ol": { m: 0, mb: 0.75, pl: 2.5 }, "& li": { mb: 0.25 },
  "& code": { ...mono, fontSize: 12, bgcolor: PANEL, px: 0.5, borderRadius: 0.5 },
  "& pre": { ...mono, fontSize: 12, bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 1, p: 1, overflowX: "auto" },
  "& pre code": { bgcolor: "transparent", p: 0 },
  "& blockquote": { m: 0, mb: 0.75, pl: 1.25, borderLeft: `3px solid ${BORDER}`, color: DIM },
  "& hr": { border: 0, borderTop: `1px solid ${BORDER}`, my: 1 },
  // a wide table scrolls inside its own box; the panel never grows sideways
  "& .tbl": { overflowX: "auto", mb: 0.75 },
  "& table": { borderCollapse: "collapse", fontSize: 12.5, minWidth: "100%" },
  "& th, & td": { border: `1px solid ${BORDER}`, px: 0.9, py: 0.45, textAlign: "left", verticalAlign: "top" },
  "& th": { bgcolor: PANEL, fontWeight: 700, whiteSpace: "nowrap" },
  "& > :first-of-type": { mt: 0 }, "& > :last-child": { mb: 0 },
};

export const Md = ({ text }) => (
  <Box sx={sx}>
    <ReactMarkdown remarkPlugins={[remarkGfm]}
      components={{ a: A, table: ({ children }) => <div className="tbl"><table>{children}</table></div> }}>
      {String(text || "")}
    </ReactMarkdown>
  </Box>
);

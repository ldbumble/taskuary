// BROWSING THE APP IN THE CANVAS (the canvas redesign, docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md):
// Connections, Settings, Reports and Hub are walked by clicks that never wait on a model. One pattern for all four:
//   1. SECTIONS - the sidebar button posts a card of section chips;
//   2. THE LIST - a chip shows that section's cards in a grid;
//   3. ONE - a card hides the rest of its list and opens its real detail in place, with today's controls; Back returns.
// Each view keeps its own data and its own controls - it is handed a `browse` render prop and draws its groups, cards and
// detail through BrowseFrame instead of its tab's rail. Every step is client state: nothing above it in the scroll
// changes, and nothing asks the server for the rail. The open card is the conversation's subject (onOpenCard, in words).
import React, { Suspense, useEffect, useRef } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";
import ArrowBackIosNewIcon from "@mui/icons-material/ArrowBackIosNew";
import { BORDER, DIM, FAINT, INK, PANEL } from "./theme.jsx";
import ConnectorsView from "./ConnectorsView.jsx";
import ReportsView from "./ReportsView.jsx";
import SettingsView from "./SettingsView.jsx";
import NewSheet from "./NewSheet.jsx";
const HubView = React.lazy(() => import("./HubView.jsx"));

const chipSx = (on) => ({ height: 30, px: 1.6, borderRadius: 99, border: `1px solid ${on ? "#55697a" : BORDER}`, cursor: "pointer",
  bgcolor: on ? "#55697a" : PANEL, color: on ? "#fff" : "#4d4a43", fontFamily: "inherit", fontSize: 12, fontWeight: 600, whiteSpace: "nowrap" });

// The frame every area draws through. sections: [{key, label, n}]; cards: [{key, title, sub, badge, icon, onOpen}];
// detail: the view's own element for the one open card, or null. `openLabel` names the open card for the assistant.
export function BrowseFrame({ title, summary, sections = [], section, onSection, note, cards = [], detail = null, onBack,
  openLabel = "", search = null, tools = null, onOpenCard, live = true, empty = "Nothing here.", onReopen = null, wide = false }) {
  // ...and a page with nothing opened on it still says WHERE the owner is: a question typed over the Connections wall went to the
  // assistant with no context at all, and "which AI agent tool do I need for this thing to work" was answered about the app in
  // general (the owner, 2026-10-01: "the open field should be the top of query ... that is current context")
  const sectionLabel = sections.find((s) => s.key === section)?.label || "";
  const where = `the ${title} page${sectionLabel ? `, ${sectionLabel} section` : ""} - nothing opened on it yet`;
  useEffect(() => { if (live) onOpenCard?.(detail ? openLabel : where); }, [live, detail, openLabel, where, onOpenCard]);
  // a card opened, or a section picked, is brought into view - the conversation above it does not move
  const root = useRef(null), one = useRef(null);
  const opened = !!detail;
  useEffect(() => { if (live && opened) one.current?.scrollIntoView({ block: "start", behavior: "smooth" }); }, [live, opened, openLabel]);
  useEffect(() => { if (live && section != null) root.current?.scrollIntoView({ block: "start", behavior: "smooth" }); }, [live, section]);
  // an earlier browse card is one line, and clicking it browses there again (a new card, at the bottom)
  if (!live) return (
    <button type="button" className="tq-fold" onClick={onReopen || undefined} title={`Browse ${title} again`}>
      <b>{title}</b><span className="grow" /><span className="again">open again</span>
    </button>
  );
  return (
    <Box ref={root} sx={{ display: "flex", flexDirection: "column", gap: 1.25, scrollMarginTop: "8px" }}>
      {/* 1. sections */}
      <Box sx={{ border: `1px solid ${BORDER}`, borderRadius: "12px", bgcolor: PANEL, px: 2, py: 1.75 }}>
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.25, flexWrap: "wrap" }}>
          <Typography sx={{ fontSize: 14, fontWeight: 700, color: INK }}>{title}</Typography>
          {!!summary && <Typography sx={{ fontSize: 12, color: DIM }}>{summary}</Typography>}
        </Box>
        {search}
        {/* what the tab offered beside its list - Run due now, Write one, the filters: the tab is gone, so it is here */}
        {tools}
        {/* a note with no list under it yet (a link to something that is gone) is said here, where it is seen */}
        {!!note && section == null && <Typography sx={{ mt: 1.25, fontSize: 12.5, color: "#7a2f3c", lineHeight: 1.5 }}>{note}</Typography>}
        {!!sections.length && (
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mt: 1.5 }}>
            {sections.map((s) => (
              <Box key={s.key} component="button" type="button" data-tq-browse-chip={s.key} aria-pressed={section === s.key}
                onClick={() => onSection(s.key)} sx={chipSx(section === s.key)}>
                {s.label}{s.n != null ? ` · ${s.n}` : ""}
              </Box>
            ))}
          </Box>
        )}
      </Box>

      {/* 3. one - the view's own detail, in place of its list */}
      {detail && (
        <Box ref={one} data-tq-browse-one="" sx={{ scrollMarginTop: "8px", border: `1px solid ${BORDER}`, borderRadius: "12px", bgcolor: PANEL, overflow: "hidden" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, px: 1.75, py: 1.1, borderBottom: `1px solid ${BORDER}` }}>
            <Box component="button" type="button" data-tq-browse-back="" onClick={onBack}
              sx={{ display: "flex", alignItems: "center", gap: 0.5, height: 32, pl: 1, pr: 1.5, borderRadius: "8px", border: `1px solid ${BORDER}`,
                bgcolor: PANEL, color: "#41525f", fontFamily: "inherit", fontSize: 12.5, fontWeight: 600, cursor: "pointer", flexShrink: 0 }}>
              <ArrowBackIosNewIcon sx={{ fontSize: 12 }} />{sectionLabel || title}
            </Box>
            <Typography sx={{ fontSize: 12, color: DIM, flex: 1, minWidth: 0 }} noWrap>
              {cards.length > 1 ? `the other ${cards.length - 1} ${sectionLabel && sectionLabel !== "everything" ? `${sectionLabel.toLowerCase()} ` : ""}cards are hidden while this one is open` : ""}
            </Typography>
          </Box>
          <Box sx={{ p: { xs: 1, sm: 1.75 } }}>{detail}</Box>
        </Box>
      )}

      {/* 2. the list */}
      {!detail && section != null && (
        <>
          {!!note && <Typography sx={{ fontSize: 12.5, color: DIM, lineHeight: 1.55, px: 0.5 }}>{note}</Typography>}
          {/* a tab whose list is ROWS (Reports, Hub) keeps them rows - `wide`; cards (Connections, Settings) sit in a grid */}
          <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: wide ? "minmax(0, 1fr)" : { xs: "minmax(0, 1fr)", sm: "repeat(auto-fill, minmax(240px, 1fr))" } }}>
            {cards.map((c) => c.node ? (
              <Box key={c.key} data-tq-browse-card={c.key} sx={{ minWidth: 0 }}>{c.node}</Box>
            ) : (
              <Box key={c.key} component="button" type="button" data-tq-browse-card={c.key} disabled={!c.onOpen} onClick={c.onOpen}
                sx={{ display: "flex", alignItems: "flex-start", gap: 1.25, textAlign: "left", p: 1.5, border: `1px solid ${BORDER}`, borderRadius: "10px",
                  bgcolor: PANEL, cursor: c.onOpen ? "pointer" : "default", fontFamily: "inherit", minWidth: 0, opacity: c.onOpen ? 1 : 0.7,
                  "&:hover": c.onOpen ? { borderColor: "#b9c3cb" } : {} }}>
                {c.icon}
                <Box sx={{ minWidth: 0, flex: 1 }}>
                  <Typography sx={{ fontSize: 13, fontWeight: 650, color: INK }} noWrap>{c.title}</Typography>
                  {!!c.sub && <Typography sx={{ fontSize: 11.5, color: DIM, lineHeight: 1.45, display: "-webkit-box", WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical", overflow: "hidden" }}>{c.sub}</Typography>}
                </Box>
                {!!c.badge && <Box component="span" sx={{ flexShrink: 0, fontSize: 10.5, fontWeight: 600, color: c.badgeInk || FAINT }}>{c.badge}</Box>}
              </Box>
            ))}
            {!cards.length && <Typography sx={{ fontSize: 12.5, color: FAINT, p: 1 }}>{empty}</Typography>}
          </Box>
        </>
      )}
    </Box>
  );
}

// a card with no open detail says so: an earlier card's subject must not stay "this" in the conversation's words
const NoSubject = ({ onOpenCard }) => { useEffect(() => { onOpenCard?.(null); }, [onOpenCard]); return null; };

// One browse card on the chat line: which area, and its state ({section, open}) - the view keeps the rest.
// `live` is false once a newer browse card is posted, so only one detail is ever mounted.
export default function CanvasBrowse({ area, state, onState, live, onOpenCard, onNavigate, onOpenTask, onReopen, onClose }) {
  const frame = (props) => <BrowseFrame {...props} live={live} onOpenCard={onOpenCard} onReopen={onReopen} />;
  const common = { browse: frame, browseState: state, onBrowseState: onState };
  if (!live) return frame({ title: AREA_TITLES[area] });
  // NEW is the one area that starts something: the card is the sheet's own form, in the conversation, and closing it
  // takes the line away (an earlier browse card folds to its title; this one has nothing left to read once it is closed)
  if (area === "new") return (
    <Box data-tq-browse="new"><NoSubject onOpenCard={onOpenCard} /><NewSheet inline open onClose={onClose} onOpenTask={onOpenTask} /></Box>
  );
  return (
    <Box data-tq-browse={area}>
      {area === "connections" && <ConnectorsView onNavigate={onNavigate} {...common} />}
      {area === "reports" && <ReportsView {...common} />}
      {area === "settings" && <SettingsView onNavigate={onNavigate} {...common} />}
      {area === "hub" && <Suspense fallback={<CircularProgress size={20} />}><HubView onOpenTask={onOpenTask} {...common} /></Suspense>}
    </Box>
  );
}
export const AREA_TITLES = { new: "New", connections: "Connections", reports: "Reports", settings: "Settings", hub: "Hub" };

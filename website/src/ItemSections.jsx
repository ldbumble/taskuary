// AN ITEM IN A TASK'S SECTIONS (the owner, 2026-10-28: "even reports should come in with the 3 sections ... Want this to be consistent across.
// even fyi"): a report or an FYI on the table is the same card a task is - its header line, then Came from | the middle left to right (no Close
// out, 2026-11-05) - with the section it is about open and the others the SLIM tabs a live agent leaves (TaskPage MINI_W): an arrow, a mark,
// a dot for where it stands, the words on hover. A tab's press opens
// its section; the one the item is about folds to its full tab while another is open, as a live agent's does. The pieces are the task's own
// (TaskPage SectionTab, SECTION, SLOT, SectionHead), so the two read as one design. Every section stays mounted: the card's verbs (Foot) ride
// the dock's row from wherever they are drawn, whichever section is open
// ...and ON A DESK THEY RIDE ITS PANE (the owner, 2026-10-31: "i thought we moved all buttons to the agent canvas?? report should be white with
// buttons on it"): as a task's moves left the bar for its panes (2026-10-29/30), the open section wears the task's white strip - its name, its
// fold arrows - and an item that `lays` its moves has every one of them on the strip of the section it is about, and on that section's spine
// folded; the bar is Back and Next. A phone's stacked sections keep the row as it was
import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import api from "./api.js";
import { LinkPopups, Md } from "./md.jsx";
import { label as btn } from "./buttons.js";
import { AttachChip, usePromptImages } from "./promptImages.jsx";
import { PromptBox } from "./AgentSummary.jsx";
import "./generalWorkspace.css";
import { FOCUS, FOCUS_EDGE, MINI_W, OPEN_MIN, PaneStrip, SECTION, SHADE, SLOT, STRIP_H, SectionHead, SectionTab, tabW, useStackBelow } from "./TaskPage.jsx";
import { BORDER, DIM, INK, frameInner } from "./theme.jsx";
import { layTable, onPressing, useSpineAll } from "./actionRow.js";
import { itemLines, readingOf } from "./threadReading.js";
import { MESSAGE } from "./kinds.js";

// a section's white card on the warm ground, as a task's focus is
export const ItemPart = ({ children, sx = null, ...rest }) => <Box {...rest} sx={{ ...FOCUS, px: { xs: 1.25, sm: 2 }, minWidth: 0, ...sx }}>{children}</Box>;
// the section an item's moves are laid on, while it lays them (the card's Foot reads it: actionRow.splitRow `all`), else null
export const ItemLay = React.createContext(null);

// WHAT AN ITEM SAYS, AS TRIAGE READ IT, AND A BOX TO ASK ABOUT IT (the Close-out spec, 2026-11-04 section 8): a report, an FYI or a dashboard
// gets the column a task's chat opens with - "What this says", "What matters to you" - atop its middle section, and a box under it.
// `ask`: { key, kind, title, reading } (reading: the message payload's `reading`, store.message_thread - optional, so none draws no lines)
// ...THE BOX ONLY ANSWERS (the owner, 2026-11-04: "question on report should not start task"): it is the dock's own door (concierge.say)
// with the item in the turn's view, area 'item', which the server answers from the item and nothing more (concierge.asked_on_item)
const SAYS = { says: "What this says", matters: "What matters to you" };
// ...AND SEND TO AGENT IS THIS BOX, ONE ROAD (the owner, 2026-11-05: "maybe attach the report or fyi list to the prompt box on bottom and make them
// type in when they hit send to agent?"): the press opens the Agent tab with the item ON the box as a chip - an FYI handful's every line, each
// one removable - and the cursor in it. With a chip on, Send starts the agent: the item and the owner's words, through the road the old agent box
// took (`hand.start`, AssistantView.startOnItem); with none, the box answers from the item as it did. Removing the last chip goes back to that.
// `hand`: { verb, items: [{ key, title }], start({ verb, text, files, items }) } - set by handToItem, through the item's own ItemSections
const HANDS = new Map();
export const handToItem = (key, hand) => { const f = key && HANDS.get(key); if (!f) return false; f(hand); return true; };
const ASK_ONLY = "the answer here reads the item only";
// `came`: what the item is, a chip on the box while nothing is handed on (the owner, 2026-11-06: Came-from rides the one box as a chip)
export function ItemAsk({ ask, hand = null, onHand = null, came = "" }) {
  const ls = itemLines(readingOf(ask?.reading));
  const [text, setText] = useState(""), [said, setSaid] = useState([]), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const pics = usePromptImages({ files: true }), input = useRef(null);
  useEffect(() => { setText(""); setSaid([]); setErr(""); pics.clear(); }, [ask?.key]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (hand) setTimeout(() => input.current?.focus(), 0); }, [hand]);
  const title = typeof ask?.title === "string" ? ask.title : "";
  const drop = (k) => { const left = hand.items.filter((i) => i.key !== k); onHand?.(left.length ? { ...hand, items: left } : null); };
  const send = async () => {
    const q = text.trim();
    if (!q || busy || pics.busy) return;
    setBusy(true); setErr("");
    try {
      if (hand) { await hand.start({ verb: hand.verb, text: q, files: pics.paths, items: hand.items }); setText(""); pics.clear(); onHand?.(null); return; }
      const { data } = await api.post("/api/concierge/say", { text: q, key: ask.key,
        view: { area: "item", title, item: { kind: ask.kind, id: ask.key, title, section: "ask" } } });
      setSaid((w) => [...w, { q, a: String(data?.say || "") }]); setText("");
    } catch (e) { setErr(e?.response?.data?.detail || e?.message || (hand ? "It did not start - press Send again." : "That did not go through - try again.")); }
    finally { setBusy(false); }
  };
  // ...A CHAT, as a task's is (the owner, 2026-11-05: "add the reports/advisor/fyi to chat thing as well without close out"): what it says and what
  // matters as plain paragraphs, the owner's words a right-hand bubble, the answer the full width - no labels, no card around it, the box the one box
  // ...THE SAME BOX IN THE SAME PLACE (the owner, 2026-11-05: "the box should be where it always is, not moved up. Don't have separate code"): the
  // task chat's own PromptBox, held at the foot of the pane whatever is above it; Send to agent puts the item on it as a chip - nothing moves
  return <Box data-tq-item-ask={ask?.kind || (hand ? "agent" : "")} data-tq-item-hand={hand ? hand.items.length : undefined}
    sx={{ display: "flex", flexDirection: "column", gap: 1, flex: "1 0 auto", minWidth: 0, px: { xs: 0.5, sm: 1 } }}>
    {ls.map((l) => <Typography key={l.k} data-tq-item-reading={l.k} title={SAYS[l.k]}
      sx={{ fontSize: 13.5, lineHeight: 1.55, color: INK, overflowWrap: "anywhere" }}>{l.text}</Typography>)}
    {said.map((t, i) => <React.Fragment key={i}>
      <Typography data-tq-item-said="" sx={{ alignSelf: "flex-end", maxWidth: "75%", fontSize: 13.5, lineHeight: 1.48, color: INK, overflowWrap: "anywhere",
        bgcolor: "var(--tq-inset, #e7efe6)", border: "1px solid var(--tq-border, #cfdccd)", borderRadius: "13px", px: 1.5, py: 1 }}>{t.q}</Typography>
      <Box data-tq-item-answer="" sx={{ fontSize: 13.5, lineHeight: 1.55, color: INK, overflowWrap: "anywhere", "& p": { my: 0.25 } }}><LinkPopups><Md text={t.a} /></LinkPopups></Box>
    </React.Fragment>)}
    <Box aria-hidden sx={{ flex: "1 1 auto" }} />
    <Box sx={{ position: "sticky", bottom: 0, bgcolor: SHADE, pt: 0.5, mx: -0.5, px: 0.5 }}>
      <PromptBox text={text} setText={setText} pics={pics} busy={busy} onSend={send} inputRef={input} cannot={hand ? null : () => ASK_ONLY}
        placeholder={MESSAGE}
        label={hand ? btn(hand.verb) : "Ask about this"} sendAttrs={{ "data-tq-item-send": hand ? "agent" : "ask" }}
        chips={hand?.items.length ? hand.items.map((i) => <AttachChip key={i.key} data-tq-item-chip={i.key} name={i.title} onRemove={busy ? null : () => drop(i.key)}
          title={`${btn(hand.verb)} - it gets ${i.title}`} />) : came ? <AttachChip data-tq-came-chip="" name={came} icon={false} title={`Came from: ${came}`} /> : null} />
      {err && <Typography role="alert" sx={{ fontSize: 12.5, color: "var(--tq-danger, #a33)", pt: 0.5 }}>{err}</Typography>}
    </Box>
  </Box>;
}

// `sections`: [{ key, n, name, body, lines, foot, icon, moves }] in the flow's order; `about`: the key the item is about (it opens there, and only it
// folds to a full tab); `here`: the section it is up to; `height`: the canvas's (CanvasItem wordsCap) - one height, like a task's three;
// `lays`: its moves ride the `about` section on a desk (ItemLay); `ask`: what it says and the box, in the AGENT section only (the owner, 2026-11-05:
// "chat is on the came from tab. that's weird ... chat box is only on the agent tab") - the item still opens on what came in, never on Agent
// `hands`: it takes a Send to agent with no box of its own to answer from (an FYI handful: ask null) - the box is drawn while a chip is on
// `noAgent`: no Send to agent on its strip (an Advisor idea - the owner, 2026-11-06)
// `moves`: what registers the item's row verbs (RowMoves, Foot), mounted out of sight - a section of its own once, "Nothing owed" on its tab
const AGENT_STARTS = new Set(["regular_agent", "coding_agent", "send-general", "start-agent"]);
export default function ItemSections({ kind, label, title, aside, sections: all, about, here = about, height, itemKey, lays = false, ask = null, hands = false, noAgent = false,
  moves = null }) {
  // NO AGENT COLUMN WITH NOTHING OF ITS OWN (the owner, 2026-11-06: "the one bottom box with Came-from as a chip, with no side-column Agent"): the
  // box is at the foot of the section the item is about, its Came-from a chip on it
  const sections = all.filter((s) => !(s.key === "agent" && !s.body));
  const [open, setOpen] = useState(about), [hand, setHand] = useState(null);
  useEffect(() => { setOpen(about); setHand(null); }, [itemKey, about]);
  const takes = !!ask || hands, boxAt = sections.some((s) => s.key === "agent") ? "agent" : about;
  useEffect(() => {
    if (!takes) return undefined;
    const f = (h) => { setHand(h); setOpen(boxAt); };
    HANDS.set(itemKey, f);
    return () => { if (HANDS.get(itemKey) === f) HANDS.delete(itemKey); };
  }, [itemKey, takes, boxAt]);
  const box = (ask || hand) && <ItemAsk ask={ask} hand={hand} onHand={setHand} came={typeof title === "string" ? title : label} />;
  const skip = (v) => noAgent && AGENT_STARTS.has(String(v?.id || "").split(":").pop());
  const body = useRef(null), [w, setW] = useState(0);
  useLayoutEffect(() => {
    const el = body.current;
    if (!el) return undefined;
    const on = () => setW(Math.round(el.getBoundingClientRect().width));
    on();
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(on); ro.observe(el); return () => ro.disconnect();
  }, []);
  // ...and a section with a STAGE MOVE on its spine (an FYI's Agent: Send to agent) folds to a full tab, as a task's does, so the move can stand
  // there (the owner, 2026-10-31); a press on it opens that section, as a task's spine does
  const spine = useSpineAll(), staged = (k) => k !== about && (spine[k] || []).length > 0;
  const closedW = (k) => (k === about || staged(k) ? tabW(w) : MINI_W);
  const openW = (k) => Math.max(OPEN_MIN, w - sections.filter((s) => s.key !== k).reduce((n, s) => n + closedW(s.key), 0) - (k === sections[0].key ? 0 : 1));
  const at = (k) => sections.findIndex((s) => s.key === k);
  // ON A PHONE THEY STACK, as a task's sections do under STACK_BELOW (trust audit R1, 2026-10-28): slim side tabs left a report 240px wide
  // ...and wider than a phone only under DESK_STACK_BELOW (TaskPage.useStackBelow): stacked, its moves went back on the bar
  const stackBelow = useStackBelow(), stacked = w > 0 && w < stackBelow, keys = sections.map((s) => s.key), kq = keys.join(" ");
  const laid = React.useMemo(() => (lays && w > 0 && !stacked ? { all: about, keys: kq.split(" ") } : null), [lays, w > 0, stacked, about, kq]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { layTable(itemKey, laid); return () => layTable(itemKey, null); }, [itemKey, laid]);
  const spineAt = useRef(spine); spineAt.current = spine;
  useEffect(() => (laid ? onPressing((id) => { const k = laid.keys.find((x) => x !== about && (spineAt.current[x] || []).some((v) => v.id === id)); if (k) setOpen(k); }) : undefined),
    [laid, about]);
  return (
    <ItemLay.Provider value={laid}>
    <Box data-tq-item-sections={kind} sx={{ ...frameInner, height, display: "flex", flexDirection: "column", boxSizing: "border-box", minWidth: 0 }}>
      {/* THE HEADER LINE a task's is (TaskPage data-tq-task-head): what kind it is in the ref's place, its title, and when */}
      <Box data-tq-item-head="" sx={{ px: 1.75, py: 0.7, bgcolor: "var(--tq-panel, #fff)", borderBottom: `1px solid ${BORDER}`, flexShrink: 0, display: "flex", gap: 0.9, alignItems: "center", minHeight: 30 }}>
        <Typography sx={{ color: "var(--tq-link, #41525f)", letterSpacing: ".015em", fontWeight: 600, fontSize: 11.5, flexShrink: 0 }}>{label}</Typography>
        <Typography noWrap title={typeof title === "string" ? title : undefined} sx={{ color: INK, flex: 1, minWidth: 0, fontWeight: 600, fontSize: 14, letterSpacing: "-.005em" }}>{title}</Typography>
        {aside && <Box sx={{ flexShrink: 0, color: DIM, fontSize: 11.5, display: "flex", alignItems: "center", gap: 0.75 }}>{aside}</Box>}
      </Box>
      <Box ref={body} data-tq-item-body="" data-tq-sections="" data-tq-main={open} data-tq-stacked={stacked ? "" : undefined}
        sx={stacked ? { flex: 1, minHeight: 0, minWidth: 0, display: "flex", flexDirection: "column", gap: 1.5, bgcolor: SHADE, overflowY: "auto",
          scrollbarWidth: "thin", overscrollBehaviorY: "contain", px: 1.25, py: 1.25, boxSizing: "border-box" }
          : { flex: 1, minHeight: 0, minWidth: 0, display: "flex", flexDirection: "row", bgcolor: SHADE, position: "relative", overflow: "hidden" }}>
        {sections.map((s, i) => stacked ? (
          <Box key={s.key} data-tq-slot={s.key} data-tq-open="" sx={{ minWidth: 0, flexShrink: 0 }}>
            <Box role="region" aria-label={s.name} className="tq-item-sec" sx={{ display: "flex", flexDirection: "column", gap: 1.5, minWidth: 0 }}>
              <SectionHead sec={s} moves={s.moves} />
              {s.body}
              {s.key === boxAt && box}
            </Box>
          </Box>
        ) : (
          // ...the open one under its white strip (TaskPage PaneStrip), which says its name: a non-`about` one folds back to the one it is about
          <Box key={s.key} data-tq-slot={s.key} data-tq-open={open === s.key ? "" : undefined}
            sx={{ ...SLOT(open === s.key, closedW(s.key)), ...(i ? { borderLeft: `1px solid ${FOCUS_EDGE}` } : {}), "& > [role=region]": { top: `${STRIP_H}px` } }}>
            {open !== s.key && <SectionTab sec={s} lines={s.lines || []} foot={s.foot || ""} icon={s.icon} here={here === s.key && open !== here}
              mini={closedW(s.key) === MINI_W} before={at(s.key) < at(open)} onOpen={() => setOpen(s.key)} />}
            {open === s.key && <PaneStrip sec={s.key} name={s.name} keys={keys} skip={skip} fold={(to) => (s.key === about ? to : about)} onFold={setOpen} />}
            <Box role="region" aria-label={s.name} aria-hidden={open !== s.key ? true : undefined} className="tq-item-sec"
              sx={{ ...SECTION(open === s.key, w ? openW(s.key) : "100%"), gap: 1.5 }}>
              {s.body}
              {s.key === boxAt && box}
            </Box>
          </Box>
        ))}
      </Box>
      {moves && <Box data-tq-item-moves="" aria-hidden sx={{ display: "none" }}>{moves}</Box>}
    </Box>
    </ItemLay.Provider>
  );
}

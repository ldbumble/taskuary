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
import { label as btn } from "./buttons.js";
import { AttachChip, usePromptImages } from "./promptImages.jsx";
import { PromptBox } from "./AgentSummary.jsx";
import "./generalWorkspace.css";
import { SECTIONS, sectionFade } from "./taskLayout.js";
import { FOCUS, FOCUS_EDGE, MINI_W, OPEN_MIN, PaneStrip, SECTION, SHADE, SLOT, STRIP_H, SectionHead, SectionTab, tabW, useStackBelow } from "./TaskPage.jsx";
import { BORDER, DIM, INK, frameInner } from "./theme.jsx";
import { layTable, onPressing, useSpineAll } from "./actionRow.js";
import { itemLines, readingOf } from "./threadReading.js";
import { MESSAGE } from "./kinds.js";
import { ArrivedWords } from "./GeneralWorkspace.jsx";
import { takeHands } from "./itemHand.js";

// a section's white card on the warm ground, as a task's focus is
export const ItemPart = ({ children, sx = null, ...rest }) => <Box {...rest} sx={{ ...FOCUS, px: { xs: 1.25, sm: 2 }, minWidth: 0, ...sx }}>{children}</Box>;
// the section an item's moves are laid on, while it lays them (the card's Foot reads it: actionRow.splitRow `all`), else null
export const ItemLay = React.createContext(null);

// WHAT AN ITEM SAYS, AS TRIAGE READ IT, AND A BOX TO ASK ABOUT IT (the Close-out spec, 2026-11-04 section 8): a report, an FYI or a dashboard
// gets the column a task's chat opens with - "What this says", "What matters to you" - atop its middle section, and a box under it.
// `ask`: { key, kind, title, reading } (reading: the message payload's `reading`, store.message_thread - optional, so none draws no lines)
// ...THE BOX IS A TASK CHAT'S ROAD (the owner, 2026-11-23: "same input box"; walk 13: it went to the home Assistant, its answer kept only in the
// page and gone, and what it said was false): his line starts the agent on the item, as Send to agent does - his line and its answer are that
// task's chat, stored and drawn there. `startsItems` is the start AssistantView gives every item box (its startOnItem)
const SAYS = { says: "What this says", matters: "What matters to you" };
// ...AND SEND TO AGENT IS THIS BOX, ONE ROAD (the owner, 2026-11-05: "maybe attach the report or fyi list to the prompt box on bottom and make them
// type in when they hit send to agent?"): the press opens the Agent tab with the item ON the box as a chip - an FYI handful's every line, each
// one removable - and the cursor in it. With a chip on, Send starts the agent: the item and the owner's words, through the road the old agent box
// took (`hand.start`, AssistantView.startOnItem); with none, the box answers from the item as it did. Removing the last chip goes back to that.
// `hand`: { verb, items: [{ key, title }], start({ verb, text, files, items }) } - set by handToItem (itemHand.js), through the item's own ItemSections
let START = null;
export const startsItems = (f) => { START = f; };
// ...and the same start for an item Taskuary made, drawn by the task page (madeTask: its chat's box)
export const startItem = (item, o) => (START ? START(item, o) : Promise.reject(new Error("It did not start - press Send again.")));
// `draft`: { text, setText, pics } - his words and files, held by the item (ItemSections) so they stay his when Send to agent moves the box to the
// Agent section: a box of its own lost what he had typed at the press (the stress round, 2026-11-18)
// `agent`: it stands in the Agent section - the box is always there, as a task's chat has it (the owner, 2026-11-20: "chat box is only on the agent tab")
const AGENT = "regular_agent";
const KIND_NOUN = { fyi: "notice", review: "draft" };
export function ItemAsk({ ask, hand = null, onHand = null, agent = false, hint = "", draft }) {
  const ls = hand || agent ? [] : itemLines(readingOf(ask?.reading));
  const { text, setText, pics } = draft;
  const [busy, setBusy] = useState(false), [err, setErr] = useState(""), input = useRef(null);
  useEffect(() => { setErr(""); }, [ask?.key]);
  useEffect(() => { if (hand) setTimeout(() => input.current?.focus(), 0); }, [hand]);
  const title = typeof ask?.title === "string" ? ask.title : "";
  const drop = (k) => { const left = hand.items.filter((i) => i.key !== k); onHand?.(left.length ? { ...hand, items: left } : null); };
  const send = async () => {
    const q = text.trim();
    if (!q || busy || pics.busy) return;
    setBusy(true); setErr("");
    try {
      if (hand) await hand.start({ verb: hand.verb, text: q, files: pics.paths, items: hand.items });
      else if (START) await START({ key: ask.key, title }, { verb: AGENT, text: q, files: pics.paths });
      else throw new Error("It did not start - press Send again.");
      setText(""); pics.clear(); onHand?.(null);
    } catch (e) { setErr(e?.response?.data?.detail || e?.message || "It did not start - press Send again."); }
    finally { setBusy(false); }
  };
  // ...A CHAT, as a task's is (the owner, 2026-11-05: "add the reports/advisor/fyi to chat thing as well without close out"): what it says and what
  // matters as plain paragraphs, the owner's words a right-hand bubble, the answer the full width - no labels, no card around it, the box the one box
  // ...its Send lit by words only (2026-11-18): the item's box goes on his words, and a file alone lit a press that did nothing
  // ...THE SAME BOX IN THE SAME PLACE (the owner, 2026-11-05: "the box should be where it always is, not moved up. Don't have separate code"): the
  // task chat's own PromptBox, held at the foot of the pane whatever is above it; Send to agent puts the item on it as a chip - nothing moves
  // ...his line and its answer in the task chat's own rows (ConvLine, ConvTurn), never a look of their own - laid straight in the
  // section (`contents`), so the box under them holds the section's foot however long what is above it runs
  return <Box className="tq-aui-chat" data-tq-item-ask={ask?.kind || (hand ? "agent" : "")} data-tq-item-hand={hand ? hand.items.length : undefined}
    sx={{ display: "contents" }}>
    {ls.map((l) => <Typography key={l.k} data-tq-item-reading={l.k} title={SAYS[l.k]}
      sx={{ fontSize: 13.5, lineHeight: 1.55, color: INK, overflowWrap: "anywhere" }}>{l.text}</Typography>)}
    {/* ...THE BOX IS THE AGENT TAB'S ALONE (the owner, 2026-11-20: "if you put prompt box on the bottom of Came from you are confusing the 2 tabs"):
        never under what came in - it stands in the Agent section: or once Send to agent has put the item on it */}
    {(hand || agent) && <><Box aria-hidden sx={{ flex: "1 1 auto" }} />
    {/* ...down over the section's own foot padding (TaskPage SECTION's 12px), or what scrolls under it shows through beneath it */}
    <Box sx={{ position: "sticky", bottom: "-12px", mb: "-12px", pb: "12px", bgcolor: `var(--tq-item-ground, ${SHADE})`, pt: 0.5, mx: -0.5, px: 0.5 }}>
      <PromptBox text={text} setText={setText} pics={pics} busy={busy} onSend={send} inputRef={input} sendOff={!text.trim()}
        placeholder={hint || MESSAGE}
        label={btn(hand ? hand.verb : AGENT)} sendAttrs={{ "data-tq-item-send": "agent" }}
        chips={hand?.items.length ? hand.items.map((i) => <AttachChip key={i.key} data-tq-item-chip={i.key} name={i.title} onRemove={busy ? null : () => drop(i.key)}
          title={`${btn(hand.verb)} - it gets ${i.title}`} />) : null} />
      {err && <Typography role="alert" sx={{ fontSize: 12.5, color: "var(--tq-danger, #a33)", pt: 0.5 }}>{err}</Typography>}
    </Box></>}
  </Box>;
}

// `sections`: [{ key, n, name, body, lines, foot, icon, moves }] in the flow's order; `about`: the key the item is about (it opens there, and only it
// folds to a full tab); `here`: the section it is up to; `height`: the canvas's (CanvasItem wordsCap) - one height, like a task's three;
// `lays`: its moves ride the `about` section on a desk (ItemLay); `ask`: what it says and the box, in the AGENT section only (the owner, 2026-11-05:
// "chat is on the came from tab. that's weird ... chat box is only on the agent tab") - the item still opens on what came in, never on Agent
// `hands`: it takes a Send to agent with no box of its own to answer from (an FYI handful: ask null) - the box is drawn while a chip is on
// `moves`: what registers the item's row verbs (RowMoves, Foot), mounted out of sight - a section of its own once, "Nothing owed" on its tab
const AGENT_STARTS = new Set(["regular_agent", "coding_agent", "send-general", "start-agent"]);
export default function ItemSections({ kind, label, title, aside, sections: all, about, here = about, height, itemKey, lays = false, ask = null, hands = false,
  moves = null }) {
  // NO AGENT COLUMN WITH NOTHING OF ITS OWN (the owner, 2026-11-06: "the one bottom box with Came-from as a chip, with no side-column Agent"): the
  // box is at the foot of the section the item is about, its Came-from a chip on it
  // ...the item by its kind in his words: "this notice", never "this fyi" (the judge's walk, 2026-11-19)
  const [open, setOpen] = useState(about), [hand, setHand] = useState(null), noun = KIND_NOUN[kind] || String(label || kind || "item").toLowerCase();
  // ...SEND TO AGENT OPENS THE AGENT'S OWN CANVAS (the owner, 2026-11-17: "why do i see the dashboard? it should be blank agent chat canvas"):
  // the press adds the Agent section - blank, the box at its foot with the item a chip on it - and opens it; the item folds to its tab on the
  // left, as a task's Came from does. Taking the chip off closes it, and the item is back as it was
  const sections = hand && !all.some((s) => s.key === "agent" && s.body)
    ? [...all.filter((s) => s.key !== "agent"), { key: "agent", n: all.length + 1, name: SECTIONS[1].name, lines: ["your words start it"],
        // ...BLANK, as any agent's canvas before its first line (the owner, 2026-11-17: "agent section should be blank ... it shows as pill on left
        // side you type on it and it goes to blank canvas"): the item is the chip on the box, and the box's own words ask what to do with it
        body: <Box data-tq-item-agent="" sx={{ flex: "1 1 auto" }} /> }]
    : all.filter((s) => !(s.key === "agent" && !s.body));
  useEffect(() => { setOpen(about); setHand(null); }, [itemKey, about]);
  // ...the box's words and files are the item's, wherever the box stands - a new item starts them empty
  const [text, setText] = useState(""), pics = usePromptImages({ files: true }), draft = { text, setText, pics };
  useEffect(() => { setText(""); pics.clear(); }, [itemKey]);   // eslint-disable-line react-hooks/exhaustive-deps
  const fadeMemo = useRef(null); fadeMemo.current = sectionFade(fadeMemo.current, open, itemKey, about);
  const fades = fadeMemo.current.moved;
  const takes = !!ask || hands, boxAt = sections.some((s) => s.key === "agent") ? "agent" : about;
  useEffect(() => {
    if (!takes) return undefined;
    return takeHands(itemKey, (h) => setHand(h));
  }, [itemKey, takes, boxAt]);
  // ...opened where its box now is, the moment it is handed on - and back on the item once the chip is off and the section with it
  useEffect(() => { if (hand) setOpen(boxAt); else setOpen((o) => (sections.some((x) => x.key === o) ? o : about)); }, [hand, boxAt]);   // eslint-disable-line react-hooks/exhaustive-deps
  const box = (ask || hand) && <ItemAsk ask={ask} hand={hand} onHand={setHand} draft={draft} agent={boxAt === "agent"}
    hint={hand ? `What should the agent do with this ${noun}?` : ""} />;
  // ...and none once it is handed on: the press is made, the box is where it goes now
  const skip = (v) => !!hand && AGENT_STARTS.has(String(v?.id || "").split(":").pop());
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
              sx={{ ...SECTION(open === s.key, w ? openW(s.key) : "100%", false, false, fades), gap: 1.5 }}>
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

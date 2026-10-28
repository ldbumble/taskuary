// THE ITEM ON THE TABLE (the canvas redesign, docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md):
// an item with a task behind it is shown by the Tasks tab's own task view (TaskPage) inside the conversation, at the
// canvas's width and the chat's full height - Task, Agent work, Close out, with their bars and the agent's pane.
//
// ONE HEIGHT, ALWAYS. Expand hides the conversation around the view; it never changes the view's own box. A pty grown
// after it has output corrupts the pane (ConPTY keeps a grown viewport top-anchored - see terminal.remember_geometry),
// so the terminal inside is sized once, for the whole canvas, and nothing here can grow it afterwards.
import React, { useEffect, useRef, useState } from "react";
import { Box } from "@mui/material";
import TaskPage from "./TaskPage.jsx";
import ActionRow, { AdvisorNext } from "./ActionRow.jsx";
import api from "./api.js";
import { onLive } from "./live.js";
import { adviceKeyFor, adviceShown, stripWord, taskNote } from "./advice.js";
import { TableVerbs, onPressed, useHost, useVerbs, walkMove } from "./actionRow.js";
import { adviceRead } from "./tableState.js";
import { hint as btnHint, label as btnLabel } from "./buttons.js";

// THE ADVISOR'S PICK ON A PHONE'S ROW (U12): the dock's row is filled by the canvas's advice, but a phone draws its own row at the
// view's foot, which was handed none - so the suggestion's line stood over a row whose dark button was something else. Read for
// this item, re-read when the Advisor's event names it, and dropped when the item moves on (adviceShown). The same ONE decision as the
// desk's (advisor.decide) - and no "Thinking..." while it is read: the rule's button is lit at once (the owner, 2026-10-23)
function useItemAdvice(card, on) {
  const [advice, setAdvice] = useState(null);
  const key = card?.key || "";
  useEffect(() => {
    if (!on || !key) { setAdvice(null); return undefined; }
    let live = true;
    const read = () => api.get("/api/advice", { params: { key } })
      .then(({ data }) => { if (live) setAdvice(adviceRead(data, key).advice); })
      .catch(() => { if (live) setAdvice(null); });
    setAdvice(null); read();
    const off = onLive("advice", (ev) => { if (adviceKeyFor(ev, { key, aliases: card.aliases || [] })) read(); });
    // an act on the item moves its revision: read the line again (2026-10-19) - not Next, which puts this item down (overnight walk)
    const after = onPressed((id) => { if (!walkMove(id)) read(); });
    return () => { live = false; off?.(); after(); };
  }, [on, key]);   // eslint-disable-line react-hooks/exhaustive-deps
  return advice;
}

// the height the view takes: the chat body's own, less its padding - the same in both states (see above). Said in CSS,
// against the chat body as a SIZE container (assistantView.css .tq-chat-body): a height measured in script was stale
// whenever the body was measured hidden or before it settled, and the view sat at its 420px floor under a screen of
// empty canvas (the owner, 2026-09-29: "fill up more width and more height ... see more in one screen")
// ...and ALL of it (the owner, 2026-10-18: "you can almost never see the full output text"): 100cqh is already the body's
// content box, so taking its padding off again left 26px of cream under the view; only the view's own 12px margin comes off now.
// The floor is lower too - at 1366x768 the 420px floor was taller than the body, and the view's head scrolled out of sight.
// ...and the body's PADDING is the view's too (2026-10-18, "top is not high enough"): its top meets the body's top (AssistantView
// toEnd and the pin), so the 26px of padding plus 14 = the body's whole height less a 12px gap over the dock.
export const CANVAS_ITEM_HEIGHT = "max(340px, calc(100cqh + 14px))";
// ...and a view of WORDS stops a drop short of it (the owner, 2026-10-26: "size of the task looks too big, should we not leave a drop of
// space under it" - and "if agent is open then use the full space"): the same 12px gap again under its cap; a pane keeps the whole height
export const wordsCap = (h) => (typeof h === "number" ? h - 12 : `calc(${h} - 12px)`);
// ...and the least a card of words grows to while a drawer is out of it: its head and ~280px of drawer to read in
export const DRAWER_FLOOR = 400;
// ...and A CARD OF WORDS HOLDS ONE HEIGHT (the owner, 2026-10-27: "if an agent is not open it should be pinned to the top of the view ... take up
// at least half or a little more, and not change if I click Reply or anything else, unless I start an agent"): it was exactly as tall as what
// its main view said, so Reply - the view going from the task to its draft - or a drawer, a stage, a draft typed into, moved its foot. Now it
// opens at least WORDS_FLOOR of the cap (and never under DRAWER_FLOOR, so a drawer has room without growing it), grows to what it says up to
// the cap while it settles, and is then held at that height (useHeldHeight): what it says past that scrolls inside
export const WORDS_FLOOR = 0.55;
export const wordsFloor = (cap) => `max(calc(${cap} * ${WORDS_FLOOR}), min(${DRAWER_FLOOR}px, ${cap}))`;
// ...held once the owner first touches the page or the card has stood still this long; re-taken when the item or the window changes
export const SETTLE_MS = 1200;

function useHeldHeight(box, key) {
  const [held, setHeld] = useState(null);
  const [size, setSize] = useState(() => (typeof window === "undefined" ? "" : `${window.innerWidth}x${window.innerHeight}`));
  useEffect(() => {
    const on = () => setSize(`${window.innerWidth}x${window.innerHeight}`);
    window.addEventListener("resize", on); return () => window.removeEventListener("resize", on);
  }, []);
  useEffect(() => {
    setHeld(null);
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    let timer = null, done = false;
    // a pane's full height is never what is held: only a card of words (the :has() rule below) has a height of its own
    const hold = () => { if (done) return; const h = el.getBoundingClientRect().height; if (!h) return; done = true; setHeld(Math.round(h)); off(); };
    const wait = () => { clearTimeout(timer); timer = setTimeout(hold, SETTLE_MS); };
    // ...still while what it says is loading, not only while its box moves: under the floor the box stands still as the task fills in
    const ro = new ResizeObserver(wait), mo = new MutationObserver(wait);
    const touch = () => hold();
    const off = () => {
      clearTimeout(timer); ro.disconnect(); mo.disconnect();
      document.removeEventListener("pointerdown", touch, true); document.removeEventListener("keydown", touch, true);
    };
    ro.observe(el); mo.observe(el, { childList: true, subtree: true }); wait();
    document.addEventListener("pointerdown", touch, true); document.addEventListener("keydown", touch, true);
    return off;
  }, [key, size]);   // eslint-disable-line react-hooks/exhaustive-deps
  return held;
}

// an item the canvas shows as a task view: it has a task, and it is not a proposal, a set-up step or a batch
export const showsTask = (card, kind) => !!card?.tid && !["proposal", "setup", "walk", "brief", "fyis", "meeting"].includes(kind);

// ON A PHONE the view is the SCREEN's height from the start, and Expand pins that same box over the page with a back
// arrow - full screen, and still never a resize: the box it pins is measured in place, the same width and height.
export const phoneItemHeight = (innerHeight) => Math.max(420, Math.round((innerHeight || 0) - 16));

export default function CanvasItem({ card, height, expanded, onExpand, onNext, busy, picking = false, onFold, onAfter, onLeave, onStay, onListChanged, onChanged, onOpenTask, onReminded, phone = false, lit = null, advice = null, onPropose = null }) {
  // a task opened "and start it" or "with this dialog up" (TaskHubPage.openTask): once, then it is spent
  const [auto, setAuto] = useState(card.autostart ? { taskId: card.tid, ...card.autostart } : null);
  const [act, setAct] = useState(card.act ? { taskId: card.tid, act: card.act } : null);
  // a view put on the table is brought into view whole - the chat's own scroll pinned its bottom, which left a task opened
  // by a link showing only its heading under a screenful of earlier lines. ...to the SAME top the chat's pin holds it at (keepTable): with
  // an 8px scroll margin here the two smooth scrolls fought, this one won, and the pin put the card back 8px when the answer landed -
  // seconds after Next on a real brain (browser/next-steady.test.mjs)
  const box = useRef(null);
  useEffect(() => { box.current?.scrollIntoView({ block: "start" }); }, [card.key]);
  const [phoneH] = useState(() => phoneItemHeight(typeof window === "undefined" ? 0 : window.innerHeight));
  // where the box sits in the page, taken the moment it is pinned - the pinned box keeps exactly this width
  const [pin, setPin] = useState(null);
  useEffect(() => {
    if (!(phone && expanded)) { setPin(null); return; }
    const r = box.current?.getBoundingClientRect();
    if (r) setPin({ left: r.left, width: r.width });   // exact: a rounded width re-wrapped the strip and moved the pane by 2px
  }, [phone, expanded]);
  const h = phone ? phoneH : height;
  const held = useHeldHeight(box, card.key);
  // NEXT, in the row: the walk's ONE button on a task (the owner, 2026-09-29), the same handler as the button it replaces
  useHost(phone);
  // ...pressable while a pick (a rail row, a link) is on its way - AssistantView holds that press (`picking`); greyed only by a Next in
  // flight, and drawn as it was then (`steady`): it flashed grey for the ~300 ms of every switch (the owner, 2026-10-26)
  useVerbs("next", [{ id: "next", group: "next", label: btnLabel("next"), disabled: !!busy && !picking, steady: true, run: () => onNext(), title: btnHint("next") }]);
  // ...and while a phone's own read is on its way the desk's decision for this item lights its row: a window narrowed to a phone dropped the
  // lit Reply for the length of the read, and the row looked as if the move had folded away (row-one-line, walk item 2 @390, 2026-10-28)
  const own = useItemAdvice(card, phone);
  const read = own || (phone && advice?.verb && advice.for === card.key ? advice : null);
  // the Assistant's lit button outranks the Advisor's line, as it does over the composer (assistantLight.js)
  const advised = lit ? null : adviceShown(read, { key: card.key, lane: card.lane }, busy);
  // ...and the strip's word and the button it lights are ONE decision, the dock's (advice.stripWord, the UI audit's C2)
  const { noAi, pick } = stripWord({ speaks: true, busy, shown: advised, lit, advice: read, key: card.key, lane: card.lane });
  // ...and with no AI the strip's own Connect an AI went with it, not onto the row (the owner, 2026-10-26: "if you don't get through ai
  // setup the whole thing doesn't work"): a no_ai pick lights nothing there
  // THE ADVISOR'S SECTION, IN THE VIEW (advice.taskNote): the desk's decision for this item (`advice`, AssistantView), a phone's own read
  const note = taskNote(phone ? adviceShown(read, { key: card.key, lane: card.lane }, false)
    : advice && (advice.for === card.key || (card.aliases || []).includes(advice.for)) ? advice : null);
  return (
    <>
    {pin && <Box aria-hidden sx={{ position: "fixed", inset: 0, zIndex: 1349, bgcolor: "#f6f4f1" }} />}
    {/* focusable, not in the Tab order: a search pick hands focus here, to what it opened (SearchEverything focusDrawn) */}
    <Box ref={box} data-tq-canvas-item={card.key} data-tq-pinned={pin ? "" : undefined} tabIndex={-1}
      sx={{ height: h, display: "flex", flexDirection: "column", minWidth: 0, scrollMarginTop: 0, outline: "none",
        // ...but a view with NO PANE in it (a stopped agent, a note, a closed task) is only as tall as what it says: the full
        // height left a screen of blank canvas under three short bars (the owner, 2026-09-30: "what's with extra space???").
        // A pane - terminal, agent chat, browser - still gets the one height it is sized for, so the pty is never grown.
        // ...on a phone too: there it stood the full screen under a three-row task, 350px of cream below Context & history
        // (the 2026-10-07 design pass). Pinned (Expand) it keeps the screen.
        // ...and a Result is words too: the full-width layout kept the whole height, a screen of blank under a stopped agent's
        // Result and Close out (the owner, 2026-10-22: "it should not take up the whole space though coding agents working we
        // want it to take up as much real estate as possible"). Only the From sidebar, laid over the work, asks for the room -
        // sized to the words it was cut off (the same day's "crunched down")
        // ...and a general agent's chat is a pane only while its session is live (the owner, 2026-10-25): finished, failed or closed it is
        // words too, and its room says so (TaskPage data-tq-agent-room)
        // ...and a DRAWER pulled out (Came from, Agent · Close out) no longer takes the whole height: the card stayed the canvas's height
        // under a few lines of Result, and the drawer and its tab ran 200px past the white of the task (the owner, 2026-10-26: "the ui of
        // the sidebars looks messed up? it's bigger then the task box"). The card keeps the height of what it says, the drawer is exactly
        // its body and scrolls inside; only a card too short to read a drawer in grows, to DRAWER_FLOOR and never past the cap
        // ...and that floor is now the card's from the start, with WORDS_FLOOR, and its height is held (useHeldHeight): a drawer, Reply or a
        // stage never moves its foot (the owner, 2026-10-27)
        ...(!pin ? { "&:not(:has(.xterm, [data-tq-agent-room='live'], [class*='tq-aui']:not([data-tq-agent-room='rest'] *), canvas, iframe))": {
          height: held ? `${held}px` : "auto", maxHeight: wordsCap(h), minHeight: wordsFloor(typeof h === "number" ? `${wordsCap(h)}px` : wordsCap(h)) },
          // ...and A TASK IN ITS THREE SECTIONS TAKES THE CANVAS (the owner, 2026-10-27: "it starts at the top and takes up most of it, down to a
          // small gap above the dock's buttons"): one height from the start, the cap, through every press - a short section is white under its words
          "&:has([data-tq-sections]):not(:has(.xterm, [data-tq-agent-room='live'], canvas, iframe))": { height: wordsCap(h), minHeight: wordsCap(h), maxHeight: wordsCap(h) } } : {}),
        ...(pin ? { position: "fixed", top: 8, left: pin.left, width: pin.width, zIndex: 1350 } : {}) }}>
      {/* a COLUMN that shrinks to the box: the task view inside is a flex column too, so its own scroller gets what is left (TaskPage) */}
      <Box sx={{ flex: "1 1 auto", minHeight: 0, display: "flex", flexDirection: "column" }}>
      {/* `rail`: the rail's own row for this task - the header's status pill wears exactly its mark and word (railStatus.js) */}
      {/* ...its verbs are this item's: the row stops drawing them the moment the table names another (actionRow.rowTable) */}
      <TableVerbs value={card.key}>
      <TaskPage taskId={card.tid} title={card.title || ""} rail={card} canvas active autostart={auto} onAutostarted={() => setAuto(null)}
        openAct={act} onActOpened={() => setAct(null)}
        expanded={expanded} onExpand={onExpand}
        onClose={onFold} onListChanged={onListChanged} onChanged={onChanged}
        // a goal's step opens as its own view on the table (TaskHubPage.openTask); onSelect never carried an id here
        onOpenTask={onOpenTask}
        // closed, put away or deleted here, the walk moves on - the same as Done on a walk card
        onSelect={(id) => { if (!id) onAfter(); }}
        onFinish={async (status, close) => { await close(); onAfter(); }}
        onReminded={(out) => { onReminded?.(out); if (out?.remindAt) onAfter(); }} backArrow={phone}
        // Mark done and Remind me put the task down AT THE PRESS, as Next does; a failure puts it back with the reason
        // ...and the day the owner typed with Remind me ("remind me Monday"), its picker's first button (assistantLight's light.day)
        saidDay={lit?.verb === "defer" ? lit.day || null : null}
        onLeave={onLeave} onStay={onStay} note={note} litMove={phone ? pick?.verb || pick?.id || "" : ""} />
      </TableVerbs>
      </Box>
      {/* THE BUTTONS ARE NOT HERE (layout B, 2026-09-30): the view registers its verbs and Next, and the ONE row above the chat line
          draws them. On a phone the same row rides at the view's foot instead, in both states - the pinned full-screen view covers
          the dock, and the box is sized once, so Expand must not add or take away a row. */}
      {/* ...and NO LINE OVER IT, as on the desk (the owner, 2026-10-26: "remove the advisor"): its pick is the lit button, a missing AI
          the row's own Connect an AI, and a warning is in the view beside what it is about (advice.taskNote) */}
      {phone && <div className="tq-docked">
        <AdvisorNext advice={noAi ? null : advised} onPropose={onPropose} />
        <ActionRow inline advised={pick} /></div>}
    </Box>
    </>
  );
}

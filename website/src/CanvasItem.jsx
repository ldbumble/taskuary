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
import ActionRow, { AdviceNone, AdvisorNext } from "./ActionRow.jsx";
import api from "./api.js";
import { onLive } from "./live.js";
import { adviceKeyFor, adviceShown, stripWord } from "./advice.js";
import { onPressed, useHost, useVerbs } from "./actionRow.js";
import { adviceRead } from "./tableState.js";
import { hint as btnHint, label as btnLabel } from "./buttons.js";

// THE ADVISOR'S PICK ON A PHONE'S ROW (U12): the dock's row is filled by the canvas's advice, but a phone draws its own row at the
// view's foot, which was handed none - so the suggestion's line stood over a row whose dark button was something else. Read for
// this item, re-read when the Advisor's event names it, and dropped when the item moves on (adviceShown).
function useItemAdvice(card, on) {
  // ...and WHILE IT IS STILL BEING READ (`asking`): the phone's strip drew nothing at all over an item the Advisor had not judged yet,
  // where the page's says "Thinking about this one…" (the matrix's phone pass, 2026-10-20)
  const [advice, setAdvice] = useState(null), [asking, setAsking] = useState(false);
  const key = card?.key || "";
  useEffect(() => {
    if (!on || !key) { setAdvice(null); setAsking(false); return undefined; }
    let live = true;
    const read = () => api.get("/api/advice", { params: { key } })
      .then(({ data }) => { if (!live) return; const r = adviceRead(data, key); setAdvice(r.advice); setAsking(!!r.asking); })
      .catch(() => { if (live) { setAdvice(null); setAsking(false); } });
    setAdvice(null); setAsking(true); read();
    const off = onLive("advice", (ev) => { if (adviceKeyFor(ev, { key, aliases: card.aliases || [] })) read(); });
    const after = onPressed(() => read());          // an act on the item moves its revision: read the line again (2026-10-19)
    return () => { live = false; off?.(); after(); };
  }, [on, key]);   // eslint-disable-line react-hooks/exhaustive-deps
  return [advice, asking];
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

// an item the canvas shows as a task view: it has a task, and it is not a proposal, a set-up step or a batch
export const showsTask = (card, kind) => !!card?.tid && !["proposal", "setup", "walk", "brief", "fyis", "meeting"].includes(kind);

// ON A PHONE the view is the SCREEN's height from the start, and Expand pins that same box over the page with a back
// arrow - full screen, and still never a resize: the box it pins is measured in place, the same width and height.
export const phoneItemHeight = (innerHeight) => Math.max(420, Math.round((innerHeight || 0) - 16));

export default function CanvasItem({ card, height, expanded, onExpand, onNext, busy, onFold, onAfter, onLeave, onStay, onListChanged, onChanged, onOpenTask, onReminded, phone = false, lit = null, onPropose = null }) {
  // a task opened "and start it" or "with this dialog up" (TaskHubPage.openTask): once, then it is spent
  const [auto, setAuto] = useState(card.autostart ? { taskId: card.tid, ...card.autostart } : null);
  const [act, setAct] = useState(card.act ? { taskId: card.tid, act: card.act } : null);
  // a view put on the table is brought into view whole - the chat's own scroll pinned its bottom, which left a task opened
  // by a link showing only its heading under a screenful of earlier lines
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
  // NEXT, in the row: the walk's ONE button on a task (the owner, 2026-09-29), the same handler as the button it replaces
  useHost(phone);
  useVerbs("next", [{ id: "next", group: "next", label: btnLabel("next"), disabled: !!busy, run: () => onNext(), title: btnHint("next") }]);
  const [read, asking] = useItemAdvice(card, phone);
  // the Assistant's lit button outranks the Advisor's line, as it does over the composer (assistantLight.js)
  const advised = lit ? null : adviceShown(read, { key: card.key, lane: card.lane }, busy);
  // ...and the strip's word and the button it lights are ONE decision, the dock's (advice.stripWord, the UI audit's C2)
  const { none, pick } = stripWord({ speaks: true, busy, shown: advised, lit, advice: read, key: card.key, lane: card.lane });
  return (
    <>
    {pin && <Box aria-hidden sx={{ position: "fixed", inset: 0, zIndex: 1349, bgcolor: "#f6f4f1" }} />}
    {/* focusable, not in the Tab order: a search pick hands focus here, to what it opened (SearchEverything focusDrawn) */}
    <Box ref={box} data-tq-canvas-item={card.key} data-tq-pinned={pin ? "" : undefined} tabIndex={-1}
      sx={{ height: h, display: "flex", flexDirection: "column", minWidth: 0, scrollMarginTop: "8px", outline: "none",
        // ...but a view with NO PANE in it (a stopped agent, a note, a closed task) is only as tall as what it says: the full
        // height left a screen of blank canvas under three short bars (the owner, 2026-09-30: "what's with extra space???").
        // A pane - terminal, agent chat, browser - still gets the one height it is sized for, so the pty is never grown.
        // ...on a phone too: there it stood the full screen under a three-row task, 350px of cream below Context & history
        // (the 2026-10-07 design pass). Pinned (Expand) it keeps the screen.
        ...(!pin ? { "&:not(:has(.xterm, [class*='tq-aui'], canvas, iframe))": { height: "auto", maxHeight: h } } : {}),
        ...(pin ? { position: "fixed", top: 8, left: pin.left, width: pin.width, zIndex: 1350 } : {}) }}>
      {/* a COLUMN that shrinks to the box: the task view inside is a flex column too, so its own scroller gets what is left (TaskPage) */}
      <Box sx={{ flex: "1 1 auto", minHeight: 0, display: "flex", flexDirection: "column" }}>
      {/* `rail`: the rail's own row for this task - the header's status pill wears exactly its mark and word (railStatus.js) */}
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
        onLeave={onLeave} onStay={onStay} />
      </Box>
      {/* THE BUTTONS ARE NOT HERE (layout B, 2026-09-30): the view registers its verbs and Next, and the ONE row above the chat line
          draws them. On a phone the same row rides at the view's foot instead, in both states - the pinned full-screen view covers
          the dock, and the box is sized once, so Expand must not add or take away a row. */}
      {/* ...and the Advisor's line rides WITH the row it lights: pinned over the composer, it stood a screen away (2026-10-19) */}
      {phone && <div className="tq-docked"><div className="tq-strip" data-tq-strip="">
        {lit && <div className="tq-next" role="status" data-tq-advice="lit"><div className="tq-next-txt">{lit.line}</div></div>}
        {!lit && !advised && !none && !busy && asking && card.lane !== "working" && (
          <div className="tq-next" role="status" data-tq-advice-thinking=""><div className="tq-next-txt">Thinking about this one…</div></div>)}
        <AdvisorNext advice={advised} onPropose={onPropose} /><AdviceNone advice={none} /></div>
        <ActionRow inline advised={pick} /></div>}
    </Box>
    </>
  );
}

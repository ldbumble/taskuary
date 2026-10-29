// The agent's browser, live, beside its terminal. Frames come from agent-browser's screencast
// through the server relay (/api/terminals/:sid/browser/ws) and are drawn on a canvas; the
// owner can take the keyboard and mouse when a page asks for something an agent must never
// type - a password, a 2FA code - and hand it back. Snapshot files the frame on the task.
import React, { useEffect, useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import api from "./api.js";
import { label } from "./buttons.js";
import { BORDER, CATPPUCCIN, FAINT, PANEL, mono } from "./theme.jsx";
import { fitFrame, keyMessage, mayShape, mouseMessage, parseMessage, shortUrl, viewportFor, viewportMoved,
  wheelMessage } from "./browserSplit.js";

const wsUrl = (sid) => {
  const t = localStorage.getItem("taskuary_token");
  return `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/terminals/${sid}/browser/ws${t ? `?token=${encodeURIComponent(t)}` : ""}`;
};

export const hostOf = (u) => { try { return new URL(u).host; } catch { return ""; } };

const btn = { ...mono, fontSize: 10.5, lineHeight: 1, px: 0.9, py: 0.45, borderRadius: 1, cursor: "pointer",
  border: `1px solid ${BORDER}`, bgcolor: "transparent", color: "#b9b2a8", "&:hover": { color: "#e1dcd5", borderColor: "#6b655c" } };

// `open`: the parent's poll of browserview.state - the relay refuses a session with no browser, so this
// connects only while that says open (a caller that does not poll leaves it true and always tries).
// `filling`: Taskuary is typing a sign-in into this page (browserview.filling) - the picture holds, and the pane says why
// `waiting`: acts of this browser the hold keeps for the owner's press (browserSplit.heldOn) - Approve / Dismiss on the view itself.
// `turn`: the agent handed the page over (browserSplit.isTurn) - "Your turn" with the hand-back on the view. `ended`: the browser closed;
// the pane stays on its last frame (GeneralWorkspace's view outlives the browser), said as such.
export default function BrowserPane({ sid, taskId, url: url0 = "", open = true, onFold, overlay = false, yourTurn = false, clearRight = false,
  filling = false, waiting = [], turn = null, onHandBack, onDecided, ended = false }) {
  const box = useRef(null), canvas = useRef(null), sendRef = useRef(null), img = useRef(null), fit = useRef(null);
  const [live, setLive] = useState(false);
  const [url, setUrl] = useState(url0);
  /* THE PAGE THE SERVER SAYS IT IS ON. A reopened task mounts this before the parent's first poll, so
     url0 is "" here - and the relay only sends a url message when the page MOVES. The address bar sat
     blank and "an empty tab, live" was drawn over a real, painting page (the 2026-10-02 pane pass). */
  useEffect(() => { if (url0) setUrl(url0); }, [url0]);
  const [driving, setDriving] = useState(false);
  // {t, bad}: a refusal must not read as a success - both used to come out in the same green
  const [note, setNote] = useState(null);
  // they tried to use a page they are only watching - the keyboard went nowhere and said nothing
  const [asked, setAsked] = useState(false);
  const drivingRef = useRef(false);
  drivingRef.current = driving;
  const held = useRef(0);       // the newest frame's seq while this tab is hidden: acked on return
  // null until the daemon says; false = it is up but holding no page, so no frame is coming
  const [attached, setAttached] = useState(null);
  const shape = useRef(null), shapeTimer = useRef(null);

  /* THE PAGE IS GIVEN THIS PANE'S SHAPE, so there is nothing left to letterbox. Debounced, because
     the splitter drags; ignored on failure, because a browser that will not resize still draws. */
  const fitViewport = (claim = false) => {
    if (!box.current || !mayShape(document.hidden, document.hasFocus(), claim)) return;
    const r = box.current.getBoundingClientRect();
    const want = viewportFor(r.width, r.height);
    // a claim re-sends even an unchanged shape: another tab may have reshaped the page since we last did
    if (!want || (!claim && !viewportMoved(shape.current, want))) return;
    clearTimeout(shapeTimer.current);
    shapeTimer.current = setTimeout(() => {
      shape.current = want;
      api.post(`/api/terminals/${sid}/browser/viewport`, want).catch(() => { shape.current = null; });
    }, 400);
  };

  // draw whatever the newest frame is into whatever size the box is now
  const paint = () => {
    const c = canvas.current, im = img.current;
    if (!c || !box.current) return;
    const r = box.current.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    const bw = Math.max(1, Math.floor(r.width)), bh = Math.max(1, Math.floor(r.height));
    if (c.width !== bw * dpr || c.height !== bh * dpr) { c.width = bw * dpr; c.height = bh * dpr; c.style.width = `${bw}px`; c.style.height = `${bh}px`; }
    const ctx = c.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#101010"; ctx.fillRect(0, 0, bw, bh);
    if (!im) return;
    fit.current = fitFrame(im.naturalWidth, im.naturalHeight, bw, bh);
    const f = fit.current;
    ctx.drawImage(im, f.x, f.y, f.w, f.h);
  };

  useEffect(() => {
    if (!open) { setLive(false); return undefined; }
    let ws, closed = false, retry = null, tries = 0;
    const connect = () => {
      ws = new WebSocket(wsUrl(sid));
      const send = (m) => ws.readyState === 1 && ws.send(JSON.stringify(m));
      sendRef.current = send;
      ws.onmessage = (e) => {
        const m = parseMessage(e.data);
        if (!m) return;
        if (m.type === "frame") {
          /* A TAB NOBODY IS LOOKING AT was still paying for all of it: a 50KB decode and a repaint
             every 80ms, and an ack asking for the next one. The stream is ack-paced end to end
             (browserview.py), so holding the ack stops it at the source - Chrome stops capturing -
             and the frame it stopped on is acked the moment the tab comes back. */
          if (document.hidden) { held.current = m.seq; return; }
          const im = new Image();
          im.onload = () => {
            /* LIVE IS THE SOCKET, NOT THE CLOCK. This went grey four seconds after the last frame -
               and an ack-paced stream sends no frame at all while a page sits still, so a sign-in
               form the agent was waiting on read as a dead pane (2026-09-15). It is live until the
               relay closes; a page that is not moving is a page that is not moving. */
            img.current = im; paint(); setLive(true);
            send({ type: "ack", seq: m.seq });       // ack AFTER drawing: the next frame is the page now, not history
          };
          im.src = m.src;
        } else if (m.type === "url" && m.url) setUrl(m.url);
        /* THE STREAM SAYS WHEN IT HAS NOTHING, and we used to drop that on the floor. An
           agent-browser daemon answers its screencast port the moment it launches, whether or not
           a page was ever opened in it - browserview.state() calls that "open", the relay
           connects, and the daemon's first message is {"connected": false, "screencasting":
           false}. No frame ever follows. The pane drew an empty canvas and nothing else, so a
           browser that had simply never been navigated looked identical to a broken one (the
           owner, 2026-09-16, after an agent gave up on `agent-browser open` and asked him to sign
           in himself). Measured on his live session: one status message, zero frames. */
        else if (m.type === "status") setAttached(m.connected !== false);
      };
      /* A dropped socket (a server restart) comes back on its own - while the parent still says the
         browser is OPEN. When the browser itself goes, the relay refuses the handshake (a 403 to the
         page, no close code to read) and this knocked every two seconds for as long as the task stayed
         open (the 2026-10-02 pane pass). Now the poll turning `open` false tears this effect down and
         true brings it back; in between, the retry backs off instead of hammering. */
      ws.onopen = () => { tries = 0; };
      ws.onclose = () => { setLive(false); if (!closed) retry = setTimeout(connect, Math.min(15000, 2000 * 2 ** tries++)); };
    };
    connect();
    return () => { closed = true; clearTimeout(retry); ws?.close(); };
  }, [sid, open]);
  useEffect(() => {
    const wake = () => {
      if (document.hidden) return;
      fitViewport(true);                       // back at this tab: it is the one being watched again
      if (!held.current) return;
      sendRef.current?.({ type: "ack", seq: held.current });
      held.current = 0;
    };
    const focus = () => fitViewport(true);
    document.addEventListener("visibilitychange", wake); window.addEventListener("focus", focus);
    const ro = new ResizeObserver(() => { paint(); fitViewport(); });
    ro.observe(box.current);
    fitViewport();
    return () => { clearTimeout(shapeTimer.current); ro.disconnect();
      document.removeEventListener("visibilitychange", wake); window.removeEventListener("focus", focus); };
  }, [sid]);

  // input reaches the page only while the owner is driving - a stray click on a watched pane
  // must not click the agent's page out from under it
  const forward = (m) => m && drivingRef.current && sendRef.current?.(m);
  // preventScroll: focusing the canvas scrolled the task card 22px under the pointer, so the owner's next clicks missed (2026-10-25)
  const takeOver = () => { setAsked(false); setDriving(true); fitViewport(true); requestAnimationFrame(() => canvas.current?.focus({ preventScroll: true })); };
  /* THE AGENT WAITING ON YOU HANDS YOU THE PAGE. Take over exists so a stray click does not land on a page an agent is
     driving; an agent that asked for a sign-in has stopped and said it will not touch the page, so asking for Take over
     as well was a second gate on one door (the owner, 2026-10-08: "if it asks me to put in info i should be able to do
     that without taking over"). The page is yours while it waits, and goes back to it when you answer - unless you
     took it yourself, which only you hand back. */
  const handed = useRef(false);
  useEffect(() => {
    if (yourTurn && !drivingRef.current) { handed.current = true; setAsked(false); setDriving(true); }
    if (!yourTurn && handed.current) { handed.current = false; setDriving(false); }
  }, [yourTurn]);
  // THE OWNER CAN OPEN A PAGE. The pane had no address bar, so when the agent handed the keyboard
  // over - which it is told to do for a password or a 2FA code - there was nowhere to hand it to:
  // Take over only forwards clicks, and there is nothing to click on about:blank. The task the
  // owner was watching could not be finished from the screen he was watching it on (2026-09-16).
  const [typed, setTyped] = useState("");
  const [going, setGoing] = useState(false);
  const say = (t, bad = false, ms = 3000) => { setNote({ t, bad }); setTimeout(() => setNote(null), ms); };
  const go = async () => {
    const want = typed.trim();
    if (!want || going) return;
    setGoing(true); setNote(null);
    try {
      const r = await api.post(`/api/terminals/${sid}/browser/open`, { url: want });
      setUrl(r.data.url); setTyped("");
    } catch (e) { say(e?.response?.data?.detail || "could not open that page", true, 6000); }
    setGoing(false);
  };
  const onMouse = (e) => {
    if (!drivingRef.current) return void (e.type === "mousedown" && setAsked(true));
    e.preventDefault();                      // ...which also stops the click focusing the canvas, so focus it: the keys follow the click
    if (e.type === "mousedown") canvas.current?.focus({ preventScroll: true });
    forward(mouseMessage(e.type, e.nativeEvent, fit.current));
  };
  const onWheel = (e) => { if (!drivingRef.current) return; e.preventDefault(); forward(wheelMessage(e.nativeEvent, fit.current)); };
  // the page asked for a password, the agent said to type it here, and the keystroke went nowhere
  // and said nothing (the owner, 2026-09-14). Dropping it is right; dropping it in silence is not.
  const onKey = (e) => { if (!drivingRef.current) return void setAsked(true); e.preventDefault(); e.stopPropagation(); forward(keyMessage(e.type, e.nativeEvent)); };

  const snapshot = async () => {
    try {
      const r = await api.post(`/api/terminals/${sid}/browser/snapshot`, { task_id: taskId || null });
      say(`saved ${r.data.name} on the task`);
    } catch (e) { say(e?.response?.data?.detail || "could not save the snapshot", true); }
  };

  return (
    <Box sx={{ position: overlay ? "absolute" : "relative", ...(overlay ? { inset: 0, zIndex: 3 } : {}), display: "flex",
      flexDirection: "column", minHeight: 0, minWidth: 0, border: `1px solid ${driving ? CATPPUCCIN.yellow : BORDER}`,
      borderRadius: 2, overflow: "hidden", bgcolor: "#101010", transition: "border-color .15s" }}>
      {/* toolbar: what page, whether frames are flowing, who is driving */}
      {/* clearRight: the session's full-screen button floats over this corner, and it sat on the fold arrow - the one way
          to put the browser away was under it (2026-10-09) */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1, pr: clearRight ? 5 : 1, py: 0.5, bgcolor: PANEL, borderBottom: `1px solid ${BORDER}`, flexShrink: 0 }}>
        <Box title={live ? "live - frames are flowing" : "connecting…"}
          sx={{ width: 8, height: 8, borderRadius: 99, flexShrink: 0, bgcolor: live ? CATPPUCCIN.green : "#5a554d",
            boxShadow: live ? `0 0 0 3px ${CATPPUCCIN.green}33` : "none", transition: "background .3s" }} />
        <Typography title="The agent opened this page itself - this pane is its browser, watched live.
Take over to drive it yourself; close the session to close it."
          sx={{ ...mono, fontSize: 10.5, color: live ? "#c9c3b9" : FAINT, letterSpacing: 0.3, flexShrink: 0 }}>
          {live ? "LIVE" : "…"}
        </Typography>
        {/* the URL is a FIELD, not a label: click it and type somewhere else. Blank shows where
            the browser is, so it still reads as the address line when nobody is typing. */}
        <Box component="input" value={typed} disabled={going}
          onChange={(e) => setTyped(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") go(); if (e.key === "Escape") setTyped(""); e.stopPropagation(); }}
          placeholder={shortUrl(url) || "type an address to open a page"}
          title={url ? `${url}\n\ntype an address and press Enter to go somewhere else` : "type an address and press Enter to open a page"}
          sx={{ ...mono, fontSize: 11, color: "#c9c3b9", flex: 1, minWidth: 0, bgcolor: "transparent",
            border: "1px solid transparent", borderRadius: 1, px: 0.75, py: 0.25, outline: "none",
            "&::placeholder": { color: "#a8a196", opacity: 1 },
            "&:hover": { borderColor: BORDER }, "&:focus": { borderColor: CATPPUCCIN.yellow, bgcolor: "#1a1a1a" } }} />
        {!!typed.trim() && (
          <Box component="button" onClick={go} disabled={going} sx={{ ...btn, flexShrink: 0 }}>{going ? "opening…" : "Go"}</Box>
        )}
        {note && <Typography title={note.t} sx={{ ...mono, fontSize: 10, flexShrink: 1, minWidth: 0, maxWidth: "45%",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          color: note.bad ? CATPPUCCIN.red : CATPPUCCIN.green }}>{note.t}</Typography>}
        <Box component="button" onClick={() => (driving ? setDriving(false) : takeOver())}
          title={driving ? "give the page back to the agent" : "drive the page yourself - for a password or a code the agent must not type"}
          sx={{ ...btn, ...(driving ? { color: CATPPUCCIN.yellow, borderColor: CATPPUCCIN.yellow } : {}) }}>
          {driving ? "Hand back" : "Take over"}
        </Box>
        <Box component="button" onClick={snapshot} title="keep this frame on the task as an attachment" sx={btn}>Snapshot</Box>
        {onFold && <Box component="button" onClick={onFold} title={overlay ? "back to the terminal" : "fold the browser away - the browser chip above the terminal brings it back"} sx={btn}>{overlay ? "✕" : "›"}</Box>}
      </Box>
      {/* the page. tabIndex so keystrokes land here while driving; the canvas swallows the wheel
          the same way the terminal does, so scrolling the page never scrolls the app */}
      <Box ref={box} onPointerDown={() => fitViewport(true)}
        sx={{ flex: 1, minHeight: 0, position: "relative", cursor: driving ? "default" : "not-allowed" }}>
        <Box component="canvas" ref={canvas} tabIndex={0} onMouseDown={onMouse} onMouseUp={onMouse} onMouseMove={onMouse}
          onWheel={onWheel} onKeyDown={onKey} onKeyUp={onKey} onContextMenu={(e) => e.preventDefault()}
          sx={{ display: "block", outline: "none", position: "absolute", inset: 0 }} />
        {/* BEFORE ANYTHING ARRIVES, it says it is starting: a black box marked "…" is how the owner has described a broken pane
            ("freezes and is just black") - the chip already said "browser · starting…" (2026-10-25) */}
        {attached === null && !live && (
          <Box data-tq-browser-starting="" sx={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
            pointerEvents: "none" }}>
            <Typography sx={{ ...mono, fontSize: 11.5, color: "#a8a196" }}>starting the browser…</Typography>
          </Box>
        )}
        {/* Only before the first frame: once a page has painted, a momentary "not connected"
            is the browser moving between pages, not an empty pane. */}
        {attached === false && !live && (
          <Box sx={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", gap: 0.75, px: 3, textAlign: "center" }}>
            <Typography sx={{ ...mono, fontSize: 11.5, color: "#c9c3b9" }}>the browser is running, with no page open</Typography>
            <Typography sx={{ ...mono, fontSize: 10.5, color: FAINT, lineHeight: 1.6 }}>
              Nothing has been navigated to yet, so there is nothing to show. Type an address up
              there to open one — then take over to drive it yourself.
            </Typography>
          </Box>
        )}
        {/* THE EMPTY PAGE SAYS IT IS EMPTY. A session that asked for a browser gets one on
            about:blank, which paints as a white rectangle labelled LIVE - and nothing said whether
            that was the page or a broken pane (the 2026-09-18 pane pass, defect #1). Frames ARE
            flowing; it is a blank tab, and here is what fills it. Gone the moment a page has an
            address. */}
        {live && (!url || url === "about:blank") && (
          <Box sx={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", pointerEvents: "none",
            alignItems: "center", justifyContent: "center", gap: 0.75, px: 3, textAlign: "center" }}>
            <Typography sx={{ ...mono, fontSize: 11.5, color: "#867f74" }}>an empty tab, live</Typography>
            <Typography sx={{ ...mono, fontSize: 10.5, color: "#a8a196", lineHeight: 1.6 }}>
              The agent opens its pages here. Or type an address above to open one yourself.
            </Typography>
          </Box>
        )}
        {/* WHILE TASKUARY TYPES A SIGN-IN the picture holds and input is dropped (browserview.relay): said, instead of "your turn - click
            the page and type" over a frozen LIVE pane (2026-10-25) */}
        {filling && (
          <Typography data-tq-browser-filling="" sx={{ ...mono, position: "absolute", left: 8, bottom: 6, fontSize: 10, color: "#e1dcd5",
            bgcolor: "#000000cc", px: 0.75, py: 0.25, borderRadius: 1, pointerEvents: "none" }}>
            {`Taskuary is signing in${hostOf(url) ? ` to ${hostOf(url)}` : ""} — the picture resumes in a moment`}
          </Typography>
        )}
        {ended && (
          <Typography data-tq-browser-ended="" sx={{ ...mono, position: "absolute", left: 8, top: 6, fontSize: 10, color: "#e1dcd5",
            bgcolor: "#000000cc", px: 0.75, py: 0.25, borderRadius: 1, pointerEvents: "none" }}>
            the browser closed — this is where it last was; it reopens when the agent next needs it
          </Typography>
        )}
        {driving && !filling && !turn && (
          <Typography sx={{ ...mono, position: "absolute", left: 8, bottom: 6, fontSize: 10, color: CATPPUCCIN.yellow,
            bgcolor: "#000000aa", px: 0.75, py: 0.25, borderRadius: 1, pointerEvents: "none" }}>
            {handed.current ? "your turn — the agent is waiting on you; click the page and type" : "you are driving — the agent's next command still runs; hand back when done"}
          </Typography>
        )}
        {asked && !driving && (
          <Box sx={{ position: "absolute", left: 8, right: 8, bottom: 6, display: "flex", alignItems: "center", gap: 1,
            bgcolor: "#000000cc", border: `1px solid ${CATPPUCCIN.yellow}66`, px: 1, py: 0.5, borderRadius: 1 }}>
            <Typography sx={{ ...mono, fontSize: 10, color: "#e1dcd5", flex: 1 }}>
              You are watching the agent's page — Take over to type on it.
            </Typography>
            <Box component="button" onClick={takeOver}
              sx={{ ...btn, color: CATPPUCCIN.yellow, borderColor: CATPPUCCIN.yellow }}>Take over</Box>
          </Box>
        )}
      </Box>
      {/* WHAT WAITS ON THE OWNER, ON THE PAGE IT WAITS ON - below the page, never over it: a CAPTCHA box under a bar is not one they
          can tick. A held act's Approve / Dismiss, and the owner's turn with its hand-back; both flow back into the agent's chat. */}
      {waiting.map((h) => <HeldBar key={h.id} held={h} onDecided={onDecided} />)}
      {turn && <TurnBar turn={turn} onHandBack={onHandBack} />}
    </Box>
  );
}

// dark, as the page's own frame is: the light toolbar's light text would read faint here, where the one thing to read is the ask
const bar = { display: "flex", alignItems: "center", flexWrap: "wrap", gap: 1, px: 1.25, py: 0.75, flexShrink: 0, bgcolor: "#1c1b19",
  borderTop: `1px solid ${CATPPUCCIN.yellow}88` };
const barText = { fontSize: 12.5, color: "#e1dcd5", flex: "1 1 220px", minWidth: 0, lineHeight: 1.4 };
const press = { ...btn, fontSize: 11.5, px: 1.25, py: 0.6 };
const primary = { ...press, color: "#101010", bgcolor: CATPPUCCIN.yellow, borderColor: CATPPUCCIN.yellow,
  "&:hover": { bgcolor: "#f3d98f", borderColor: "#f3d98f", color: "#101010" } };
const failed = (e, data) => data?.send_error || e?.response?.data?.detail || (e ? "That did not go through - nothing was done. Try again." : "");

// A HELD ACT (browsergate.check): Approve runs that exact command in this browser and the agent is told what happened - it goes on
// in the same conversation by itself; Dismiss tells it the step was not done. The existing decide road, the same as the card's.
function HeldBar({ held: h, onDecided }) {
  const [busy, setBusy] = useState(""), [err, setErr] = useState("");
  const decide = async (verb) => {
    if (busy) return;
    setBusy(verb); setErr("");
    try {
      const { data } = await api.post(`/api/reviews/${h.id}/decide`, { verb, final_text: null, note: null, cc: null, anyway: false }, { timeout: 120000 });
      if (data?.send_error) { setErr(failed(null, data)); setBusy(""); onDecided?.(); return; }
      onDecided?.();
    } catch (e) { setErr(failed(e)); setBusy(""); }
  };
  return (
    <Box data-tq-browser-held={h.id} sx={bar}>
      <Typography sx={barText} title={[h.url, h.why].filter(Boolean).join("\n")}>
        <Box component="span" sx={{ color: CATPPUCCIN.yellow, fontWeight: 600 }}>Approve: </Box>{h.what}
        {h.why && <Box component="span" sx={{ color: "#a8a196" }}>{` — held because ${h.why}`}</Box>}
      </Typography>
      <Box component="button" onClick={() => decide("approve")} disabled={!!busy} sx={primary}
        title="Taskuary runs exactly this in the agent's browser, and the agent carries on from there">{busy === "approve" ? "running…" : label("approve", "action")}</Box>
      <Box component="button" onClick={() => decide("reject")} disabled={!!busy} sx={press}
        title="Not done - the agent is told, and carries on without it or asks you">{busy === "reject" ? "…" : "Dismiss"}</Box>
      {err && <Typography role="alert" sx={{ ...mono, fontSize: 10.5, color: CATPPUCCIN.red, flexBasis: "100%" }}>{err}</Typography>}
    </Box>
  );
}

// THE OWNER'S TURN (browserview.your_turn): the page is theirs to click and type on (yourTurn hands it over), and Done hands it back -
// the agent's next message, so it looks at the page and goes on.
function TurnBar({ turn, onHandBack }) {
  const [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const back = async () => {
    if (busy) return;
    setBusy(true); setErr("");
    try { await onHandBack?.(); } catch (e) { setErr(failed(e)); setBusy(false); }
  };
  useEffect(() => { setBusy(false); setErr(""); }, [turn?.request_id]);
  return (
    <Box data-tq-browser-turn={turn.request_id} sx={bar}>
      <Typography sx={barText}>
        <Box component="span" sx={{ color: CATPPUCCIN.yellow, fontWeight: 600 }}>{turn.text || "Your turn in the browser"}</Box>
        <Box component="span" sx={{ color: "#a8a196" }}> · click the page and do it, then hand it back</Box>
      </Typography>
      <Box component="button" onClick={back} disabled={busy} sx={primary}
        title="The agent looks at the page as you left it and carries on">{busy ? "handing back…" : "Done — hand back to the agent"}</Box>
      {err && <Typography role="alert" sx={{ ...mono, fontSize: 10.5, color: CATPPUCCIN.red, flexBasis: "100%" }}>{err}</Typography>}
    </Box>
  );
}

// THE TASK'S LAST BROWSER VIEW, once no browser is showing (browserview.keep_frame): the page its agent last stood on, folded to one
// line on a phone, and kept folded or open as the owner left it. Nothing at all when the task kept none. Drawn above a live session's
// conversation until its browser opens (SessionPane), and on the ended agent's Result (TaskPage).
const lastFoldKey = (tid) => `tq-browser-last-folded.${tid}`;
export function LastView({ taskId, sid = "", narrow = false }) {
  const [last, setLast] = useState(null);
  const [open, setOpen] = useState(() => { try { const v = localStorage.getItem(lastFoldKey(taskId)); return v === null ? null : v !== "1"; } catch { return null; } });
  useEffect(() => {
    let live = true;
    api.get(`/api/tasks/${taskId}/browser/last`).then((r) => live && setLast(r.data?.src ? r.data : null)).catch(() => {});
    return () => { live = false; };
  }, [taskId, sid]);
  if (!last) return null;
  const shown = open === null ? !narrow : open;
  const toggle = () => { setOpen(!shown); try { localStorage.setItem(lastFoldKey(taskId), shown ? "1" : "0"); } catch { /* private mode */ } };
  return (
    <Box data-tq-browser-last="" sx={{ flex: "0 0 auto", mb: 1, border: `1px solid ${BORDER}`, borderRadius: 2, overflow: "hidden", bgcolor: "#101010" }}>
      <Box component="button" onClick={toggle} aria-expanded={shown}
        sx={{ ...mono, width: "100%", display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.6, fontSize: 10.5, cursor: "pointer",
          border: 0, bgcolor: "#1a1a1a", color: "#c9c3b9", textAlign: "left", "&:hover": { color: "#e1dcd5" } }}>
        <Box sx={{ width: 7, height: 7, borderRadius: 99, bgcolor: "#5a554d", flexShrink: 0 }} />
        <Box component="span" sx={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {`browser · where the agent last was${last.url ? ` · ${shortUrl(last.url, 48)}` : ""}`}</Box>
        <Box component="span" sx={{ flexShrink: 0 }}>{shown ? "Hide" : "Show"}</Box>
      </Box>
      {shown && <Box component="img" src={last.src} alt={`The agent's browser, last on ${last.url || "a page"}`}
        sx={{ display: "block", width: "100%", maxHeight: "min(46vh, 480px)", objectFit: "contain", bgcolor: "#101010" }} />}
    </Box>
  );
}

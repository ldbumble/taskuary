// FIRST RUN, on the assistant canvas: three plain questions - what AI do you have, what email do you have, any other
// connection - each answered by clicking one of the Connections page's own cards.
//
// The owner, 2026-10-14: "Think about a idiot user who knows nothing about nothing and he should setup this app in 2 steps
// ... use the advisor as well to say next steps ... it should never drop the user". And 2026-10-15: "Don't create new ui. keep
// the same as we have in connections but just show them/tell what to do next using the advisor ... like what ai do you have?
// what email do you have? any other connection you would like to setup". So nothing here draws a card: ConnCard is the
// catalogue's, logos and status included, and a clicked card opens the card's own setup (ChannelDetail). The question is the
// Advisor's line on top, and it is the server's (firstrun.state) - never guessed here.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api";
import { DIM } from "./theme.jsx";
import { CardGrid, ChannelDetail, ConnCard, connCardOf } from "./ConnectorsView.jsx";
import { CliPane, useCliSetup } from "./cliSetup.jsx";
import { focusOf } from "./firstRunFocus.js";
import { SETUP_AI } from "./aiShelf.js";

const CHECK_MS = 90_000;            // a card test is a minute at most server-side; past this we say so instead of spinning
const INSTALL_MS = 6 * 60_000;
const FIRST = 4;                    // the four most people have; More shows the rest of the same shelf
const errText = (e) => e?.response?.data?.detail || (e?.code === "ECONNABORTED" ? "That took too long." : e?.message) || "That didn't work.";
// the logo each CLI wears is its maker's - the same mark as that maker's API card on Connections
const CLI_LOGO = { claude: "anthropic", codex: "openai", gemini: "gemini", copilot: "github" };
const MAIL_TYPES = ["outlook", "gmail", "imap"];
const OTHER_TYPES = ["whatsapp", "teams", "slack", "telegram", "github", "imessage", "discord", "google_chat", "mattermost",
  "rocketchat", "matrix", "gitlab", "jira", "linear", "asana", "trello", "notion", "todoist", "clickup", "monday"];

// THE QUESTION, in the Advisor's own line (ActionRow's AdvisorNext draws the same row over the composer)
const Ask = ({ text }) => (
  <div className="tq-next" role="status" data-tq-firstrun-next="" style={{ justifyContent: "flex-start" }}>
    <div className="tq-next-txt">{text}</div>
  </div>
);

// one shelf: the first four cards, and More for the rest of it - the catalogue's card, never one of our own. A card that is
// open stands alone with its setup under it: under all twenty-one, the form landed a screen away from the card that opened it
function Shelf({ cards, more, opened, detail, onAll, allLabel = "Show all" }) {
  const [all, setAll] = useState(false);
  const one = opened && cards.find((c) => c.key === opened);
  const shown = one ? [one] : all ? cards : cards.slice(0, FIRST);
  const small = { color: DIM, fontSize: 12.5 };
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <CardGrid>{shown.map((c) => <ConnCard key={c.key} c={c} />)}</CardGrid>
      {one ? <>{detail}<Box><Button size="small" onClick={onAll} sx={small}>{allLabel}</Button></Box></>
        : cards.length > FIRST && <Box><Button size="small" onClick={() => setAll((v) => !v)} sx={small}>
          {all ? "Show fewer" : `${more} (${cards.length - FIRST})`}</Button></Box>}
    </Box>
  );
}

// `revisit`: opened from Set up Taskuary on an install that may be set up already - every question stays open, so the AI or
// the mailbox can be changed from the same cards
export default function FirstRun({ onWalk, onChanged, revisit = false }) {
  const [st, setSt] = useState(null), [err, setErr] = useState("");
  const [conns, setConns] = useState([]), [sources, setSources] = useState([]);
  const [busy, setBusy] = useState(""), [said, setSaid] = useState("");     // a pick in flight says so on the Advisor line
  const [open, setOpen] = useState(null);                                   // {id, simple}: a card's own setup, below its shelf
  const [browse, setBrowse] = useState(false);                              // "Pick a different AI": every card again
  const { openSetup, opening, pane, setPane, note } = useCliSetup();
  const was = useRef("");
  const reload = useCallback(async () => {
    try {
      const [f, c, s] = await Promise.all([api.get("/api/setup/first-run", { timeout: 30_000 }), api.get("/api/connectors"), api.get("/api/sources")]);
      setSt(f.data); setConns(c.data.data || []); setSources(s.data.data || []); setErr("");
    } catch (e) { setErr(`${errText(e)} Retrying…`); }
  }, []);
  useEffect(() => { reload(); }, [reload]);
  // while mail is being read - or a Microsoft sign-in may finish in another tab - read again until it is done
  useEffect(() => {
    if (!st || st.step === "done" || st.step === "ai") return undefined;
    const id = setTimeout(reload, st.step === "reading" ? 3000 : 5000);
    return () => clearTimeout(id);
  }, [st, reload]);
  // a step moved: the rail reloads and says what is next, and so does the top bar's chip (TaskHubPage listens) - it went stale
  useEffect(() => {
    if (!st || st.step === was.current) return;
    if (was.current) { onChanged?.(); window.dispatchEvent(new Event("tq-setup-changed")); setOpen(null); }
    was.current = st.step;
  }, [st, onChanged]);

  // A CLI CARD IS ONE CLICK: connect, test, make it the AI (firstrun.choose_cli) - or install it first when it is not here
  const pick = async (ai) => {
    if (!ai.installed && ai.install && !ai.done) { install(ai); return; }
    setBusy(ai.name); setOpen(null); setBrowse(false);
    setSaid(`Checking that ${ai.title} works - this can take up to a minute…`);
    try { await api.post("/api/setup/first-run/ai", { name: ai.name }, { timeout: CHECK_MS }); }
    catch (e) { setBusy(""); setSaid(""); setErr(`${errText(e)} Click the card to try again.`); return; }
    setBusy(""); setSaid(""); reload();               // what happened is the server's line now - and it survives a reload
  };
  const install = async (ai) => {
    setBusy(ai.name); setSaid(`Installing ${ai.title}… this takes about a minute.`);
    try {
      await api.post("/api/cli/install", { name: ai.install });
      const until = Date.now() + INSTALL_MS;
      for (;;) {
        await new Promise((r) => setTimeout(r, 2500));
        const { data } = await api.get("/api/cli/install/state");
        if (data.phase === "installing" && data.detail) setSaid(`${data.detail} (this can take a few minutes)`);
        if (data.phase === "done") break;
        if (data.phase === "failed") throw new Error(data.detail || "the installer stopped");
        if (Date.now() > until) throw new Error("the install is taking too long");
      }
      setBusy(""); await pick({ ...ai, installed: true, done: true });   // installed: test it right away - one click, the whole step
    } catch (e) { setBusy(""); setSaid(""); setErr(`${ai.title} didn't install: ${errText(e)} Click its card to try again, or pick another AI.`); }
  };

  if (!st) return <Box sx={{ p: 2, display: "flex", gap: 1, alignItems: "center" }}><CircularProgress size={16} />
    <Typography sx={{ color: DIM }}>{err || "Getting set up…"}</Typography></Box>;

  const byType = (types) => types.flatMap((t) => conns.filter((c) => c.Type === t));
  // plain: the same card, its state in a first-time owner's words (connCardOf) - the Connections page keeps its own
  const card = (c, simple) => connCardOf(c, sources, () => setOpen((o) => (o?.id === c.ConnectorId ? null : { id: c.ConnectorId, simple })), true);
  // the CLIs read as cards the catalogue would draw: the AI's name, its maker's logo, and its state in the same plain words
  const fix = st.fix;
  const stateOf = (ai) => (busy === ai.name ? ["on", "Checking it works…"]
    : fix?.name === ai.name ? ["failing", fix.fix === "signin" ? "Needs sign-in" : fix.fix === "install" ? "Not installed - click to install" : "Not answering"]
    : st.step !== "ai" && st.brain.name === ai.title ? ["on", "Connected"]
    : ["off", ai.installed ? "Not set up - on this computer" : "Not installed - click to install"]);
  const cliCards = st.ais.map((ai) => {
    const [state, words] = stateOf(ai);
    return { key: `cli-${ai.name}`, title: ai.title, channel: CLI_LOGO[ai.name] || "cli", go: busy ? undefined : () => pick(ai),
      state, plain: true, desc: `${words} · ${ai.sub}` };
  });
  const ai = [...cliCards, ...byType(SETUP_AI).map((c) => card(c, true))];      // st.ais leads with the four most people pay for
  const mail = byType(MAIL_TYPES).map((c) => card(c, true));
  const other = byType(OTHER_TYPES).map((c) => card(c, false));
  const conn = open && conns.find((c) => c.ConnectorId === open.id);
  const detail = conn && (
    <Box sx={{ mt: 0.5 }}>
      <ChannelDetail key={conn.ConnectorId} conn={conn} sources={sources} reload={reload} simple={open.simple}
        onBack={() => { setOpen(null); reload(); }} onConnected={reload} />
    </Box>
  );
  const q = st.step === "ai" ? "ai" : st.step === "email" ? "mail" : "other";
  // THE PICKED CARD STANDS ALONE with its one next step under it (the owner, 2026-10-15: "i clicked chat gpt the other boxes should
  // go away, otherwise it looks like nothing happens ... you act something happens, show whats next step clearly. any error lead them
  // to fix"). Checking: say so. Needs sign-in: one button that runs the CLI's own login, and the check runs by itself when it ends.
  const focus = !open && focusOf(st, busy, browse);
  const fixed = fix && (st.ais.find((a) => a.name === fix.name) || { name: fix.name, title: fix.title, installed: true });
  const check = () => fixed && pick(fixed);
  // the login ended: check it, and if it still fails the Sign in button is back rather than a pane that has exited
  const ended = () => { setPane(null); check(); };
  const signin = q === "ai" && fix?.fix === "signin" && fix.setup;
  const cli = signin && { name: fix.name, setup: fix.setup, installed: true };
  const cliDetail = busy ? (
    <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}><CircularProgress size={14} />
      <Typography sx={{ color: DIM, fontSize: 13.5 }}>Checking it works - this can take up to a minute.</Typography></Box>
  ) : signin ? (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1, alignItems: "flex-start" }}>
      {!pane?.sid ? <>
        {/* the why is the Advisor's line above; under the card is only the thing to press */}
        <Button variant="contained" disableElevation disabled={!!opening}
          onClick={() => openSetup({ ...cli, login: true })}>{opening ? "Opening…" : `Sign in to ${fix.title}`}</Button>
      </> : <>
        <Typography sx={{ fontSize: 14 }}>Sign in below - a browser window may open; finish there. When the sign-in ends, Taskuary
          checks {fix.title} by itself.</Typography>
        <Box sx={{ width: "100%" }}><CliPane pane={pane} height="34vh" hint={false} onExit={ended} /></Box>
        <Button size="small" onClick={check}>Check now</Button>
      </>}
      {note?.bad && <Typography sx={{ fontSize: 13, color: "#9b2c2c" }}>{note.text} - try again, or pick a different AI.</Typography>}
    </Box>
  ) : null;
  const shelf = (k, cards, more) => (revisit || q === k) && (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      {revisit && <Typography sx={{ fontWeight: 600, fontSize: 15 }}>{
        { ai: "What AI do you have?", mail: "What email do you have?", other: "Any other connection you'd like to set up?" }[k]}</Typography>}
      <Shelf cards={cards} more={more} opened={(open && `c${open.id}`) || (k === "ai" && focus) || null}
        detail={open ? detail : cliDetail} allLabel={k === "ai" ? "Pick a different AI" : "Show all"}
        onAll={() => { setOpen(null); if (k === "ai") setBrowse(true); }} />
    </Box>
  );
  return (
    <Box data-tq-firstrun={st.step} sx={{ display: "flex", flexDirection: "column", gap: 1.75, maxWidth: 980 }}>
      <Ask text={said || err || st.next} />
      {shelf("ai", ai, "More AI")}
      {shelf("mail", mail, "More email")}
      {shelf("other", other, "More connections")}
      {(st.step === "reading" || st.step === "done") && (
        <Box sx={{ display: "flex", gap: 1.25, alignItems: "center", flexWrap: "wrap" }}>
          {st.step === "reading" && <><CircularProgress size={16} /><Typography sx={{ color: DIM }}>
            {st.sorting ? `Sorting ${st.sorting} email${st.sorting === 1 ? "" : "s"}…` : "Reading your mail…"}</Typography></>}
          <Button variant="contained" disableElevation disabled={st.step !== "done"} onClick={onWalk}>Walk me through my tasks</Button>
        </Box>
      )}
    </Box>
  );
}

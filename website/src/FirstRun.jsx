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
import { focusOf, signinUrl } from "./firstRunFocus.js";
import FirstRunAbout from "./FirstRunAbout.jsx";
import SetupDone from "./SetupDone.jsx";
import CanvasBrowse from "./CanvasBrowse.jsx";
import { writeSetupLine } from "./setupLine.js";
import { useVerbs } from "./actionRow.js";
import { doneOf, frontierOf, navMoves, nextOf, openAt, pickOf, prevOf, reachable, requiredDone } from "./setupSteps.js";
import { openBugReport } from "./bugReportOpen.js";
import { SETUP_AI } from "./aiShelf.js";
import { label as btnLabel } from "./buttons.js";
import { plural } from "./timeWords.js";

const CHECK_MS = 200_000;           // its test, then one test email sorted (firstrun._prove, 90s at most): past this we say so
const INSTALL_MS = 6 * 60_000;
const FIRST = 4;                    // the four most people have; More shows the rest of the same shelf
const errText = (e) => e?.response?.data?.detail || (e?.code === "ECONNABORTED" ? "That took too long." : e?.message) || "That didn't work.";
// the logo each CLI wears is its maker's - the same mark as that maker's API card on Connections
const CLI_LOGO = { claude: "anthropic", codex: "openai", gemini: "gemini", copilot: "github" };
const MAIL_TYPES = ["outlook", "gmail", "imap"];

// THE QUESTION, in the Advisor's own line (ActionRow's AdvisorNext draws the same row over the composer)
const Ask = ({ text }) => (
  <div className="tq-next" role="status" data-tq-firstrun-next="" style={{ justifyContent: "flex-start" }}>
    <div className="tq-next-txt">{text}</div>
  </div>
);

// one shelf: the first four cards, and More for the rest of it - the catalogue's card, never one of our own. A card that is
// open stands alone with its setup under it: under all twenty-one, the form landed a screen away from the card that opened it
// `group`: {label, cards} drawn under the shelf with a heading of its own - the coding tools, after the AI most people have
function Shelf({ cards, more, opened, detail, onAll, allLabel = "Show all", group = null }) {
  const [all, setAll] = useState(false);
  const every = group ? [...cards, ...group.cards] : cards;
  const one = opened && every.find((c) => c.key === opened);
  const shown = one ? [one] : all ? cards : cards.slice(0, FIRST);
  const small = { color: DIM, fontSize: 12.5 };
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <CardGrid>{shown.map((c) => <ConnCard key={c.key} c={c} />)}</CardGrid>
      {one ? <>{detail}<Box><Button size="small" onClick={onAll} sx={small}>{allLabel}</Button></Box></>
        : cards.length > FIRST && <Box><Button size="small" onClick={() => setAll((v) => !v)} sx={small}>
          {all ? "Show fewer" : `${more} (${cards.length - FIRST})`}</Button></Box>}
      {!one && group?.cards.length > 0 && <>
        <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: DIM, mt: 1 }} data-tq-firstrun-group="">{group.label}</Typography>
        <CardGrid>{group.cards.map((c) => <ConnCard key={c.key} c={c} />)}</CardGrid>
      </>}
    </Box>
  );
}

// `revisit`: opened from Set up Taskuary on an install that may be set up already - every question stays open, so the AI or
// the mailbox can be changed from the same cards
export default function FirstRun({ onWalk, onFinish, onChanged, revisit = false }) {
  const [st, setSt] = useState(null), [err, setErr] = useState("");
  const [loadErr, setLoadErr] = useState(""), [fails, setFails] = useState(0);   // the FIRST load failing: said, retried, Try again
  const [conns, setConns] = useState([]), [sources, setSources] = useState([]);
  const [busy, setBusy] = useState(""), [said, setSaid] = useState("");     // a pick in flight says so on the Advisor line
  const [open, setOpen] = useState(null);                                   // {id, simple}: a card's own setup, below its shelf
  const [browse, setBrowse] = useState(false);                              // "Pick a different AI": every card again
  const [url, setUrl] = useState(""), [details, setDetails] = useState(false);   // the login's own link; its terminal, hidden
  const [signing, setSigning] = useState(null);                             // {cid, flow, url}: ChatGPT's browser sign-in under way
  const [aboutLine, setAboutLine] = useState("");                           // About your work's question, for the Advisor's line
  // the step's pick (pickOf): its title as state, so the row has it in the pass the shelf is drawn; its press, the card's own
  const [pickTitle, setPickTitle] = useState(""), pickRef = useRef(null);
  // ONE STEP ON THE CANVAS (setupSteps.ORDER: ai, mail, about, other), Back and Next in the row, and A STEP THAT COMPLETES MOVES ON
  // (the owner, 2026-10-15: "always have next/back button if possible and move to next step once one is complete"). Going back to
  // change the AI used to leave no way forward but the rail.
  const [view, setView] = useState(null);
  const go = useCallback((v) => { setView(v); setOpen(null); setBrowse(false); }, []);
  // a step on the rail opens only once the steps before it are done (SetupSteps disables the rest): About your work pressed from Your
  // AI, then saved, put Setup complete over a day with no AI and no mail (the non-coder audit, 2026-10-17)
  const stRef = useRef(null);
  useEffect(() => {
    const on = (e) => { const v = e.detail === "finish" ? "other" : e.detail; if (!stRef.current || reachable(stRef.current, v)) go(v); };
    window.addEventListener("tq-setup-go", on);
    return () => window.removeEventListener("tq-setup-go", on);
  }, [go]);
  // MORE CONNECTIONS IS THE CONNECTIONS PAGE (its sections, its cards, their own setup), and the Advisor says which to pick from the
  // survey and the job (firstrun.suggest_connections) - the owner, 2026-10-15: "for other connectors it should show this screen with
  // advisor suggesting based off of your job what to choose"
  const [browseSt, setBrowseSt] = useState({}), [connSug, setConnSug] = useState(null);     // {line, picks}
  useEffect(() => {
    if (view !== "other" || connSug) return undefined;
    let on = true;
    api.post("/api/setup/first-run/suggest-connections", {}, { timeout: 120_000 })
      .then(({ data }) => on && setConnSug(data || { line: "", picks: [] })).catch(() => on && setConnSug({ line: "", picks: [], failed: true }));
    return () => { on = false; };
  }, [view, connSug]);
  const connLine = connSug?.line || "";
  // what setup says next is the ADVISOR'S line, in its bar over the row (setupLine.js): written every render, cleared on the way out
  const lineRef = useRef("");
  useEffect(() => { writeSetupLine(lineRef.current); });
  useEffect(() => () => writeSetupLine(""), []);
  const prevSt = useRef(null);
  useEffect(() => {
    if (!st) return;
    const was = prevSt.current; prevSt.current = st;
    if (view === null) { setView(openAt(st, revisit || st.dismissed)); return; }
    if (!was) return;
    // a working AI moves on to the email - a first one, or a new one picked on the way back; the mail coming in moves on to About
    const newAi = st.step !== "ai" && (was.step === "ai" || (was.brain?.name && st.brain?.name && was.brain.name !== st.brain.name));
    if (view === "ai" && newAi) go("mail");
    else if (view === "mail" && !doneOf(was, "mail") && doneOf(st, "mail")) go("about");
  }, [st]);   // eslint-disable-line react-hooks/exhaustive-deps
  const { openSetup, opening, pane, setPane, note } = useCliSetup();
  const was = useRef("");
  // FINISH IS THE OWNER'S PRESS, in the row under the canvas like every other move (the owner, 2026-10-15: "we should be able to
  // dismiss the walk through and then the morning digest screen will show up ... button should be on bottom like normal"): until
  // then the canvas stays setup, never a half-finished day. Walking into the tasks finishes it too.
  // ...and refused, with what to do, while there is no AI or no mail (409): a day with neither never fills
  const finishThen = (go) => async () => {
    try { await api.post("/api/setup/first-run/finish"); }
    catch (e) { if (e?.response?.status === 409) { setErr(errText(e)); return; } /* else the canvas still moves on; the flag is set next time */ }
    window.dispatchEvent(new Event("tq-setup-changed")); go?.();
  };
  const reopened = revisit || !!st?.dismissed;
  const fix = st?.fix;
  const fixed = fix && (st.ais.find((a) => a.name === fix.name) || { name: fix.name, title: fix.title, installed: true });
  const nav = navMoves(st, view, reopened);
  const VERB = {
    back: { label: "Back", tone: "s", run: () => go(prevOf(view)), title: "The step before" },
    next: { label: "Next", tone: "p", run: () => go(nextOf(view)), title: "The next step" },
    walk: { label: "Walk me through my tasks", tone: "p", run: finishThen(onWalk), title: "Everything waiting, most important first" },
    finish: { label: reopened ? "Back to my day" : "Finish setup", tone: "p", run: finishThen(onFinish),
      title: "Setup is done - the canvas shows your day. Setup on the top bar opens this again." },
  };
  // Back takes the row's leading slot (the one Next takes on a card): the row shows two moves of a kind and folds the rest behind a
  // ▾, and Back, Walk and Finish as one kind put Finish setup behind it on the last step
  // ...and ADVICE COMES WITH ITS BUTTON (the owner, 2026-10-15: "making buttons available when necessary"): each connection the
  // Advisor names opens its section on the Connections page below; one Taskuary cannot connect yet gets no button
  // every one it names that can be connected - it named five and gave three buttons (the Advisor audit, 2026-10-15)
  // ...and NOT AS BUTTONS IN THE ROW: the row keeps its own moves (the owner, 2026-10-16: "No such buttons. If it suggest systems
  // then you can do it in search ... don't like new buttons besides for what there was before") - the picks it can connect are
  // typed into the catalogue's own search, so their cards are what the page shows
  const typed = useRef(false);
  useEffect(() => {
    const names = (connSug?.picks || []).filter((x) => !x.planned).slice(0, 5).map((x) => x.title);
    if (view !== "other" || typed.current || !names.length) return;
    typed.current = true;
    setBrowseSt({ q: names.join(", "), section: null, open: null });
  }, [view, connSug]);
  // ...and the fix the line names is a button too (the Advisor audit, 2026-10-15): "Press Install" and "Press Change" named buttons
  // setup did not have - an AI to install, and a brain failing on the real mail, which only Back three times could reach
  const fixRow = !st ? [] : [
    ...(view === "ai" && fix?.fix === "install" && fixed?.install && !busy ? [{ id: "setup:install", group: "decide", tone: "p", label: `Install ${fixed.title}`,
      title: "Installs it on this computer, then checks it works", run: () => install(fixed) }] : []),
    // (on Setup complete its big button is Change AI itself - SetupDone)
    ...(view !== "ai" && view !== "done" && st.ai_error ? [{ id: "setup:change-ai", group: "decide", tone: "p", label: "Change AI",
      title: "Back to Your AI, to pick one that sorts your mail", run: () => go("ai") }] : []),
  ];
  // ...and THE STEP'S PICK, lit, when nothing else is (setupSteps.pickOf - the shelf's first card, by its own title; drawn below)
  const pickRow = pickTitle && !fixRow.length ? [{ id: "setup:pick", group: "decide", tone: "p",
    label: `Connect ${pickTitle}`, title: "Opens its setup here - the same as pressing its card", run: () => pickRef.current?.run?.() }] : [];
  // ONE filled move: a fix leads when there is one; reopened setup's Back to my day is outlined beside Next
  const toneOf = (m) => (fixRow.length && m.id !== "back" ? "s" : m.id === "finish" && view !== "other" ? "s" : VERB[m.id].tone);
  // ABOUT YOUR WORK MOVES ITS OWN QUESTIONS (FirstRunAbout's Back and Next, one question a screen): only the way back to the day stays
  // ...and SETUP COMPLETE has its one big button on the canvas (SetupDone), nothing in the row
  const navShown = view === "done" ? [] : view === "about" ? nav.filter((m) => m.id === "finish") : nav;
  useVerbs("setup", [...navShown.map((m) => ({ id: `setup:${m.id}`, group: m.id === "back" ? "next" : "decide", disabled: !!m.disabled, why: m.why || "",
    ...VERB[m.id], tone: toneOf(m) })), ...fixRow, ...pickRow], navShown.length + fixRow.length + pickRow.length > 0);
  // an error is about the step it happened on: it followed the owner to the next one (the Advisor audit, 2026-10-15)
  useEffect(() => { setErr(""); }, [view]);
  // THE RAIL MARKS WHAT IS ON THE CANVAS (SetupSteps): it said About your work while the owner was back on the email step
  useEffect(() => {
    if (!view) return;
    const at = view === "done" ? "finish" : view;            // the rail's last row is where Setup complete stands
    window.__tqSetupShown = at;
    window.dispatchEvent(new CustomEvent("tq-setup-shown", { detail: at }));
  }, [view]);
  // THE SIGN-IN IS A STEP, NOT A TERMINAL (the owner, 2026-10-15: "terminal is broken display"): the login's link is read off its
  // screen and offered as a link; the pane stays mounted, hidden, so its end still runs the check
  useEffect(() => {
    if (!pane?.sid) { setUrl(""); setDetails(false); return undefined; }
    let on = true;
    const read = () => api.get(`/api/terminals/${pane.sid}/screen`, { params: { lines: 60 } })
      .then(({ data }) => { const u = signinUrl(data); if (on && u) setUrl(u); }).catch(() => {});
    read(); const id = setInterval(read, 2000);
    return () => { on = false; clearInterval(id); };
  }, [pane?.sid]);
  // A BACKGROUND READ NEVER CLEARS AN ERROR (the non-coder audit, 2026-10-17): the 3-5s poll wiped the Change AI road's error before
  // it could be read. `err` goes on a user's own press or a step change; the first load's failure is its own (loadErr).
  const reload = useCallback(async () => {
    try {
      const [f, c, s] = await Promise.all([api.get("/api/setup/first-run", { timeout: 30_000 }), api.get("/api/connectors"), api.get("/api/sources")]);
      setSt(f.data); setConns(c.data.data || []); setSources(s.data.data || []); setLoadErr("");
      return f.data;
    } catch (e) { setLoadErr(errText(e)); setFails((n) => n + 1); return null; }
  }, []);
  useEffect(() => { reload(); }, [reload]);
  // ...and a first load that failed is tried again by itself - it said "Retrying…" and never did
  useEffect(() => {
    if (st || !fails) return undefined;
    const id = setTimeout(reload, 3000);
    return () => clearTimeout(id);
  }, [st, fails, reload]);
  // while mail is being read - or a Microsoft sign-in may finish in another tab, or a key is being tried on an AI card - read again
  useEffect(() => {
    if (!st || st.step === "done" || (st.step === "ai" && !open)) return undefined;
    const id = setTimeout(reload, st.step === "reading" ? 3000 : 5000);
    return () => clearTimeout(id);
  }, [st, reload, open]);
  // a step moved: the rail reloads and says what is next, and so does the top bar's chip (TaskHubPage listens) - it went stale
  // ...and About your work saved is a step too: keyed on the step alone, the chip said "about your work" after it (2026-10-16)
  useEffect(() => {
    const at = st && `${st.step}|${!!st.about_done}`;
    if (!st || at === was.current) return;
    if (was.current) { onChanged?.(); window.dispatchEvent(new Event("tq-setup-changed")); setOpen(null); }
    was.current = at;
  }, [st, onChanged]);

  // A CLI CARD IS ONE CLICK: connect, test, make it the AI (firstrun.choose_cli) - or install it first when it is not here
  const pick = async (ai) => {
    setErr("");
    if (!ai.installed && ai.install && !ai.done) { install(ai); return; }
    setBusy(ai.name); setOpen(null); setBrowse(false);
    setSaid(`Checking that ${ai.title} works - it sorts one test email, up to two minutes…`);
    try { await api.post("/api/setup/first-run/ai", { name: ai.name }, { timeout: CHECK_MS }); }
    catch (e) { setBusy(""); setSaid(""); setErr(`${errText(e)} Pick it again to retry.`); return; }
    await reload(); setBusy(""); setSaid("");         // what happened is the server's line now; cleared only once it is drawn (no flicker back)
  };
  // CHATGPT IS A BROWSER SIGN-IN, not a CLI in a terminal (the owner, 2026-10-15: "for chatgpt regular why are you opening a
  // terminal??? no need for that. it's a regular oauth setup"): its card's own sign-in (chatgptauth), then tested and made the AI
  // ONE SIGN-IN AT A TIME, ITS OWN TOKEN: Cancel (or leaving setup) drops it, and the loop checks after every wait - it kept polling
  // past Cancel, found no sign-in in progress, and put up a red "didn't finish" on the very road the card recommends (2026-10-17)
  const signRef = useRef(null);
  useEffect(() => () => { signRef.current = null; }, []);
  const planSignin = async (c) => {
    setErr(""); setOpen(null); setBrowse(false);
    const me = {}; signRef.current = me;
    const gone = () => signRef.current !== me;
    let flow;
    try { flow = (await api.post(`/api/connectors/${c.ConnectorId}/chatgpt/signin`)).data; }
    catch (e) { if (!gone()) setErr(`${errText(e)} Pick ChatGPT to try again, or pick another AI.`); return; }
    if (gone()) return;
    setSigning({ cid: c.ConnectorId, flow: flow.flow, url: flow.url });
    window.open(flow.url, "_blank", "noopener");
    for (const until = Date.now() + 10 * 60_000; Date.now() < until;) {
      await new Promise((r) => setTimeout(r, 2000));
      if (gone()) return;
      let d;
      try { d = (await api.post(`/api/connectors/${c.ConnectorId}/chatgpt/poll`, { flow: flow.flow })).data; } catch { continue; }
      if (gone()) return;
      if (d.status === "pending") continue;
      setSigning(null); signRef.current = null;
      if (d.status !== "ok") { setErr(`The ChatGPT sign-in didn't finish: ${d.detail || "no reason given"}. Pick ChatGPT to try again.`); return; }
      return planCheck(c.ConnectorId);
    }
    if (gone()) return;
    signRef.current = null; setSigning(null); setErr("The ChatGPT sign-in took too long. Pick ChatGPT to start it again.");
  };
  const planCheck = async (cid) => {
    setErr(""); setBusy(`c${cid}`); setSaid("Checking ChatGPT works - it sorts one test email, up to two minutes…");
    try { await api.post("/api/setup/first-run/connector", { cid }, { timeout: CHECK_MS }); }
    catch (e) { setErr(`${errText(e)} Pick ChatGPT to try again.`); }
    await reload(); setBusy(""); setSaid("");
  };
  const cancelSignin = () => {
    signRef.current = null;
    if (signing) api.post(`/api/connectors/${signing.cid}/chatgpt/cancel`, { flow: signing.flow }).catch(() => {});
    setSigning(null); setErr("");
  };
  const install = async (ai, verb = "Installing") => {
    setErr(""); setBusy(ai.name); setSaid(`${verb} ${ai.title}… this takes about a minute.`);
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
    } catch (e) { setBusy(""); setSaid(""); setErr(`${ai.title} didn't install: ${errText(e)} Pick it again to retry, or pick another AI.`); }
  };

  // the bar is never blank: while setup loads it says so, or what went wrong - and the failure is tried again, by itself or by Try again
  stRef.current = st;
  const loadLine = loadErr && `${loadErr} Trying again in a moment.`;
  if (!st) lineRef.current = loadLine || "Getting set up…";
  if (!st) return <Box sx={{ p: 2, display: "flex", gap: 1, alignItems: "center" }}><CircularProgress size={16} />
    <Typography sx={{ color: DIM }}>{loadLine || "Getting set up…"}</Typography>
    {loadErr && <Button size="small" onClick={reload}>{btnLabel("try_again")}</Button>}</Box>;

  const byType = (types) => types.flatMap((t) => conns.filter((c) => c.Type === t));
  // plain: the same card, its state in a first-time owner's words (connCardOf) - the Connections page keeps its own
  const card = (c, simple) => connCardOf(c, sources, () => setOpen((o) => (o?.id === c.ConnectorId ? null : { id: c.ConnectorId, simple })), true);
  // the CLIs read as cards the catalogue would draw: the AI's name, its maker's logo, and its state in the same plain words
  // ...in words that say what to do: one that can't install here says what to pick instead, one installed needs its sign-in
  const noInstall = "Can't install on this computer - pick ChatGPT or a key instead";
  const stateOf = (ai) => (busy === ai.name ? ["on", "Checking it works…"]
    : fix?.name === ai.name ? ["failing", fix.fix === "signin" ? "Needs sign-in" : fix.fix === "install" ? "Not installed - press Install"
      : ["update", "retry"].includes(fix.fix) ? "Signed in · not answering" : !ai.installed ? noInstall : "Not answering"]
    : st.step !== "ai" && st.brain.name === ai.title ? ["on", "Your AI - it sorts your mail"]
    // connected on the Connections page, just not the one sorting the mail: it read "Not set up" (the owner, 2026-10-16)
    : ai.connected ? ["on", "Connected - pick it to make it your AI"]
    : ["off", ai.installed ? "Installed - needs sign-in" : ai.install ? "Not installed - pick it to install" : noInstall]);
  const cliCards = st.ais.map((ai) => {
    const [state, words] = stateOf(ai);
    return { key: `cli-${ai.name}`, title: ai.title, channel: CLI_LOGO[ai.name] || "cli", go: busy ? undefined : () => pick(ai),
      state, plain: true, desc: `${words} · ${ai.sub}` };
  });
  // ChatGPT leads: the plan most people already pay for, signed in through the browser (planSignin) - not the Codex CLI's terminal
  const plan = byType(["chatgpt"])[0], planKey = plan && `c${plan.ConnectorId}`;
  const planBusy = busy && busy === planKey;
  // THE AI IN USE BY ITS CONNECTION, never its name: "ChatGPT (your plan)" never matched the card titled ChatGPT, which said
  // "Not set up" under "Your AI is ChatGPT" and started a new sign-in when pressed (2026-10-17)
  const inUseCid = (c) => st.step !== "ai" && st.brain?.pick === `connector:${c.ConnectorId}`;
  const planOn = plan && inUseCid(plan) && fix?.key !== planKey;
  const planCard = plan && { ...card(plan, true), title: "ChatGPT", channel: "openai", plain: true, pick: `connector:${plan.ConnectorId}`,
    state: signing || planBusy || planOn ? "on" : fix?.key === planKey ? "failing" : "off",
    desc: `${signing ? "Signing in…" : planBusy ? "Checking it works…" : fix?.key === planKey ? "Signed in · not answering"
      : planOn ? "Your AI - it sorts your mail" : "Not set up"}` + " · sign in with your ChatGPT account",
    go: busy || signing || planOn ? undefined : () => planSignin(plan) };
  const keyCards = byType(SETUP_AI).map((c) => ({ ...card(c, true), pick: `connector:${c.ConnectorId}` }));
  // WHAT MOST PEOPLE HAVE LEADS (the non-coder audit, 2026-10-17): the first four were ChatGPT and three coding tools, with the
  // organisation's card and the keys under More AI. ChatGPT, the organisation card when there is one, the keys - and the coding
  // tools under a heading of their own
  const lead = [...(planCard ? [planCard] : []), ...keyCards];
  const all = [...lead, ...cliCards];
  // the AI in use leads the shelf, even one from More AI: the cards showed four others while the line named Azure OpenAI
  const inUse = st.step !== "ai" && st.brain?.name;
  const using = (c) => (c.pick ? inUseCid({ ConnectorId: Number(c.pick.slice(10)) }) : c.title === inUse);
  const ai = inUse ? [...all.filter(using), ...lead.filter((c) => !using(c))] : lead;
  const coding = cliCards.filter((c) => !(inUse && using(c)));
  const mail = byType(MAIL_TYPES).map((c) => card(c, true));
  pickRef.current = pickOf(st, view || frontierOf(st), (view || frontierOf(st)) === "mail" ? mail : ai, !!busy || !!signing || !!open || !!fix);
  if ((pickRef.current?.title || "") !== pickTitle) setPickTitle(pickRef.current?.title || "");
  const conn = open && conns.find((c) => c.ConnectorId === open.id);
  const detail = conn && (
    <Box sx={{ mt: 0.5 }}>
      <ChannelDetail key={conn.ConnectorId} conn={conn} sources={sources} reload={reload} simple={open.simple}
        onBack={() => { setOpen(null); reload(); }} onConnected={reload} />
    </Box>
  );
  const q = view || frontierOf(st);
  const aboutDue = q === "about";
  // the mail is sorted in the background: setup never waits on it, and says so (the owner, 2026-10-15: "it never says emails 45 are
  // processed, moving on or doing it in background as no need to wait") - and a mailbox read with nothing in it says that (st.empty)
  const sortingLine = st.step === "reading" ? (st.sorting ? ` Your mail is being sorted in the background - ${plural(st.sorting, "email")} to go; no need to wait.`
    : st.empty ? " Connected - nothing new to sort yet." : " Your mail is being read in the background - no need to wait.") : "";
  // the brain failing on the real mail, said the same on every step - the server's own line only came with its "reading" step
  const aiErr = st.ai_error ? `${st.brain?.name || "Your AI"} isn't sorting your mail - ${st.ai_error}.` : "";
  lineRef.current = said || err || {
    ai: fix?.why || (aiErr ? `${aiErr} Pick another AI - it is checked on a test email first.` : st.step === "ai" ? "What AI do you have? Pick it - Taskuary checks it works and uses it to sort your mail."
      : `Your AI is ${st.brain?.name || "set"} - it sorts your mail and runs the Assistant. Pick another here to switch.`),
    // a brain failing on the real mail is said on every step past the AI, with Change AI in the row - "no need to wait" over mail
    // that was not being sorted at all was the opposite of true (the Advisor audit, 2026-10-15)
    mail: aiErr ? `${aiErr} Change AI picks one that does.` : doneOf(st, "mail") ? `Your email is connected.${sortingLine} Another mailbox can be added the same way.`
      // a sign-in that failed: why, and what to do - not the question again under the card's own error (2026-10-16)
      : st.mail_error ? `${st.mail_error} Fix it in the card and press Connect again - or pick a different email.`
      : `What email do you have? Pick it - ${mail[0]?.title || "Outlook mail"} is one sign-in.`,
    about: aiErr ? `${aiErr} Change AI picks one that does.` : aboutLine || "A few questions about your work - filled in from your email where I can.",
    done: aiErr ? `${aiErr} Change AI picks one that does.` : "You're set up. Anything else you connect is optional - Connections has it all, any time.",
    other: aiErr ? `${aiErr} Change AI picks one that does.` : connSug ? (connLine || (connSug.failed ? "I couldn't suggest connections just now - pick a section below, or skip it: nothing more is needed."
      : "Nothing else is needed - connect more here any time, from Connections."))
      : "Looking at what you told me about your work to suggest what to connect…",
  }[q];
  // THE PICKED CARD STANDS ALONE with its one next step under it (the owner, 2026-10-15: "i clicked chat gpt the other boxes should
  // go away, otherwise it looks like nothing happens ... you act something happens, show whats next step clearly. any error lead them
  // to fix"). Checking: say so. Needs sign-in: one button that runs the CLI's own login, and the check runs by itself when it ends.
  const focus = !open && focusOf({ ...st, step: q === "ai" ? "ai" : st.step }, planBusy ? "" : busy, browse, signing ? `c${signing.cid}` : planBusy ? busy : null);
  const check = () => (fix?.key ? planCheck(Number(fix.key.slice(1))) : fixed && pick(fixed));
  // the login ended: check it, and if it still fails the Sign in button is back rather than a pane that has exited
  const ended = () => { setPane(null); check(); };
  const signin = q === "ai" && fix?.fix === "signin" && fix.setup;
  // SIGNED IN AND STILL FAILING (firstrun: the CLI's own status said so): the sign-in is not the fix, so it is never offered -
  // a "Successfully logged in" was sent straight back to Sign in (the owner, 2026-10-15). What it said, and the moves that can fix it.
  const stuck = q === "ai" && ["update", "retry"].includes(fix?.fix);
  const said_ = fix?.detail && <Typography sx={{ fontSize: 12.5, color: DIM, fontFamily: "monospace", whiteSpace: "pre-wrap", maxWidth: 760 }}>
    What it said: {fix.detail}</Typography>;
  const cli = signin && { name: fix.name, setup: fix.setup, installed: true };
  const cliDetail = busy ? (
    <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}><CircularProgress size={14} />
      <Typography sx={{ color: DIM, fontSize: 13.5 }}>Checking it works by sorting one test email - up to two minutes.</Typography></Box>
  ) : signing ? (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1, alignItems: "flex-start" }}>
      <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}><CircularProgress size={14} />
        <Typography sx={{ fontSize: 14 }}>Finish signing in to ChatGPT in your browser - Taskuary carries on by itself when you're done.</Typography></Box>
      {/* a work ChatGPT can refuse other apps - OpenAI's own page says so in a code (3p_delegated_access_policy_denied, 2026-10-16) */}
      <Typography sx={{ fontSize: 12.5, color: DIM, maxWidth: 620 }}>If OpenAI says your workspace's policy denies it, use Codex
        instead - press Cancel and pick Codex. (A workspace setting blocks other apps; its admin can change it.)</Typography>
      <Box sx={{ display: "flex", gap: 1 }}>
        <Button variant="outlined" href={signing.url} target="_blank" rel="noreferrer">Open the sign-in page</Button>
        <Button size="small" sx={{ color: DIM }} onClick={cancelSignin}>Cancel</Button>
      </Box>
    </Box>
  ) : signin ? (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1, alignItems: "flex-start" }}>
      {!pane?.sid ? <>
        {/* the why is the Advisor's line above; under the card is only the thing to press */}
        <Button variant="contained" disableElevation disabled={!!opening}
          onClick={() => openSetup({ ...cli, login: true })}>{opening ? "Opening…" : `Sign in to ${fix.title}`}</Button>
      </> : <>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}><CircularProgress size={14} />
          <Typography sx={{ fontSize: 14 }}>A sign-in page opened in your browser - finish signing in there. Taskuary checks {fix.title} by
            itself when you're done.</Typography></Box>
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          {url && <Button variant="outlined" href={url} target="_blank" rel="noreferrer">Open the sign-in page</Button>}
          <Button size="small" onClick={check}>Check now</Button>
          <Button size="small" sx={{ color: DIM }} onClick={() => setDetails((v) => !v)}>{details ? "Hide details" : "Show details"}</Button>
        </Box>
        <Box sx={{ width: "100%", display: details ? "block" : "none" }}><CliPane pane={pane} height="34vh" hint={false} onExit={ended} /></Box>
      </>}
      {note?.bad && <Typography sx={{ fontSize: 13, color: "#9b2c2c" }}>{note.text} - try again, or pick a different AI.</Typography>}
    </Box>
  ) : stuck ? (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1, alignItems: "flex-start" }}>
      {said_}
      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
        {fix.key && plan && fix.key === planKey && <Button variant="contained" disableElevation onClick={() => planSignin(plan)}>Sign in again</Button>}
        {fix.fix === "update" && fix.install && <Button variant="contained" disableElevation
          onClick={() => install({ ...fixed, install: fix.install }, "Updating")}>Update {fix.title}</Button>}
        <Button variant={fix.fix === "update" || fix.key ? "outlined" : "contained"} disableElevation onClick={check}>{btnLabel("try_again")}</Button>
        <Button onClick={() => openBugReport({ message: `${fix.title} didn't answer the setup test
${fix.detail || ""}`, screen: "Setup",
          route: `first-run ${fix.name}` })}>{btnLabel("report_bug")}</Button>
      </Box>
    </Box>
  ) : null;
  const shelf = (k, cards, more, group = null) => q === k && (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <Shelf cards={cards} more={more} opened={(open && `c${open.id}`) || (k === "ai" && focus) || null} group={group}
        detail={open ? detail : cliDetail} allLabel={k === "ai" ? "Pick a different AI" : "Show all"}
        onAll={() => { setOpen(null); if (k === "ai") setBrowse(true); }} />
    </Box>
  );
  // About your work saved: Setup complete only once the AI and the mail work too - else the first step still undone
  const afterAbout = async () => {
    const first = !reopened && !st.about_done, s = await reload();
    go(!s ? "other" : !requiredDone(s) ? frontierOf(s) : first ? "done" : "other");
  };
  return (
    <Box data-tq-firstrun={st.step} sx={{ display: "flex", flexDirection: "column", gap: 1.75, maxWidth: 980 }}>
      {shelf("ai", ai, "More AI", { label: "If you use a coding tool", cards: coding })}
      {shelf("mail", mail, "More email")}
      {aboutDue && <FirstRunAbout again={!!st.about_done} onBack={() => go("mail")} onLine={setAboutLine} onSaved={afterAbout} />}
      {/* the first time the required steps are done: confetti and the way into the day (the owner, 2026-10-16) - or, with the AI
          failing on the mail, that problem and Change AI as its one big button */}
      {q === "done" && <SetupDone onDay={finishThen(onFinish)} onMore={() => go("other")}
        aiError={aiErr} onChangeAi={() => go("ai")} />}
      {q === "other" && <CanvasBrowse area="connections" state={browseSt} onState={setBrowseSt} live onOpenCard={() => {}} />}
    </Box>
  );
}

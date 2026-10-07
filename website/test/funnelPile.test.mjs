import { test } from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { LANES, LANE_META, attentionBand, levelOf, ageText, agoText, arrivals, chipsOf, lastSaidIndex, lastActIndex, cardFor, currentItemFromPile, currentPresentationChanged, departures, displayRevision, drawOrder, followsItem, keysOf, laneMeta, railAge, refreshCurrentPresentation, refreshPilePresentation, rowMeta, statusLine } from "../src/funnelPile.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
const cardsSrc = () => read("assistantCards.jsx");

test('Current follows only an explicit canonical migration or lineage alias', () => {
  const prior = { key: 'review:8', tid: 3 };
  const fresh = { key: 'processing:root', processing_id: 'root', aliases: ['review:8'], tid: 3, lane: 'approve' };
  assert.equal(followsItem(prior, fresh), true);
  assert.equal(currentItemFromPile(prior, { items: [], current: fresh }), fresh);
  assert.equal(followsItem({ ...prior, key: 'review:9' }, fresh), false);
});

test("every lane the server knows has a word, a mark and a role the theme can colour", () => {
  // `stopped` is inserted, never a reorder: lane_index IS the rail's sort order (funnel._order).
  // `theirs` follows `yours`: your task, waiting on somebody else (2026-09-25)
  assert.deepStrictEqual(LANES, ["blocked", "time", "approve", "asked", "yours", "theirs", "queued", "stopped", "saved", "broken", "unjudged", "forgotten", "report", "fyi", "working"]);
  // the owner's OWN work is a lane, not a kind override: a kind beats its lane (rowMeta), which is
  // right when the kind says more and wrong here - "on you" would have beaten "waiting to start" on
  // every queued row, because both carry kind 'todo' (the owner, 2026-09-16: "shouldn't this show
  // an emoji as well? queued or something").
  assert.strictEqual(LANE_META.yours.word, "on you");
  // an agent that ran and LEFT is neither waiting to start nor waving - it has its own word, taken
  // from taskLifecycle.agentPhase, which has named this correctly for the Tasks tab all along
  assert.strictEqual(LANE_META.stopped.word, "agent stopped");
  // ...and a row NOTHING judged is not an fyi: `fyi` claims a verdict was reached, and the whole
  // point of the error state is that none was (the owner, 2026-09-15: "that's a bad bug")
  assert.strictEqual(LANE_META.unjudged.word, "triage failed");
  assert.strictEqual(LANE_META.unjudged.role, "bad");
  // a failed check is second only to an agent that is stuck, wears the oxblood `bad` role, and
  // is NOT in the server's MUTED_LANES - a rule that quiets a chatty report cannot quiet it failing
  assert.strictEqual(LANE_META.broken.role, "bad");
  for (const l of LANES) { assert.ok(LANE_META[l].word); assert.ok(LANE_META[l].mark); assert.ok("role" in LANE_META[l]); }
  // oxblood is spent on nothing but "this is on you": an agent waiting, a draft waiting for a yes
  assert.deepStrictEqual(LANES.filter((l) => LANE_META[l].role === "you"), ["blocked", "approve"]);
  assert.strictEqual(laneMeta("nonsense"), LANE_META.fyi);
});

test("the rail draws the server's next-first list as it comes: what comes out next is on top", () => {
  const items = [{ key: "a" }, { key: "b" }, { key: "c" }];
  assert.deepStrictEqual(drawOrder(items).map((i) => i.key), ["a", "b", "c"]);
  assert.notStrictEqual(drawOrder(items), items);   // a copy: the caller splices the current one out
  assert.deepStrictEqual(drawOrder(null), []);
});

test("an arrival is a key we have not drawn before - and the first paint is never an arrival", () => {
  const first = [{ key: "a" }, { key: "b" }];
  assert.deepStrictEqual([...arrivals(null, first)], []);
  const prev = keysOf(first);
  assert.deepStrictEqual([...arrivals(prev, [{ key: "b" }, { key: "z" }])], ["z"]);
  assert.deepStrictEqual([...arrivals(prev, first)], []);
  // ...and a departure is a key that was drawn and is gone - it falls out of the mouth
  assert.deepStrictEqual(departures(first, [{ key: "b" }]).map((i) => i.key), ["a"]);
  assert.deepStrictEqual(departures(null, first), []);
});

test("the card under a line is decided by kind, one card per kind", () => {
  assert.strictEqual(cardFor({ kind: "review" }), "reply");
  assert.strictEqual(cardFor({ kind: "action" }), "reply");
  assert.strictEqual(cardFor({ kind: "agent" }), "agent");
  assert.strictEqual(cardFor({ kind: "meeting" }), "meeting");
  assert.strictEqual(cardFor({ kind: "report" }), "report");
  assert.strictEqual(cardFor({ kind: "agentdone" }), "agentdone");
  assert.strictEqual(cardFor({ kind: "idea" }), "idea");
  assert.strictEqual(cardFor({ kind: "asked" }), "message");
  assert.strictEqual(cardFor({ kind: "fyi" }), "message");
  assert.strictEqual(cardFor({ kind: "triaging" }), null);
  assert.strictEqual(cardFor({ kind: "brief" }), "brief");
  assert.strictEqual(cardFor({ kind: "task" }), "task");
  assert.strictEqual(cardFor({ kind: "fyis" }), "fyis");
  assert.strictEqual(cardFor({ kind: "wrapup" }), "wrapup");
  assert.strictEqual(cardFor({ kind: "todo", lane: "working", tid: 358 }), "agent");
  assert.strictEqual(cardFor(null), null);
});

test("a dispatched message follows its task into the live agent row", () => {
  const card = { key: "msg:44", tid: 358, kind: "todo", lane: "asked" };
  const working = { key: "agent:358", tid: 358, kind: "todo", lane: "working", agent: "coder", sid: "abc" };
  assert.equal(currentItemFromPile(card, { current: null, items: [working] }), working);
  assert.equal(followsItem(card, working), true);
  assert.equal(cardFor(working), "agent");
  assert.equal(followsItem(card, { key: "agent:999", tid: 999, lane: "working" }), false);
});

test("full display revisions replace completed pile responses and retain identical ones", () => {
  const old = { rev: "legacy-same", display_revision: "display-1", items: [{ key: "a", preview: "old" }] };
  const edited = { rev: "legacy-same", display_revision: "display-2", items: [{ key: "a", preview: "new" }] };
  assert.equal(displayRevision(old), "display-1");
  assert.equal(displayRevision({ rev: "legacy-only" }), "legacy-only");
  assert.equal(refreshPilePresentation(old, { ...old }), old);
  assert.equal(refreshPilePresentation(old, edited), edited);
  assert.deepEqual(refreshPilePresentation(null, { items: [] }), { items: [] });
});

test("a changed Current presentation is a complete replacement so removed fields stay removed", () => {
  const old = { key: "msg:44", lane: "approve", presentation_revision: "p1",
    preview: "old excerpt", draft: true, tail: ["old question"], more: 3 };
  const fresh = { key: "msg:44", lane: "asked", presentation_revision: "p2", title: "Fresh title" };
  const fromPile = currentItemFromPile(old, { current: fresh, items: [] });
  const replaced = refreshCurrentPresentation(old, fromPile);
  assert.equal(currentPresentationChanged(old, fresh), true);
  assert.equal(replaced, fresh);
  assert.deepEqual(replaced, fresh);
  assert.equal("preview" in replaced, false);
  assert.equal("draft" in replaced, false);
  assert.equal("tail" in replaced, false);
  assert.equal("more" in replaced, false);
  assert.equal(refreshCurrentPresentation(fresh, { ...fresh }), fresh);
});

test("an explicitly missing scoped Current cannot resurrect from a stale queue row", () => {
  const current = { key: "msg:44", tid: 7, presentation_revision: "p1" };
  assert.equal(currentItemFromPile(current, { current: null, items: [{ ...current, presentation_revision: "p2" }] }), null);
  assert.equal(currentItemFromPile(current, { items: [{ ...current, presentation_revision: "p2" }] }).presentation_revision, "p2");
  const working = { key: "agent:7", tid: 7, lane: "working", presentation_revision: "worker-p1" };
  assert.equal(currentItemFromPile(current, { current: null, items: [working] }), working);
  assert.equal(currentItemFromPile(current, { current: null, items: [{ ...working, tid: 8 }] }), null);
  assert.equal(currentItemFromPile(current, { current: null, items: [{ ...working, lane: "blocked" }] }), null);
});

test("ages read as a person says them", () => {
  const now = new Date("2026-09-03T12:00:00").getTime();
  assert.strictEqual(ageText("2026-09-03 12:12:00", now), "in 12 min");
  assert.strictEqual(ageText("2026-09-03 14:30:00", now), "in 2h");
  assert.strictEqual(ageText("2026-09-03 11:59:30", now), "now");
  assert.strictEqual(ageText("2026-09-03 11:20:00", now), "40 min");
  assert.strictEqual(ageText("2026-09-03 08:00:00", now), "4h");
  assert.strictEqual(ageText("2026-08-30 08:00:00", now), "4d");
  assert.strictEqual(ageText("", now), "");
  assert.strictEqual(ageText("garbage", now), "");
});

test("the header line counts the pipe and what is on you", () => {
  assert.strictEqual(statusLine([], false), "All caught up");
  assert.strictEqual(statusLine([{ lane: "fyi" }, { lane: "approve" }, { lane: "blocked" }], false), "3 in the pipe · 2 on you");
  assert.strictEqual(statusLine([{ lane: "fyi" }], false), "1 in the pipe");
  assert.strictEqual(statusLine([{ lane: "fyi" }], true), "thinking…");
});

test("the Assistant page IS the app: the landing view, the Board the one other, the bubble off it", () => {
  const page = read("TaskHubPage.jsx");
  // THE CANVAS REDESIGN (2026-09-29): no tab strip. The Assistant is the landing view and the Board, the agents and their
  // wall, the one full-screen view beside it; every other page is a card in the Assistant's canvas.
  assert.match(page, /const VIEWS = \["Assistant", "Board"\];/);
  assert.doesNotMatch(page, /const TABS = /);
  assert.match(page, /if \(t === "Timeline" \|\| t === "Tasks"\) t = "Assistant";/);   // old links and cards still land
  assert.match(page, /if \(BROWSED\[t\]\) \{ ask\(\{ kind: "browse", area: BROWSED\[t\] \}\); t = "Assistant"; \}/);
  assert.doesNotMatch(page, /<FeedView/);                   // the rail is mounted by the Assistant, nowhere else
  assert.match(page, /useState\("Assistant"\)/);           // the default, always
  assert.doesNotMatch(page, /<FloatingAssistant/);
  // ...and the way back from the Board wears Taskuary's star, drawn in the pill's own ink
  assert.match(page, /<TaskuaryMark size=\{16\} \/>Assistant/);   // the real logo, not a second drawing of it (2026-10-06)
  const view = read("AssistantView.jsx");
  assert.match(view, /\/api\/funnel\/pile/);
  assert.match(view, /\/api\/concierge\/next/);
  assert.match(view, /All done/);
  assert.match(view, /!pile \? \(/);                  // loading is not a false empty Timeline
  assert.match(view, /Loading timeline/);
  assert.match(view, /const sharedFilter = useRef\("\{\}"\)/); // default filter must not force a duplicate mount rebuild
  // a row with no message - an assistant idea that became a task - still opens on the stage: the
  // canonical item describes a task as readily as a message (2026-09-16)
  assert.match(view, /openByItem\?\.\(pid, target\)/);
  assert.match(read("FeedView.jsx"), /const openByItem = \(itemId, target\) =>/);
  const feedSource = read("FeedView.jsx");
  assert.match(feedSource, /view === "unread" && top && !unreadInventory/); // wait for canonical Unread; do not race it with legacy feed reads
  assert.match(feedSource, /\{!top && <FunnelBar/); // Assistant's pile replaces the legacy funnel query
  assert.match(view, /const visibleItems = items\.slice\(0, revealed\)/); // first load paints incrementally
  assert.match(view, /requestAnimationFrame\(addBatch\)/);              // progressive batches do not impose one frame per row
  assert.match(view, /count \+ 24/);                                     // large accounts finish promptly
  assert.doesNotMatch(view, /By the way|className="tq-btw"/);   // no bottom strip: the rail and the card already say it (2026-09-23)
  assert.doesNotMatch(view, /tq-pipe-walls/);             // no funnel: what comes out next is the FIRST row
  // What is on the table STAYS WHERE IT IS. Hoisting it to the top of one flat stack would tear a
  // row out of its category on every Next now that the rail is grouped - and an fyi batch would
  // tear out ten (the owner, 2026-09-16: "it should highlight all 4 or 10 ... now i think it
  // condenses"). One bracket, drawn behind the rows, moving none of them.
  assert.doesNotMatch(view, /current: true \}\] : \[\]\), \.\.\.drawOrder/);
  assert.match(view, /const batchKeys = new Set\(batch \? \(batch\.members \|\| \(batch\.items \|\| \[\]\)\.map/);
  // ...and the rows the batch holds are put BACK on the rail while it is on the table: shown is
  // read, so they leave the pile the moment the batch goes up and there was nothing left to ring
  assert.match(view, /const onTable = batch \? \(batch\.items \|\| \[\]\)\.filter/);
  assert.match(view, /className="tq-pile-batch"/);
  // ...and ONE item on the table says the same word on the same border. Both wear the identical
  // slate ring, so without it the ring on a single row had to be read rather than known (the
  // owner, 2026-09-17: "isn't there a current word on the border around chosen task?").
  assert.match(view, /\{isCur && <b className="tq-pile-now">on the table<\/b>\}/);
  assert.match(read("assistantView.css"), /\.tq-pile-batch b, \.tq-pile-now \{/);
  assert.match(view, /const bands = bandsOf\(drawn\.map\(/);          // grouped by category, headings freeze
  // ...each band taking the room it has, less the extra height of the row on the table - which is
  // 24px taller than the rest and drawn inside one of those bands
  assert.match(view, /fillCaps\(room - \(curKey \? CUR_H - ROW_H : 0\), bands\)/);
  // Unread is the ranked pipe again: it is the only source for CURRENT/NEXT and for what the chat
  // will actually ask about. All remains FeedView's chronological history.
  assert.match(view, /<FeedView[^]*top=\{\(\{ openByMid, openByItem \}\) => <Pile/);
  assert.match(read("FeedView.jsx"), /typeof top === "function" \? top\(\{ openByMid, openByItem \}\) : top/);
  // The rail's kind/source filters narrow the rail's OWN rows and nothing else: the pile and the
  // walk are asked for over everything, so the assistant processes the whole pipe whatever the
  // rail is showing (the owner, 2026-09-04: "how the assistant works on filtered tasks - does it
  // only process those?"). The one narrowing the walk takes is `only`, which is the "Just what
  // came in" button. If that ever changes, these two are where it has to be said out loud.
  const pileRequest = view.slice(view.indexOf('api.get("/api/funnel/pile"'), view.indexOf("setPile", view.indexOf('api.get("/api/funnel/pile"')));
  // The pile lookup remains scoped to Current, with its key captured before the request so a
  // superseded response cannot reconcile a newer Current selected while the request was pending.
  assert.match(pileRequest, /requestedCurrentKey \? \{ current: requestedCurrentKey \}/);
  assert.doesNotMatch(pileRequest, /\b(cat|pick|channel|source)\b/);
  assert.match(view, /key: body\.key, only: body\.only, include_surfaced: body\.include_surfaced, exclude: body\.exclude,/);
  assert.match(view, /selection_revision: body\.selection_revision, expected_next_key: body\.expected_next_key, expected_next_members: body\.expected_next_members/);
  assert.doesNotMatch(view, /include_surfaced: true/); // a read row is not presented again by Next
  assert.doesNotMatch(view, /i\.surfaced && !i\.current \? "shown"/);                              // unread never looks processed
  assert.match(view, /stage=\{stageMode === "chat" \? chat : placeholder\} rowMode=\{stageMode\}/);   // the two ways to use the stage
  assert.match(view, /onPull=\{\(r\) => pull\(keyForRow\(r\)/);   // a Timeline row is pulled in by the pipe's own key
  assert.match(view, /window\.location\.hash = `msg=\$\{mid\}`/);   // "on the Timeline" pins the row over the chat
  assert.doesNotMatch(view, /turn\(\{ mode: "open" \}\)/);   // the day never writes itself: the welcome is the door
  // words are interpreted, never dispatched (PW-121..125): the two immediate exceptions (Next, a reply
  // draft) run on the decision; everything else arrives as a proposal card whose button submits the
  // structured proposal by id and version to the shared execute road
  assert.match(view, /if \(!prop && data\.decision\) await decide\(data\.decision, data\)/);
  assert.match(view, /\/api\/operations\/\$\{p\.id\}\/execute`, \{ version: p\.version \}/);
  assert.doesNotMatch(view, /dispatch`, \{ kind: "coding"/);                       // no verb is carried out from the chat itself
  assert.doesNotMatch(view, /tq-quick/);                  // nothing sits over the composer any more
  assert.doesNotMatch(view, /SUGGESTIONS/);               // ...and the page invents no vocabulary of its own
  // the action words go to the row by the prompt, never under a chat line (the owner, 2026-10-06: "no button in line ever")
  assert.match(view, /<BarVerbs owner=\{`line:\$\{m\.id\}`\}/);
  assert.doesNotMatch(view, /className="tq-verbs"/);
  assert.match(view, /chipsOf\(m\)/);                       // from the durable turn: a poll must not erase them
  assert.match(view, /chip: runChip/);                    // one road for every one of them
  assert.match(view, /moved up - it looked urgent/);       // the rail shows promotions
  assert.match(view, /data\.events\?\.length/);           // the watcher's lines land in the chat as they happen
  // a rerun is the chat line's word now, not a second button on the card (2026-09-07: "only one place")
  assert.doesNotMatch(cardsSrc(), /Run it again/);
  assert.match(cardsSrc(), /Open walkthrough/);             // set-up opens the Assistant operator, not a coding checkout
  // the answers an agent NAMED are answers you can click, bound to the request that asked - the
  // waiting room is for a pane that is not asking anything (the owner, 2026-09-17)
  // (the walk's agent card is gone - an agent's item opens its task, answered in its own pane; the game keeps the picks)
  assert.match(read("gameItem.jsx"), /\/worker\/answer/);
  assert.doesNotMatch(view, /onClick=\{\(\) => settle\("done"\)\}/);   // Done is a suggestion, not a button that settles
  assert.match(read("FeedView.jsx"), /\/api\/ingest\/poll/);            // sync now, on the rail's header
  // the chat keeps its bottom in view as it grows - except while a browse card is read from its top (the canvas redesign)
  assert.match(view, /new ResizeObserver\(\(\) => \{ if \(!holdBottom\.current && el\.scrollHeight/);
  assert.doesNotMatch(view, /maxWidth: 1380/);             // the chat takes the width it has
  assert.doesNotMatch(cardsSrc(), /Just what came in/);    // no mail-only walk: a set is the model's to name (2026-09-25)
  assert.match(view, /Walk me through my tasks/);
  // the Timeline: an fyi filed on a thread's task does not wear the task's state, and no stray 0 under a verdict
  assert.match(read("FeedView.jsx"), /r\.TaskId && r\.MsgStatus !== "filed" && <LifecycleChip kind="task"/);
  assert.match(read("FeedView.jsx"), /\{!!\(verdict\.existing_task_id \|\| \(verdict\.related_message_ids/);
  assert.match(cardsSrc(), /All read, next/);             // a handful of fyi's goes in one click
  assert.match(read("TaskPage.jsx"), /<TerminalPane sid=\{term\.sid\}/);   // a stopped agent's own screen: its task view on the canvas
  assert.doesNotMatch(view, /left: side, right: side/);    // no taper: every row is a Timeline row's width
  assert.doesNotMatch(view, /<Drawer/);                    // no reader drawer: reading happens in the card
  const css = read("assistantView.css");
  // The work rail's gutter carries an AGE, not a clock, so it needs less width than the dated
  // Timeline's - the two rails are separate views now and their gutters say different things.
  assert.match(css, /\.tq-pile-row \{[^}]*grid-template-columns: 44px 14px minmax\(0, 1fr\)/);
  assert.match(read("FeedView.jsx"), /const GUTTER = 66;/);   // ...and the dated Timeline keeps its own
  // ...but they are set in ONE type: the Timeline's clock reads at the rail's size and weight,
  // and its dot is the SOURCE, the same answer the logo beside it gives (the owner, 2026-09-17).
  assert.match(read("FeedView.jsx"), /const gutterTime = \{ font: "600 11px 'IBM Plex Sans'/);
  assert.match(read("FeedView.jsx"), /const dotOf = \(r\) => channelColor\(r\?\.Channel \|\| "email"\);/);
  assert.doesNotMatch(css, /tq-pipe-/);                    // the funnel's CSS is gone with it
  // Still no "The pipe · N" banner over the whole rail (the owner, 2026-09-03). The per-CATEGORY
  // heading that freezes as you scroll is a different thing, and it is what replaced the dock's
  // level dropdown (the owner, 2026-09-16: "freeze on the type until you get to next category").
  assert.doesNotMatch(view, /The pipe ·/);
  assert.match(view, /className={`tq-pile-head\$\{folds \? " folds" : ""\}`}/);
  // ...and a band you can open is shut the same way: the heading is the control (2026-09-16)
  assert.match(view, /const folds = CAPPED\.includes\(level\) && rows\.length > FLOOR/);
  assert.match(css, /\.tq-pile-head \{[^}]*position: sticky/);
  assert.match(view, /One more and you're clear/);    // ...the count is the encouragement, at the bottom, from fifteen
  const feed = read("FeedView.jsx");
  assert.match(feed, /useState\(top \? "unread" : ""\)/);   // the Assistant rail opens on unread
  assert.match(feed, /view === "unread" \? \(typeof top/);     // ranked pipe, not historical rows
  // PW107 supersedes only the third Needs me surface with exactly All + Unread. The existing
  // All/detail and Unread/chat assertions follow the interaction helper where that logic moved.
  assert.match(feed, /feedViews\(!!top\)/);
  assert.match(feed, /const visibleStage = interaction\.showChatStage \? stage : null/);
  assert.match(feed, /const chatMode = interaction\.pullRowIntoChat/);
  assert.match(feed, /\) : visibleStage \|\| \(/);                    // no selection shows the review placeholder, not chat history
  assert.match(feed, /label: "Assistant discussion"/);               // task-bound walkthrough turns remain readable in All
  assert.match(feed, /"concierge_user", "concierge_assistant"/);      // distinct from an agent's own working conversation
  assert.match(feed, /tab === "discussion"/);
  assert.match(view, /for \(const pending of deferredChat\.current\) clearTimeout\(pending\)/); // one transition cannot queue two Next turns
  assert.match(view, /deferredChat\.current\.clear\(\);\s*const epoch = chatEpoch\.current/);
  assert.match(feed, /if \(narrow \|\| chatMode\) return;/);   // a chat is not a preview pane: no hover-open in chat mode
  assert.match(feed, /addEventListener\("hashchange", openHash\)/);   // a card's #msg= opens the row while the rail is already up
  const cards = read("assistantCards.jsx");
  // the two "not ours" doors the owner asked for: one that teaches memory, one that does not
  // 'not ours' is the chat line's word now (concierge.CHIPS), not a panel on the card
  assert.doesNotMatch(cardsSrc(), /not-mine/);
  // prep is the chat line's word now (concierge.CHIPS meeting), not a button on the card
  assert.doesNotMatch(cardsSrc(), /Prep me/);
  assert.match(cards, /SourceMark/); assert.match(cards, /ChannelIcon/);   // the logo of where it came from
  assert.doesNotMatch(cards, /On the Timeline/);                            // a dead link: Chat mode reads no #msg= (2026-09-23)
  // Once triage combines chat lines into a task, both an ordinary item and its pending reply show
  // that exact task bundle together. The conversation endpoint is intentionally not used here: a
  // long WhatsApp room may contain several separate tasks.
  assert.match(cards, /function CombinedTaskText/);
  assert.match(cards, /useFetched\(card\?\.tid \? `\/api\/tasks\/\$\{card\.tid\}`/);
  assert.match(cards, /filter\(\(m\) => String\(m\.Status \|\| ""\) !== "context"\)/);
  assert.match(cards, /messages combined by triage/);
  assert.match(cards, /<Clamp><CombinedTaskText card=\{card\} list=\{false\} \/><\/Clamp>/);   // the message shown, More only when it is cut off
  assert.match(cards, /\(over \|\| open\) && <button/);
  // reply + ordinary message, each WITHOUT the checklist - that stays on the task (2026-09-23)
  assert.equal((cards.match(/<CombinedTaskText card=\{card\} list=\{false\} \/>/g) || []).length, 2);
  assert.match(read("SettingsView.jsx"), /funnel_hours/); assert.match(read("SettingsView.jsx"), /funnel_max/);
});

test("a few kinds say more than their lane does", async () => {
  const { rowMeta, laneMeta } = await import("../src/funnelPile.js");
  // an agent's finished job and a report you set up share the 'report' lane; they do not read alike
  assert.equal(rowMeta({ kind: "agentdone", lane: "report" }).word, "agent finished");
  assert.equal(rowMeta({ kind: "agentdone", lane: "report" }).role, "done");
  // ...and a kind never beats a lane that is MORE specific: both of these carry kind 'todo'
  assert.equal(rowMeta({ kind: "todo", lane: "yours" }).word, "on you");
  assert.equal(rowMeta({ kind: "todo", lane: "queued" }).word, "waiting to start");
  assert.equal(rowMeta({ kind: "wrapup", lane: "report" }).word, "close it?");
  assert.equal(rowMeta({ kind: "report", lane: "report" }).word, laneMeta("report").word);
  assert.equal(rowMeta({ kind: "fyi", lane: "fyi" }).word, "fyi");
  assert.equal(rowMeta(null).word, "fyi");
});

test("the action words hang on the last thing Taskuary SAID about the item, not on a passive notice", () => {
  const item = { id: "a1", role: "assistant", card: { key: "msg:1", kind: "review", chips: [{ verb: "approve", label: "Send the reply" }] } };
  const notice = { id: "a2", role: "assistant", card: { key: "agent:9", kind: "agent", background_event: true } };
  assert.equal(lastSaidIndex([{ id: "u1", role: "user" }, item]), 1);
  assert.equal(lastSaidIndex([item, notice]), 0, "a background update must not take the words off the item");
  assert.equal(lastSaidIndex([item, { id: "r1", role: "receipt" }]), 0, "a receipt is not somewhere to act");
  assert.equal(lastSaidIndex([]), -1);
  // ...but a receipt carrying its way on (Not done -> Try again, a cancel, a sweep's Next) takes the words: drawn under the
  // line above it, a failed act ended on an empty row
  const failed = { id: "r2", role: "receipt", status: "error", chips: [{ verb: "next", label: "Next" }] };
  assert.equal(lastActIndex([item, failed]), 1);
  assert.equal(lastActIndex([item, { id: "r1", role: "receipt" }]), 0, "a bare receipt still is not");
  assert.equal(lastActIndex([failed, item]), 1, "a newer line takes them back");
  // an answer to a typed question carries them on the turn itself; a surfaced item on its card
  assert.deepEqual(chipsOf(item).map((c) => c.verb), ["approve"]);
  assert.deepEqual(chipsOf({ role: "assistant", chips: [{ verb: "next", label: "Next" }] }).map((c) => c.verb), ["next"]);
  // ...and a clarifying choice replaces them: it goes back as words, so mixing the two invites two answers
  assert.deepEqual(chipsOf({ ...item, options: ["Tuesday", "Thursday"] }), [{ ask: "Tuesday", label: "Tuesday" }, { ask: "Thursday", label: "Thursday" }]);
  assert.deepEqual(chipsOf({ role: "assistant" }), []);
});

// Four cards read `${ageText(x)} ago` and so said "now ago" on anything fresher than two minutes -
// and "in 3 min ago" when the server's stamp was a moment ahead of the browser's clock.
test("an age said as a sentence never reads 'now ago' or 'in 3 min ago'", () => {
  const now = Date.parse("2026-09-10T12:00:00Z");
  const at = (min) => new Date(now - min * 60000).toISOString();
  assert.equal(agoText(at(0), now), "just now");
  assert.equal(agoText(at(1), now), "just now");
  assert.equal(agoText(at(7), now), "7 min ago");
  assert.equal(agoText(at(150), now), "2h ago");
  assert.equal(agoText(at(-3), now), "in 3 min");     // a stamp in the future is not an age at all
  assert.equal(agoText(null, now), "");
  assert.equal(agoText("not a date", now), "");
});

test("the waving agent is the one lane sized to be seen", () => {
  // "can't see the hand waving. used to say agent waving?" (the owner, 2026-09-11). The mark and
  // the word were both in the table; nothing wore them, because row_lane never said `blocked`.
  const meta = LANE_META.blocked;
  assert.equal(meta.word, "agent waiting on you");          // ...the same word timelineState.waving uses
  assert.equal(meta.mark, "👋");
  assert.equal(meta.loud, true);
  // LOUD IS EXACTLY "this is on you". The two tables disagreed while they were two - the Timeline
  // shouted a ready reply and the rail did not - and unifying them had to pick one (2026-09-16).
  // Tying it to the role rather than listing keys is what stops it drifting again.
  assert.deepEqual(Object.entries(LANE_META).filter(([, m]) => m.loud).map(([k]) => k).sort(),
                   Object.entries(LANE_META).filter(([, m]) => m.role === "you").map(([k]) => k).sort());
  // still the owner's own level, not a new one
  assert.equal(attentionBand({ lane: "blocked" }), attentionBand({ lane: "approve" }));
});

test("a loud lane wears its mark and its bigger pill", () => {
  const feed = read("FeedView.jsx");
  assert.match(feed, /className=\{`tq-pile-tag\$\{m\.loud \? " loud" : ""\}`\}/);
  assert.match(feed, /\{m\.loud && m\.mark \? `\$\{m\.mark\} ` : ""\}\{m\.word\}/);
  assert.match(read("assistantView.css"), /\.tq-pile-tag\.loud \{[^}]*font-size: 11px/);
});

// THE TASKS RAIL AND THE WORK RAIL SAY THE SAME THING. The rail used to paint everything that was
// not done, dropped or busy with one red "needs you" chip, so a coder parked on a question and a
// reply waiting for your yes were indistinguishable (the owner, 2026-09-22). These two words must
// never collapse into one again, and they are the vocabulary's, not this rail's.
test("a waving agent and a waiting reply are two different words", () => {
  assert.equal(rowMeta({ lane: "blocked" }).word, "agent waiting on you");
  assert.equal(rowMeta({ lane: "approve" }).word, "ready to close out");
  assert.notEqual(rowMeta({ lane: "blocked" }).word, rowMeta({ lane: "approve" }).word);
});

test("every lane the Tasks rail can land on has a word and a role", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("../src/ui.jsx", import.meta.url), "utf8");
  const body = source.slice(source.indexOf("const taskLane ="), source.indexOf("const laneState ="));
  const lanes = [...new Set([...body.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]))].filter((l) => LANES.includes(l));
  assert.ok(lanes.length >= 5, "taskLane must still be reading lanes by name");
  for (const lane of lanes) {
    assert.ok(rowMeta({ lane }).word, `lane ${lane} has no word in lanes.json`);
    assert.ok("role" in rowMeta({ lane }), `lane ${lane} has no role, so the chip has no colour`);
  }
});

test('railAge: empty or unreadable is blank, the past buckets into < 30m / < 1h / Nh / Nd', () => {
  const now = new Date('2026-09-28T12:00:00').getTime();
  const ago = (min) => new Date(now - min * 60000).toISOString();
  assert.strictEqual(railAge('', now), '');
  assert.strictEqual(railAge(null, now), '');
  assert.strictEqual(railAge('not a date', now), '');
  assert.strictEqual(railAge(ago(0), now), '< 30m');
  assert.strictEqual(railAge(ago(29), now), '< 30m');
  assert.strictEqual(railAge(ago(30), now), '< 1h');
  assert.strictEqual(railAge(ago(59), now), '< 1h');
  assert.strictEqual(railAge(ago(60), now), '1h');
  assert.strictEqual(railAge(ago(1439), now), '23h');
  assert.strictEqual(railAge(ago(1440), now), '1d');
  assert.strictEqual(railAge(ago(3 * 1440 + 600), now), '3d');
});

test('railAge: the future reads "in ..." and a server stamp with a space parses as local time', () => {
  const now = new Date('2026-09-28T12:00:00').getTime();
  const ahead = (min) => new Date(now + min * 60000).toISOString();
  assert.strictEqual(railAge(ahead(5), now), 'in 5m');
  assert.strictEqual(railAge(ahead(59), now), 'in 59m');
  assert.strictEqual(railAge(ahead(60), now), 'in 1h');
  assert.strictEqual(railAge(ahead(1439), now), 'in 23h');
  assert.strictEqual(railAge(ahead(1440), now), 'in 1d');
  assert.strictEqual(railAge('2026-09-28 10:00:00', now), '2h');
});

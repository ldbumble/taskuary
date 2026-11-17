// CLOSE OUT HAS TWO SENDS (the owner, 2026-11-03: "when you send message through close out we need button send and close and send without
// closing so task stays open on send"): Send and close sends and then closes - the primary, and still kept open while an agent works - and
// Send sends with the task left open, as Send does everywhere else. On a tight line Send folds into a ▾, never Send and close.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { hint, label, rowsOf, verbOfRow, ALL_LABELS } from "../src/buttons.js";
import { advisedIn, typeOf } from "../src/actionRow.js";
import { barFolds } from "../src/foldBar.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const rd = read("ReviewDecision.jsx");

test("the one list names both sends, and each hover says exactly what it does", () => {
  assert.equal(label("send_close"), "Send and close");
  assert.match(hint("send_close"), /^Sends the reply, then closes the task - its agent is stopped, and it stays open only while something else on it still waits on you/);
  assert.equal(hint("approve"), "Sends the reply - the task stays open until you Mark done");
  assert.doesNotMatch(hint("approve"), /Close out|closes/);
  assert.deepEqual(rowsOf("send_close"), ["send_close"]);
  assert.equal(verbOfRow("41:send_close"), "send_close");
  assert.ok(ALL_LABELS.includes("Send and close"));
  assert.equal(typeOf({ id: "41:send_close" }), "reply", "it sits with the reply's moves");
});

test("the Advisor's or the Assistant's pick lights its own send - Send never lights Send and close, nor the other way round", () => {
  const list = [{ id: "41:send_close", label: "Send and close", group: "decide", tone: "p", card: true },
    { id: "41:approve", label: "Send", group: "decide", tone: "s", card: true }, { id: "done", label: "Mark done", group: "more" }];
  assert.equal(advisedIn(list, { verb: "send_close", label: "Send and close" })?.id, "41:send_close");
  assert.equal(advisedIn(list, { verb: "approve", label: "Send" })?.id, "41:approve");
  // ...and where the draft stands without Send and close (outside Close out, a send frozen on Check delivery) its Send is the same yes
  const one = [{ id: "41:approve", label: "Send", group: "decide", tone: "p", card: true }, { id: "done", label: "Mark done", group: "more" }];
  assert.equal(advisedIn(one, { verb: "send_close", label: "Send and close" })?.id, "41:approve");
  assert.equal(advisedIn([{ id: "done", label: "Mark done", group: "more" }], { verb: "send_close", label: "Send and close" }), null);
});

test("a close-out's pair: Approve and close and Approve, on the one list, and the close-out's yes lights Approve and close", () => {
  assert.equal(label("send_close", "closeout"), "Approve and close");
  assert.match(hint("send_close", "closeout"), /^Runs what finishing it does on GitHub, sends the reply, then closes the task - its agent is stopped, and it stays open only while something else/);
  assert.ok(ALL_LABELS.includes("Approve and close"));
  const list = [{ id: "41:send_close", label: "Approve and close", group: "decide", tone: "p", card: true },
    { id: "41:approve", label: "Approve", group: "decide", tone: "s", card: true }, { id: "41:alt", label: "Decline", group: "decide", tone: "s", card: true }];
  assert.equal(advisedIn(list, { verb: "approve", label: "Approve" })?.id, "41:send_close");
  // ...a draft's Send stays Send: "send it" never lights Send and close
  const sends = [{ id: "41:send_close", label: "Send and close", group: "decide", tone: "p", card: true }, { id: "41:approve", label: "Send", group: "decide", tone: "s", card: true }];
  assert.equal(advisedIn(sends, { verb: "approve", label: "Send" })?.id, "41:approve");
});

test("the close-out card in Close out draws Approve and close first and filled, Approve beside it; only the first's receipt closes", () => {
  assert.match(rd, /const twoApproves = !!co && !r\.Stale && closesIt && sendable && !simulated && !delivery\.frozen;/);
  const moves = rd.slice(rd.indexOf("] : co && !r.Stale ? ["), rd.indexOf("] : proposal ? ["));
  assert.ok(moves.indexOf('no("send_close")') < moves.indexOf('no("approve")'), "Approve and close first");
  assert.match(moves, /id: no\("send_close"\), label: [^\n]*closeCo, tone: "p"/);
  assert.match(moves, /tone: twoApproves \? "s" : "p"/);
  assert.match(moves, /run: \(\) => decideBoth\("approve", true\)/);
  assert.match(moves, /run: \(\) => decideBoth\("approve", !twoApproves\)/);
  assert.match(rd, /await onSent\(\{ closes: closesIt && close && !!data\.reply\?\.ok \}\); return;/);
  const jsx = rd.slice(rd.indexOf("twoApproves ? (<>"), rd.indexOf(") : proposal ? ("));
  assert.ok(jsx.indexOf('data-tq-send="close"') < jsx.indexOf("{foldMore("), "Approve and close is never in the ▾");
  assert.match(jsx, /run: \(\) => \{ setSendAt\(null\); decideBoth\("approve", false\); \}/);
  assert.match(rd, /const folded = paired && !bar\.shown\("send"\);/);
});

test("Close out draws Send and close first and filled, Send beside it; only Send and close's receipt closes", () => {
  assert.match(rd, /const twoSends = closesIt && !simulated && !co && !proposal && canSendIt && !r\.Stale && !chatFile && !delivery\.frozen;/);
  const moves = rd.slice(rd.indexOf("] : twoSends ? ["), rd.indexOf("] : [", rd.indexOf("] : twoSends ? [")));
  assert.ok(moves.indexOf('no("send_close")') < moves.indexOf('no("approve")'), "Send and close first");
  assert.match(moves, /id: no\("send_close"\)[^\n]*tone: "p"/);
  assert.match(moves, /id: no\("approve"\)[^\n]*tone: "s"/);
  assert.match(moves, /run: \(\) => decide\("approve", false, true\), title: closeTitle/);
  assert.match(moves, /run: \(\) => decide\("approve", false, false\), title: sendTitle/);
  assert.match(rd, /await onSent\(\{ closes: closesIt && shut && verb === "approve" && \(data\.reply \? !!data\.reply\.ok : true\),\n\s+said: verb === "approve" \? \{ text: value, channel: r\.Channel \|\| "", to: sentTo\(r\), subject: deliverySubject\(r\), id: r\.ReviewId, done: pw\.sentAs \} : null \}\); return;/);
  assert.match(rd, /const closeTitle = `\$\{to\} - \$\{closeThen\}`, sendTitle = `\$\{to\} - \$\{stays\}`;/);
  // ...whatever its agent is doing: the server stops it under the close (concierge.close_after_send)
  assert.match(rd, /const closeThen = "then the task closes";/);
  assert.match(rd, /\$\{closeWord\} sends this to \$\{replyContext\(r\)\}[^`]*- \$\{closeThen\}; \$\{sendWord\} sends it and \$\{stays\}\./);
});

test("a send nobody could confirm keeps which send was pressed: Check delivery and Send anyway close only after Send and close", () => {
  assert.match(rd, /const closing = new Set\(\);/);
  assert.match(rd, /if \(close !== undefined\) \{ if \(close\) closing\.add\(r\.ReviewId\); else closing\.delete\(r\.ReviewId\); \}/);
  assert.match(rd, /const sendAnyway = \(\) => decide\("approve", true\);/);
  assert.match(rd, /run: \(\) => decide\("approve"\), title: delivery\.line/);
});

test("the line never wraps: Send folds into the ▾ beside Send and close, never the other way, and an advised Send stays out", () => {
  assert.match(rd, /flexWrap: paired \? "nowrap" : "wrap"/);
  assert.match(rd, /const paired = twoSends \|\| twoApproves;/);
  const jsx = rd.slice(rd.indexOf(") : twoSends ? ("), rd.indexOf("// ...a calendar answer's note may be empty"));
  assert.ok(jsx.indexOf('data-tq-send="close"') < jsx.indexOf("{foldMore("), "Send and close is never in the ▾");
  assert.match(jsx, /foldMore\(\[\{ id: no\("approve"\)/);
  assert.match(rd, /data-tq-send-more="" data-tq-bar-more=""/);
  // ...an advised Send has no rank, so the bar's fold never takes it
  assert.match(rd, /paired \? \{ \.\.\.\(sendLit \? \{\} : \{ send: 1 \}\)/);
});

// A PHONE'S INVITE (the owner, 2026-11-15: an action row is ONE line, what does not fit folds into its ▾): "Propose this time and close", the ▾
// and Accept / Decline ran off the card's right edge at 390px - the card measured only its own Send. The line folds on the Tasks bar's road
// (foldBar): Send first, then the other answers, into the one ▾; the filled move never
test("an invite's other answers fold into the card's ▾ after Send, on the bar's own fold road", () => {
  assert.match(rd, /import \{ useFoldBar \} from "\.\/foldBar\.js";/);
  assert.doesNotMatch(rd, /foldSend|new ResizeObserver\(fit\)/, "the card keeps no second measure of its own");
  assert.match(rd, /data-tq-cal-instead=\{a\} data-tq-bar-item=\{`cal:\$\{a\}`\} style=\{bar\.shown\(`cal:\$\{a\}`\) \? undefined : HIDE\}/);
  assert.match(rd, /data-tq-send="open" data-tq-bar-item="send" style=\{folded \? HIDE : undefined\}/);
  // the card's line at 390px: [Propose this time and close 182] [Propose this time 128] [Accept 66] [Decline 68] in ~300px, 6px apart, a 30px ▾
  const line = [{ id: "#0", w: 182, rank: 0 }, { id: "send", w: 128, rank: 1 }, { id: "cal:accept", w: 66, rank: 2 }, { id: "cal:decline", w: 68, rank: 2 }];
  assert.deepEqual(barFolds(line, 480, 6, 30), [], "a desk holds all four");
  assert.deepEqual(barFolds(line, 380, 6, 30), ["send"], "Send goes first");
  assert.deepEqual(barFolds(line, 300, 6, 30), ["send", "cal:accept", "cal:decline"], "then Accept and Decline - nothing left past the edge");
  assert.ok(182 + 6 + 30 <= 300, "what stays fits the card");
  // ...and each folded answer is the press its button was
  assert.match(rd, /run: \(\) => \{ setSendAt\(null\); answerInstead\(a\); \}/);
});

// WHAT IT DID, ONE LINE A STEP - the general agent's trail (agentSteps.js), drawn here so the Assistant's chat draws its own steps the
// same way: looking into the app's own trouble (troubleshoot.py) shows what it read and pressed, as an agent's work does (the owner,
// 2026-10-23: "if we do that we need to see what it's thinking like general agent").
import React from "react";
import { CircularProgress } from "@mui/material";
import SearchIcon from "@mui/icons-material/SearchRounded";
import WebIcon from "@mui/icons-material/LanguageRounded";
import BrowserIcon from "@mui/icons-material/WebRounded";
import FileIcon from "@mui/icons-material/DescriptionOutlined";
import WriteIcon from "@mui/icons-material/EditNoteRounded";
import FolderIcon from "@mui/icons-material/FolderOpenOutlined";
import FindIcon from "@mui/icons-material/ManageSearchRounded";
import CommandIcon from "@mui/icons-material/TerminalRounded";
import MailIcon from "@mui/icons-material/MailOutline";
import TaskIcon from "@mui/icons-material/TaskAltRounded";
import DataIcon from "@mui/icons-material/StorageRounded";
import PlanIcon from "@mui/icons-material/ChecklistRounded";
import HelperIcon from "@mui/icons-material/GroupsOutlined";
import SyncIcon from "@mui/icons-material/SyncRounded";
import ToolIcon from "@mui/icons-material/BuildOutlined";
import ThoughtIcon from "@mui/icons-material/LightbulbOutlined";
import { Md } from "./md.jsx";
import { stepLabel } from "./agentSteps.js";
import "./agentStepRows.css";

// A SMALL MARK BY KIND (the owner, 2026-11-05: "look how other chat libraries show intermediately the tool calls"): a search, a web page, a
// file, a command, the browser - read at a glance down the column, the words beside it say which
const ICON = { web: SearchIcon, page: WebIcon, read: FileIcon, skill: FileIcon, edit: WriteIcon, list: FolderIcon, search: FindIcon, run: CommandIcon, mail: MailIcon,
  task: TaskIcon, data: DataIcon, plan: PlanIcon, helper: HelperIcon, sync: SyncIcon, tool: ToolIcon, thought: ThoughtIcon };
export const iconOf = (step) => (step.kind === "page" && step.browser ? BrowserIcon : ICON[step.kind] || null);
const Mark = ({ step }) => { const I = iconOf(step); return I ? <I aria-hidden className="tq-aui-step-icon" /> : <span className="tq-aui-tool-dot" />; };

// A step is one line. What it did is a row whose raw call - the command, its output - waits behind the row's own disclosure, for
// debugging; what it SAID is its own words, in the type the answer is in.
// ...a failure the agent made good by trying again (`recovered`, agentSteps.stepsOf) says so quietly; red is for one it did not
// ...and one Taskuary held for the owner's yes (`held`) waits, quietly - its card below says what Approve runs
// ...and a look whose non-zero exit was its answer (`none`: `ls notes*`, nothing there) found none - plainly, no red
const STATUS_WORD = { running: "working", recovered: "retried - worked", held: "waits for your yes", refused: "not run", none: "found none", error: "failed" };
import { whyFailed } from "./stepWhy.js";
// ...a command shown as itself (agentSteps `code`) sits in a code span inside its words: "Ran `git log --oneline -10`"
const Label = ({ step }) => {
  const t = stepLabel(step), at = step.code ? t.indexOf(step.code) : -1;
  return at < 0 ? <span>{t}</span> : <span>{t.slice(0, at)}<code className="tq-aui-step-code">{step.code}</code>{t.slice(at + step.code.length)}</span>;
};
export const StepRow = ({ step }) => {
  if (step.kind === "said") return <div className="tq-aui-said"><Md text={step.summary} /></div>;
  if (step.kind === "note" || step.kind === "error") return <div className={`tq-aui-note tq-aui-note-${step.kind}`}>{step.summary}</div>;
  // ...and the one at work now says what it is doing, with a quiet spinner where its word was
  // ...one still at work while later ones finished runs alongside them, and says so (agentSteps `alongside`)
  // ...and the files the agent named for it that its title does not (agentSteps.agentWords), as quiet chips beside its words
  const head = <><Mark step={step} /><Label step={step} />
    {(step.chips || []).map((c) => <span key={c} className="tq-aui-step-chip" data-tq-step-chip="">{c}</span>)}
    {!!step.outcome && <span className="tq-aui-step-outcome" data-tq-step-outcome=""> - {step.outcome}</span>}
    {step.times > 1 && <span className="tq-aui-step-outcome" data-tq-step-times=""> ({step.times} times)</span>}
    {step.status === "running" ? <>{step.alongside && <em data-tq-step-alongside="">still working in parallel</em>}
      <CircularProgress size={10} thickness={5} className="tq-aui-step-spin" aria-label="working" /></>
      : step.status !== "done" && <em>{STATUS_WORD[step.status] || "failed"}</em>}</>;
  const cls = `tq-aui-step tq-aui-step-${step.kind} tq-aui-tool-${step.status === "done" ? "complete" : step.status}`;
  // ...a step that FAILED opens on why, in one plain line, and only then the tool's raw output, folded (the owner, 2026-11-05: "i clicked on it it
  // made no sense" - a stack of tool text with no reason in front of it)
  const failed = ["error", "recovered"].includes(step.status);
  // ...a helper's own steps open under its row (agentSteps `kids`), never interleaved with the main agent's
  if (step.kids?.length) return <details className={`${cls} tq-aui-step-helper`} data-tq-helper=""><summary>{head}</summary>
    <div className="tq-aui-helper-steps"><AgentSteps data={{ steps: step.kids }} /></div></details>;
  // ...A COMMAND AT WORK IS THE ROW IT WILL BE WHEN DONE (the owner, 2026-11-23: "on everything mode it flashes black for the commands then closes
  // quickly"): its newest output (agentSteps.tailOf) waits behind the row's own disclosure, as the whole of it does once it ends - one <details>
  // all its life, so nothing opens or shuts by itself and a row he opened stays open as it finishes
  const body = step.tail ? [step.raw, `→ ${step.tail}`].filter(Boolean).join("\n") : step.detail;
  return body
    ? <details className={cls}><summary>{head}</summary>
      {failed && <div className="tq-aui-step-why" data-tq-step-why="">{step.why || whyFailed(step.detail, step.own)}{step.status === "recovered" ? " It tried again another way, and that worked." : ""}</div>}
      {failed ? <details className="tq-aui-step-raw"><summary>Raw output</summary><pre>{body}</pre></details>
        : <pre {...(step.tail ? { "data-tq-step-tail": "" } : {})}>{body}</pre>}</details>
    : <div className={cls}><div className="tq-aui-step-line">{head}</div></div>;
};
export const AgentSteps = ({ data }) => (
  <div className="tq-aui-steps">{(data?.steps || []).map((st) => <StepRow key={st.id} step={st} />)}</div>
);

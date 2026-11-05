// WHAT IT DID, ONE LINE A STEP - the general agent's trail (agentSteps.js), drawn here so the Assistant's chat draws its own steps the
// same way: looking into the app's own trouble (troubleshoot.py) shows what it read and pressed, as an agent's work does (the owner,
// 2026-10-23: "if we do that we need to see what it's thinking like general agent").
import React from "react";
import { Md } from "./md.jsx";
import "./agentStepRows.css";

// A step is one line. What it did is a row whose raw call - the command, its output - waits behind the row's own disclosure, for
// debugging; what it SAID is its own words, in the type the answer is in.
// ...a failure the agent made good by trying again (`recovered`, agentSteps.stepsOf) says so quietly; red is for one it did not
// ...and one Taskuary held for the owner's yes (`held`) waits, quietly - its card below says what Approve runs
// ...and a look whose non-zero exit was its answer (`none`: `ls notes*`, nothing there) found none - plainly, no red
const STATUS_WORD = { running: "working", recovered: "retried - worked", held: "waits for your yes", none: "found none", error: "failed" };
import { whyFailed } from "./stepWhy.js";
export const StepRow = ({ step }) => {
  if (step.kind === "said") return <div className="tq-aui-said"><Md text={step.summary} /></div>;
  if (step.kind === "note" || step.kind === "error") return <div className={`tq-aui-note tq-aui-note-${step.kind}`}>{step.summary}</div>;
  const head = <><span className="tq-aui-tool-dot" /><span>{step.summary}</span>
    {step.status !== "done" && <em>{STATUS_WORD[step.status] || "failed"}</em>}</>;
  const cls = `tq-aui-step tq-aui-step-${step.kind} tq-aui-tool-${step.status === "done" ? "complete" : step.status}`;
  // ...a step that FAILED opens on why, in one plain line, and only then the tool's raw output, folded (the owner, 2026-11-05: "i clicked on it it
  // made no sense" - a stack of tool text with no reason in front of it)
  const failed = ["error", "recovered"].includes(step.status);
  return step.detail
    ? <details className={cls}><summary>{head}</summary>
      {failed && <div className="tq-aui-step-why" data-tq-step-why="">{whyFailed(step.detail)}{step.status === "recovered" ? " It tried again another way, and that worked." : ""}</div>}
      {failed ? <details className="tq-aui-step-raw"><summary>Raw output</summary><pre>{step.detail}</pre></details> : <pre>{step.detail}</pre>}</details>
    : <div className={cls}><div className="tq-aui-step-line">{head}</div></div>;
};
export const AgentSteps = ({ data }) => (
  <div className="tq-aui-steps">{(data?.steps || []).map((st) => <StepRow key={st.id} step={st} />)}</div>
);

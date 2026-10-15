// The setup's next step, in the Advisor's own bar over the row (setupLine.js) - the same .tq-next the Advisor draws in.
import React from "react";
import { useSetupLine } from "./setupLine.js";

export default function SetupLine() {
  const text = useSetupLine();
  return text ? <div className="tq-next" role="status" data-tq-setup-line=""><div className="tq-next-txt">{text}</div></div> : null;
}

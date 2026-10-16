// WHAT THIS INSTALL CAN DO (GET /api/capabilities): coding exists only where a coding tool is connected (agents.coding_ready) -
// the screens that offer coding ask here and hide it when there is none (the owner, 2026-10-16: "if no cli tool like cloud api
// tools no coding"). Asked once; asked again when setup moves (a CLI connected there brings coding back). Until the answer is in,
// coding shows - a coder never loses the button to a slow read.
import { useEffect, useState } from "react";
import api from "./api";

let asked = null;
export const capabilities = () => (asked ||= api.get("/api/capabilities").then(({ data }) => data || {})
  .catch(() => { asked = null; return {}; }));
if (typeof window !== "undefined") window.addEventListener?.("tq-setup-changed", () => { asked = null; });

export function useCoding() {
  const [coding, setCoding] = useState(true);
  useEffect(() => {
    let on = true;
    const read = () => capabilities().then((c) => on && setCoding(c.coding !== false));
    read();
    window.addEventListener("tq-setup-changed", read);
    return () => { on = false; window.removeEventListener("tq-setup-changed", read); };
  }, []);
  return coding;
}

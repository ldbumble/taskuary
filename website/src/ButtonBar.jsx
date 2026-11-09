// ONE BUTTON ROW, EVERYWHERE (the owner, 2026-11-06: "make it sections and not all different sizes", and of the New dialog's footer:
// "this is too thick. it should just be button wide and button should be on left ... Reusable code is always the best"). A task's row of
// moves (TaskPage MovesLine) and every dialog's actions draw through this: one height, padding, font and radius, outlined; the one lit
// move alone filled - a task's Advisor pick (`.tq-ab.row.p`), a dialog's main button (`variant="contained"`); a red Delete keeps its red.
// Left-aligned under the content, as tall as a button, no band. Sections: <ButtonBar.Sep /> between groups, never beside an empty one.
import React from "react";
import { Box } from "@mui/material";
import { ACCENT, INK } from "./theme.jsx";

export const ROW_BTN = { height: 28, minHeight: 28, minWidth: 0, px: 1.5, py: 0, fontSize: 12, fontWeight: 600, lineHeight: 1, letterSpacing: 0, textTransform: "none",
  borderRadius: 99, border: "1px solid var(--tq-border, #b9c3cc)", bgcolor: "var(--tq-panel, #fff)", backgroundImage: "none", color: INK, boxShadow: "none", boxSizing: "border-box",
  display: "inline-flex", alignItems: "center", flexShrink: 0, whiteSpace: "nowrap" };
const LIT = { bgcolor: ACCENT, borderColor: ACCENT, color: "#fff" };
const BTN = "& .tq-ab.row, & .MuiButton-root", FILL = "& .tq-ab.row.p, & .MuiButton-contained:not(.MuiButton-containedError)";
export const ROW_LOOK = {
  [BTN]: ROW_BTN, "& .MuiButton-startIcon": { mr: 0.75, ml: 0 },
  "& .tq-ab.row:hover:not(:disabled), & .MuiButton-root:hover": { bgcolor: "var(--tq-panel, #f1f4f7)", borderColor: ACCENT, boxShadow: "none" },
  [FILL]: LIT, "& .tq-ab.row.p:hover:not(:disabled), & .MuiButton-contained:not(.MuiButton-containedError):hover": { bgcolor: "#46586a", borderColor: "#46586a" },
  "& .MuiButton-containedError": { bgcolor: "error.main", borderColor: "error.main", color: "#fff" }, "& .MuiButton-containedError:hover": { bgcolor: "error.dark" },
  "& .MuiButton-root.Mui-disabled": { opacity: 0.5, color: INK }, "& .MuiButton-contained.Mui-disabled": { ...LIT, opacity: 0.45 },
  "& .tq-row-sep": { width: "1px", height: 18, bgcolor: "var(--tq-inset, #d8d1c5)", flexShrink: 0 } };
// a dialog's actions: under its content, left, one button tall - `children` in order, the main move first
export function ButtonBar({ children, sx = {}, ...rest }) {
  return <Box data-tq-button-bar="" sx={{ ...ROW_LOOK, display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", justifyContent: "flex-start", px: 3, pt: 0.5, pb: 2, ...sx }} {...rest}>
    {children}</Box>;
}
ButtonBar.Sep = function Sep() { return <span className="tq-row-sep" aria-hidden="true" />; };

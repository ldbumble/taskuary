// CONNECT AN AI, the one button every "no AI is connected" message carries (owner-approved, 2026-10-21): each said an AI was needed
// and gave no way to connect one. It opens Connections at the AI cards (words.json `ai`); `onGo` runs first - a sheet closes itself.
import React from "react";
import { Button } from "@mui/material";
import { openAppLink } from "./appLinks.js";
import { place } from "./words.js";

export const CONNECT_AI = "Connect an AI";
export const connectAi = () => openAppLink(place("ai").href);

export default function ConnectAi({ onGo, variant = "contained", size = "small", sx }) {
  return <Button size={size} variant={variant} disableElevation data-tq-connect-ai=""
    onClick={(e) => { e.stopPropagation(); onGo?.(); connectAi(); }} sx={{ whiteSpace: "nowrap", flex: "none", ...sx }}>{CONNECT_AI}</Button>;
}

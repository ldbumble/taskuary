import React, { createContext, useContext, useMemo, useState, useSyncExternalStore } from "react";
import { CssBaseline, IconButton, ThemeProvider, Tooltip } from "@mui/material";
import DarkModeOutlinedIcon from "@mui/icons-material/DarkModeOutlined";
import LightModeOutlinedIcon from "@mui/icons-material/LightModeOutlined";
import { createThemeController } from "./appTheme.js";
import { createAppTheme } from "./theme.jsx";
import "./appTheme.css";

const Appearance = createContext(null);
export function AppThemeProvider({ children }) {
  const [controller] = useState(() => createThemeController());
  const mode = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const theme = useMemo(() => createAppTheme(mode), [mode]);
  return <Appearance.Provider value={{ mode, toggle: controller.toggle }}>
    <ThemeProvider theme={theme}><CssBaseline />{children}</ThemeProvider>
  </Appearance.Provider>;
}

export function ThemeToggle() {
  const { mode, toggle } = useContext(Appearance);
  const label = mode === "dark" ? "Switch to light theme" : "Switch to dark theme";
  return <Tooltip title={label}>
    <IconButton size="small" onClick={toggle} aria-label={label} aria-pressed={mode === "dark"}>
      {mode === "dark" ? <LightModeOutlinedIcon sx={{ fontSize: 18 }} /> : <DarkModeOutlinedIcon sx={{ fontSize: 18 }} />}
    </IconButton>
  </Tooltip>;
}

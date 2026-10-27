import "./fonts.css";
import React from "react";
import { createRoot } from "react-dom/client";
import TaskHubPage from "./TaskHubPage.jsx";
import { startTracking } from "./demoTrack";
import { needsLink, UNLINKED_LINE, UNLINKED_EVENT } from "./unlinked.js";
import { record } from "./lastError.js";
import BugReportDialog from "./BugReportDialog.jsx";
import { label as btnLabel } from "./buttons.js";
import { installOneLine } from "./oneLine.js";
installOneLine();
import { installTouchHints } from "./touchHint.js";
installTouchHints();
import { installSecondClick } from "./secondClick.js";
installSecondClick();

// a crash that draws no Assistant line still leaves its report ready behind the Help icon
window.addEventListener("error", (e) => record(e.error || e.message));
window.addEventListener("unhandledrejection", (e) => record(e.reason));

// A page left open across a rebuild asks for chunk names that no longer exist ("Failed to fetch
// dynamically imported module .../HubView-<old hash>.js", the owner, 2026-09-23, mid-walk). Vite
// raises this for EVERY lazy chunk, so one reload here covers what lazyGeneral.js covered for one.
// Once per session: a second failure is a real error and goes to the boundary instead of looping.
window.addEventListener("vite:preloadError", (e) => {
  let tried = false;
  try { tried = sessionStorage.getItem("tq-chunk-reload") === "1"; sessionStorage.setItem("tq-chunk-reload", "1"); } catch { /* storage disabled */ }
  if (tried) return;
  e.preventDefault();
  window.location.reload();
});
window.addEventListener("load", () => setTimeout(() => { try { sessionStorage.removeItem("tq-chunk-reload"); } catch { /* storage disabled */ } }, 10000));

// A render error must land on the PAGE, not take the app down: one bad row in one view was
// white-screening everything, terminal sessions included. The boundary names the error, and
// "try again" just re-renders - state and sessions live server-side, so nothing is lost.
class Boundary extends React.Component {
  // the fallback replaces the top bar, Help with it: the crash's own report has to be offered here
  state = { err: null, report: null };
  static getDerivedStateFromError(err) { return { err }; }
  componentDidCatch(err, info) { console.error("render error:", err, info?.componentStack); record(err); }
  render() {
    if (!this.state.err) return this.props.children;
    return (
      <div style={{ maxWidth: 720, margin: "80px auto", padding: 24, fontFamily: "'IBM Plex Sans', 'Segoe UI', sans-serif",
        background: "#fff", border: "1px solid #f3d1d1", borderRadius: 12 }}>
        <div style={{ fontWeight: 600, fontSize: 16, color: "#6b2733", marginBottom: 8 }}>
          Something in this view failed to draw
        </div>
        <div style={{ fontSize: 13, color: "#1f2430", marginBottom: 12 }}>
          Your data and any running agent sessions are untouched — they live on the server, not in this page.
        </div>
        <pre style={{ fontSize: 11.5, background: "#f4f1ec", border: "1px solid #e1dcd5", borderRadius: 8,
          padding: 12, whiteSpace: "pre-wrap", color: "#5e685f", maxHeight: 180, overflow: "auto" }}>
          {String(this.state.err?.stack || this.state.err)}
        </pre>
        <button onClick={() => this.setState({ err: null, report: null })}
          style={{ padding: "6px 16px", borderRadius: 8, border: "1px solid #d8cfbe", background: "#eae4d8",
            color: "#55697a", fontWeight: 600, cursor: "pointer" }}>
          {btnLabel("try_again")}
        </button>
        <button onClick={() => location.reload()}
          style={{ marginLeft: 8, padding: "6px 16px", borderRadius: 8, border: "1px solid #e1dcd5",
            background: "#fff", color: "#1f2430", cursor: "pointer" }}>
          Reload the app
        </button>
        <button type="button" onClick={() => this.setState({ report: { message: String(this.state.err?.message || this.state.err), stack: this.state.err?.stack } })}
          style={{ marginLeft: 12, padding: 0, border: 0, background: "none", color: "#4d4a43", fontSize: 12, cursor: "pointer", textDecoration: "underline" }}>
          {btnLabel("report_bug")}
        </button>
        <BugReportDialog open={!!this.state.report} onClose={() => this.setState({ report: null })} screen="crash" error={this.state.report} />
      </div>
    );
  }
}

const unlinked = needsLink(document, typeof localStorage === "undefined" ? null : localStorage);
const Unlinked = () => <div style={{ margin: "80px auto", maxWidth: 560, fontFamily: "'IBM Plex Sans', 'Segoe UI', sans-serif", fontSize: 14, color: "#5e685f" }}>{UNLINKED_LINE}</div>;
const root = createRoot(document.getElementById("root"));
root.render(unlinked ? <Unlinked /> : <Boundary><TaskHubPage /></Boundary>);
// the token went stale under an open page (unlinked.staleToken): every call would meet 401 from here on
window.addEventListener(UNLINKED_EVENT, () => root.render(<Unlinked />), { once: true });

startTracking();   // the static demo only, and only on taskuary.com

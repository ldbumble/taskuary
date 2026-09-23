import React from "react";
import { createRoot } from "react-dom/client";
import TaskHubPage from "./TaskHubPage.jsx";
import { startTracking } from "./demoTrack";

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
  state = { err: null };
  static getDerivedStateFromError(err) { return { err }; }
  componentDidCatch(err, info) { console.error("render error:", err, info?.componentStack); }
  render() {
    if (!this.state.err) return this.props.children;
    return (
      <div style={{ maxWidth: 720, margin: "80px auto", padding: 24, fontFamily: "'IBM Plex Sans', 'Segoe UI', sans-serif",
        background: "#fff", border: "1px solid #f3d1d1", borderRadius: 12 }}>
        <div style={{ fontWeight: 800, fontSize: 16, color: "#6b2733", marginBottom: 8 }}>
          Something in this view failed to draw
        </div>
        <div style={{ fontSize: 13, color: "#1f2430", marginBottom: 12 }}>
          Your data and any running agent sessions are untouched — they live on the server, not in this page.
        </div>
        <pre style={{ fontSize: 11.5, background: "#f4f1ec", border: "1px solid #e1dcd5", borderRadius: 8,
          padding: 12, whiteSpace: "pre-wrap", color: "#5e685f", maxHeight: 180, overflow: "auto" }}>
          {String(this.state.err?.stack || this.state.err)}
        </pre>
        <button onClick={() => this.setState({ err: null })}
          style={{ padding: "6px 16px", borderRadius: 8, border: "1px solid #d8cfbe", background: "#eae4d8",
            color: "#55697a", fontWeight: 700, cursor: "pointer" }}>
          Try again
        </button>
        <button onClick={() => location.reload()}
          style={{ marginLeft: 8, padding: "6px 16px", borderRadius: 8, border: "1px solid #e1dcd5",
            background: "#fff", color: "#1f2430", cursor: "pointer" }}>
          Reload the app
        </button>
      </div>
    );
  }
}

createRoot(document.getElementById("root")).render(<Boundary><TaskHubPage /></Boundary>);

startTracking();   // the static demo only, and only on taskuary.com

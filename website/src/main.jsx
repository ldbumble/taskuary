import React from "react";
import { createRoot } from "react-dom/client";
import TaskHubPage from "./TaskHubPage.jsx";

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
      <div style={{ maxWidth: 720, margin: "80px auto", padding: 24, fontFamily: "'Inter', 'Segoe UI', sans-serif",
        background: "#fff", border: "1px solid #f3d1d1", borderRadius: 12 }}>
        <div style={{ fontWeight: 800, fontSize: 16, color: "#b91c1c", marginBottom: 8 }}>
          Something in this view failed to draw
        </div>
        <div style={{ fontSize: 13, color: "#1f2430", marginBottom: 12 }}>
          Your data and any running agent sessions are untouched — they live on the server, not in this page.
        </div>
        <pre style={{ fontSize: 11.5, background: "#f7f8fa", border: "1px solid #e3e6ec", borderRadius: 8,
          padding: 12, whiteSpace: "pre-wrap", color: "#697386", maxHeight: 180, overflow: "auto" }}>
          {String(this.state.err?.stack || this.state.err)}
        </pre>
        <button onClick={() => this.setState({ err: null })}
          style={{ padding: "6px 16px", borderRadius: 8, border: "1px solid #c9cff0", background: "#eef0ff",
            color: "#4f46e5", fontWeight: 700, cursor: "pointer" }}>
          Try again
        </button>
        <button onClick={() => location.reload()}
          style={{ marginLeft: 8, padding: "6px 16px", borderRadius: 8, border: "1px solid #e3e6ec",
            background: "#fff", color: "#1f2430", cursor: "pointer" }}>
          Reload the app
        </button>
      </div>
    );
  }
}

createRoot(document.getElementById("root")).render(<Boundary><TaskHubPage /></Boundary>);

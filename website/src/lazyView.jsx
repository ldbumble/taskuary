// A view that is not on the first screen, kept out of the entry chunk.
//
// React.lazy alone suspends on the first draw even when the chunk is already in, and a chunk fetched only when drawn made
// deep links wait on a second round trip. So the chunk is asked for as soon as the first screen is up (the browser's first
// idle moment, or at once when something draws it sooner), and an instance drawn after it landed renders the component
// itself - synchronously, exactly as a static import did. Only an instance drawn before it landed goes through Suspense
// (nothing for that moment), and it keeps that element type for its whole life, so a later re-render never remounts it.
import React, { Suspense, useRef } from "react";

const idle = (f) => (typeof window !== "undefined" && window.requestIdleCallback ? window.requestIdleCallback(f, { timeout: 1500 }) : setTimeout(f, 200));

export function lazyView(load, pick = (m) => m.default) {
  let C = null, ready = null;
  const start = () => ready || (ready = load().then((m) => { C = pick(m); return { default: C }; }));
  idle(() => start().catch(() => { /* drawn, the lazy rethrows to the boundary; a stale build reloads (main.jsx) */ }));
  const Late = React.lazy(start);
  return function View(props) {
    const was = useRef(C);
    const Now = was.current;
    return Now ? <Now {...props} /> : <Suspense fallback={null}><Late {...props} /></Suspense>;
  };
}

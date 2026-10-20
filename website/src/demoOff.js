// demoApi.js as the app on a real server sees it (vite.config.js aliases it here outside the demo build): every
// reader asks DEMO first, so these answer only that question and keep the recorded world out of the bundle.
export const DEMO = false, DEMO_GUIDED = false;
export const demoJourneySnapshot = () => ({ phase: "request" });
export const onDemoJourney = () => () => {};
export const startDemoAssistant = () => Promise.reject(new Error("not the demo"));
export default null;

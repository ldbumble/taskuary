const KEY = "taskuary-microphone-provider";
export const voiceChoice = () => {
  try { return ["windows", "browser"].includes(localStorage.getItem(KEY)) ? localStorage.getItem(KEY) : "auto"; }
  catch { return "auto"; }
};
export function chooseVoice(value) {
  localStorage.setItem(KEY, value);
  window.dispatchEvent(new Event("taskuary-voice-choice"));
}
export function micRoute(voice, browser, choice) {
  if (choice === "windows") return voice?.builtin ? "windows" : "off";
  if (choice === "browser") return browser ? "browser" : "off";
  // Automatic: a voice card, else Windows voice typing on this computer (its own Win+H - the owner, 2026-11-16: "Use the Windows voice rec"),
  // else the tab's own recogniser (a Mac, Linux), else none
  return voice?.ready ? "connector" : voice?.builtin ? "windows" : browser ? "browser" : "off";
}

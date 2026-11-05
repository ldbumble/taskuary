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
  return voice?.ready ? "connector" : browser ? "browser" : voice?.builtin ? "windows" : "off";
}

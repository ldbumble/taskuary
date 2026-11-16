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
  // Automatic: a voice card (or an AI card that hears), else the tab's own recogniser, else none - the press offers Local Whisper in one press.
  // Windows voice typing only when chosen (2026-11-16: its PowerShell/WinRT child failed on PCs where every other app hears the mic)
  return voice?.ready ? "connector" : browser ? "browser" : "off";
}

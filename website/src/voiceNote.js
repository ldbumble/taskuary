const MARK = "🎤 Voice note";

// Timeline rows carry Preview, while the open panel carries the same message as BodyText.
// Voice-note controls must follow whichever copy the panel actually has.
export const voiceNoteBody = (row, message) => String(message?.BodyText ?? row?.BodyText ?? row?.Preview ?? "");

export const isVoicePlaceholder = (body) => {
  const text = String(body || "");
  return text.startsWith(MARK) && text.includes(" - not transcribed");
};

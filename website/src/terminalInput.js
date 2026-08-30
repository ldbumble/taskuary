// Clipboard image handling lives outside the React/xterm lifecycle so its two decisions stay
// testable: only real image files are intercepted, and the terminal receives a plain local-path
// instruction that every supported coding CLI can act on.
export const pastedImageFiles = (clipboardData) => [...(clipboardData?.items || [])]
  .filter((item) => item.kind === "file" && /^image\//.test(item.type))
  .map((item) => item.getAsFile())
  .filter(Boolean);

export const pastedImagePrompt = (paths) => !paths.length ? ""
  : `${paths.length === 1 ? "Pasted image - open it with your image/Read tool:"
    : "Pasted images - open them with your image/Read tool:"} ${paths.map((path) => `"${path}"`).join(" ")}`;

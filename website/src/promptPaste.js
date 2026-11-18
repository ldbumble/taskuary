// WHAT A PASTE IS (2026-11-18). Word and Excel put the copied words on the clipboard AND a picture of them: the box took the picture and
// cancelled the paste, so a row copied from a sheet arrived as a screenshot of itself and the words never came. A paste that carries words is
// those words; the files it carries are taken only when there are no words with them (a screenshot, a copied picture, a copied file).
// `takes(file)`: whether this box takes the file at all
export const pastedFiles = (clipboard, takes = () => true) => {
  if (String(clipboard?.getData?.("text/plain") || "").trim()) return [];
  return [...(clipboard?.files || [])].filter(takes);
};

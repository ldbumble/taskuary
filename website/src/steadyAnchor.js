// A POPOVER STAYS WHERE ITS BUTTON WAS PRESSED (overnight walk, 2026-10-26): a lit move from a folded group stands on the row only while
// it is lit, and the press clears the light - so "remind me Monday", then its lit Remind me, folded the button back into its ▾ under the
// picker it had just opened, and MUI drew the picker at the screen's top-left corner, a whole screen from the row. The anchor is the
// button while it is drawn, and the place it stood once it is gone.
export const steady = (el) => {
  if (!el?.getBoundingClientRect) return el;
  const at = el.getBoundingClientRect();
  return { nodeType: 1, getBoundingClientRect: () => (el.isConnected && el.getClientRects().length ? el.getBoundingClientRect() : at) };
};

// The fade belongs to the bottom edge of the Timeline viewport, never to a row or its age.
// Rows passing behind this band lighten; scrolling them upward reveals them at full contrast again.
export const FADE_BANDS = {
  off: null,
  gentle: { height: 100, solidAt: 100 },
  normal: { height: 150, solidAt: 94 },
  sharp: { height: 200, solidAt: 88 },
};

export const FADE_MODES = Object.keys(FADE_BANDS);

export const fadeBand = (mode = "normal") =>
  Object.prototype.hasOwnProperty.call(FADE_BANDS, mode) ? FADE_BANDS[mode] : FADE_BANDS.normal;

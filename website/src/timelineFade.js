// How much a Timeline row dims with age (Settings > Display > Fade older Timeline items). Kept out
// of the React tree so the curve itself is testable: the whole point of the setting is that each
// mode reaches a visibly different place at the same age, and only a table of numbers proves that.
//
// {grace hours before it starts, span hours from there to the floor, floor}. On the cream palette a
// gentle is still visibly a fade within one morning; otherwise the setting says it is on while
// rendering a three-hour span at effectively full opacity. The floors keep every row readable.
export const FADE = { off: null, gentle: [0.5, 6, 0.68], normal: [0.25, 4, 0.5], sharp: [0, 2.5, 0.35] };

export const FADE_MODES = Object.keys(FADE);

// Purely visual. FeedView restores the row a person opens, while the rest of the rail keeps its
// age gradient; hover and scrolling must not make the whole list flash dark/full/dark.
export const ageOpacity = (hours, mode = "normal") => {
  const c = FADE[mode];
  if (!c || !(hours > 0)) return 1;                 // unknown mode, 'off', a future or unparsed time
  const [grace, span, floor] = c;
  return hours <= grace ? 1 : Math.max(floor, 1 - (1 - floor) * (hours - grace) / span);
};

// A deliberate filter is already doing the visual prioritization. Dimming its matches again can
// make the whole result set look disabled when every match happens to be old.
export const timelineOpacity = (hours, mode = "normal", filtered = false) =>
  filtered ? 1 : ageOpacity(hours, mode);

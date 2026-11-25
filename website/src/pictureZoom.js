// A PICTURE OPENED LARGER IS HIS TO ZOOM AND MOVE (PictureView): where it stands is {s, x, y} - s times its fitted size, its centre moved x, y
// from the window's - and `fit` is the fitted picture's size (w, h) in the window's (W, H)
export const FIT = { s: 1, x: 0, y: 0 }, MAX = 8, STEP = 1.5;
const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
// ...never dragged off: it moves only as far as it overhangs the window, and not at all where it does not
const lim = (s, w, W) => Math.max(0, (s * w - W) / 2);
export const pan = (v, { w = 0, h = 0, W = 0, H = 0 } = {}) => v.s <= 1 ? FIT
  : { s: v.s, x: clamp(v.x, -lim(v.s, w, W), lim(v.s, w, W)), y: clamp(v.y, -lim(v.s, h, H), lim(v.s, h, H)) };
// ...zoomed by k about a point (from the window's centre): what is under the pointer or between the fingers stays under them
export const zoomAt = (v, k, a = { x: 0, y: 0 }, fit) => {
  const s = clamp(v.s * k, 1, MAX), r = s / v.s;
  return pan({ s, x: a.x - (a.x - v.x) * r, y: a.y - (a.y - v.y) * r }, fit);
};
// ...and the arrows step round the card's pictures, the last on to the first
export const stepAt = (n, i, d) => n ? (i + d + n) % n : 0;
// ...through those it was handed, where the one pressed is among them, else that one alone
export const keyOf = (f) => f?.path || f?.url || f?.id || f?.name || "";
export const pictureList = (file, files) => (files?.length && files.some((f) => keyOf(f) === keyOf(file)) ? files : file ? [file] : []);

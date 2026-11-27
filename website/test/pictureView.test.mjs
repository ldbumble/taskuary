// A PICTURE ON A CARD OPENS LARGER, TO ZOOM (the owner, 2026-11-25: "you should be able to zoom in on an image that pops up on the white cards if
// you need"): a post's picture, a picture handed over, a run of them - a press opens the one viewer (PictureView) with that picture, the wheel,
// a pinch or + - zoom it about the pointer, a drag moves it only as far as it overhangs, and the arrows step through the card's others.
import test from "node:test";
import assert from "node:assert/strict";
import { FIT, MAX, pan, pictureList, stepAt, zoomAt } from "../src/pictureZoom.js";

const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);

test("a zoom holds still the point it is made about, between fit and eight times", () => {
  const fit = { w: 800, h: 450, W: 800, H: 600 }, at = { x: 200, y: 100 };
  const v = zoomAt(FIT, 2, at, fit);
  near(v.s, 2);
  // ...the picture's point under the pointer, (a - x) / s from its centre, is drawn back under it: x + s * p
  near(v.x + v.s * at.x, at.x); near(v.y + v.s * at.y, at.y);
  const w = zoomAt(v, 1.5, { x: -50, y: 20 }, fit), p = { x: (-50 - v.x) / v.s, y: (20 - v.y) / v.s };
  near(w.x + w.s * p.x, -50); near(w.y + w.s * p.y, 20);
  assert.equal(zoomAt(FIT, 0.5, at, fit), FIT, "never smaller than fitted");
  near(zoomAt({ s: 6, x: 0, y: 0 }, 4, { x: 0, y: 0 }, fit).s, MAX);
});

test("a zoomed picture moves only as far as it overhangs the window", () => {
  const fit = { w: 800, h: 450, W: 800, H: 600 };
  assert.deepEqual(pan({ s: 2, x: 5000, y: 5000 }, fit), { s: 2, x: 400, y: 150 }, "800 wide at 2x overhangs 400 each side; 900 tall in 600 overhangs 150");
  assert.deepEqual(pan({ s: 1.2, x: 0, y: 90 }, fit), { s: 1.2, x: 0, y: 0 }, "540 tall still fits 600: it does not move up or down");
  assert.equal(pan({ s: 1, x: 30, y: 30 }, fit), FIT);
});

test("the arrows step round the card's pictures; the one pressed is where it starts", () => {
  assert.deepEqual([stepAt(3, 2, 1), stepAt(3, 0, -1), stepAt(3, 1, 1), stepAt(0, 0, 1)], [0, 2, 2, 0]);
  const a = { path: "a.png" }, b = { path: "b.png" };
  assert.deepEqual(pictureList(b, [a, b]), [a, b]);
  assert.deepEqual(pictureList(b, [a]), [b], "one not among them stands alone");
  assert.deepEqual(pictureList(b, null), [b]);
});

// ...the real components, drawn through a hook stub: their own children expanded, a press called as the click calls it
const ESB = async (entry, stub) => {
  const hold = setInterval(() => {}, 1000);
  try {
    const { build } = await import("esbuild");
    const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: entry },
      bundle: true, write: false, format: "esm", jsx: "automatic", platform: "node", logLevel: "silent", loader: { ".css": "empty" },
      plugins: [{ name: "stubs", setup(b) {
        b.onResolve({ filter: /.*/ }, (a) => (a.path in stub ? { path: a.path, namespace: "stub" } : undefined));
        b.onLoad({ filter: /.*/, namespace: "stub" }, (a) => ({ contents: stub[a.path], loader: "js" })); } }] });
    const { writeFileSync } = await import("node:fs"), { join } = await import("node:path"), { pathToFileURL } = await import("node:url");
    const f = join((await import("../browser/tempdirs.mjs")).ownTemp("tq-pics-"), "page.mjs"); writeFileSync(f, out.outputFiles[0].text);
    return import(pathToFileURL(f).href);
  } finally { clearInterval(hold); }
};
let slots = [], at = 0, draw = () => {};
globalThis.__R = { useState: (v) => { const i = at++; if (!(i in slots)) slots[i] = typeof v === "function" ? v() : v;
    return [slots[i], (n) => { slots[i] = typeof n === "function" ? n(slots[i]) : n; draw(); }]; },
  useRef: (v) => { const i = at++; if (!(i in slots)) slots[i] = { current: v }; return slots[i]; },
  useEffect: () => {}, useLayoutEffect: () => {}, useMemo: (f) => f(), jsx: (type, props) => ({ type, props: props || {} }), Fragment: "Fragment",
  Children: { toArray: (c) => [].concat(c || []) } };
globalThis.__R.jsxs = globalThis.__R.jsx; globalThis.__R.createElement = (type, props, ...children) => ({ type, props: { ...props, children } });
const MUI = "export const Box = 'Box', Button = 'Button', Checkbox = 'Checkbox', CircularProgress = 'Spin', Typography = 'Typography', Dialog = 'Dialog', IconButton = 'IconButton';";
const BASE = { "react": "export const { useState, useRef, useEffect, useLayoutEffect, useMemo, Children, createElement } = globalThis.__R; export default globalThis.__R;",
  "react/jsx-runtime": "export const { jsx, jsxs, Fragment } = globalThis.__R;", "@mui/material": MUI,
  "./fileSave.js": "export const attUrl = (f) => f.url, useSave = () => ['', () => {}, ''];", "./theme.jsx": "export const INK = '', ACCENT = '', ALERT_INK = '', BORDER = '', DIM = '', FAINT = '', label = {};" };
const ICONS = Object.fromEntries(["Add", "ChevronLeft", "ChevronRight", "Close", "Remove", "OpenInNew"].map((n) => [`@mui/icons-material/${n}`, `export default '${n}';`]));
const expand = (n) => Array.isArray(n) ? n.map(expand) : n && typeof n === "object" && typeof n.type === "function" ? expand(n.type(n.props))
  : n && typeof n === "object" ? { ...n, props: { ...n.props, children: expand(n.props.children) } } : n;
const find = (n, ok, out = []) => { if (Array.isArray(n)) n.forEach((x) => find(x, ok, out)); else if (n && typeof n === "object") { if (ok(n)) out.push(n); find(n.props.children, ok, out); } return out; };
const words = (n) => Array.isArray(n) ? n.map(words).join("") : n && typeof n === "object" ? words(n.props.children) : n == null || n === false ? "" : String(n);
const pic = (name) => ({ id: `output:${name}`, path: name, name, kind: "output", content_type: "image/png", preview: "picture", url: `/api/task-outputs/7/${name}`, handed: true, call: 0 });
const THREE = ["banner-one.png", "banner-two.png", "banner-tall.png"].map(pic);

test("a press on a picture the turn handed over opens the one viewer with that picture, the card's others a step away", async () => {
  const { default: TurnFiles } = await ESB(`export { default } from "./src/TurnFiles.jsx";`, { ...BASE,
    "./PublishedPages.jsx": "export const CopyFile = 'CopyFile', FileDialog = 'FileDialog', Preview = 'Preview', isText = () => false;",
    "./Artifact.jsx": "export default 'Artifact'; export const Items = 'Items';" });
  let tree; slots = []; draw = () => { at = 0; tree = expand(TurnFiles({ files: THREE })); }; draw();
  const viewer = () => find(tree, (n) => n.type === "FileDialog")[0].props, img = () => find(tree, (n) => n.type === "img")[0];
  assert.equal(viewer().file, null, "shut until pressed");
  assert.equal(img().props.style.cursor, "zoom-in", "the cursor says it opens larger");
  find(tree, (n) => n.type === "Items")[0].props.items[1].onPick();
  img().props.onClick();
  assert.equal(viewer().file.name, "banner-two.png", "the picture pressed");
  assert.deepEqual(viewer().files.map((f) => f.name), THREE.map((f) => f.name), "the arrows step through the card's pictures");
});

test("a press on a post card's picture opens it in the card's viewer", async () => {
  const { ReviewCard } = await ESB(`export { ReviewCard } from "./src/Artifact.jsx";`, { ...BASE, ...ICONS,
    "./cardLine.js": "export const lineAt = () => 0, lineStep = () => 0, shownTab = () => null;", "./PassedCard.jsx": "export const PressedButton = 'PressedButton';",
    "./ui.jsx": "export const CcRow = 'CcRow', DraftField = 'DraftField', ToRow = 'ToRow';", "./pressable.js": "export const FOCUS_RING = {}, pressable = () => ({});",
    "./md.jsx": "export const MdLine = 'MdLine';", "./bulkCard.js": "export const listCap = () => 0;",
    "./textDiff.js": "export const changeMarks = () => [], hasChange = () => false, lengthSaid = () => '', wordDiff = () => [];" });
  const seen = [], f = pic("expense-tools.png");
  slots = []; at = 0;
  const tree = expand(ReviewCard({ id: 1, kind: "post", fields: [{ key: "image", type: "picture", value: f.path, file: f }], onView: (x) => seen.push(x) }));
  const img = find(tree, (n) => n.props?.["data-tq-act-image"])[0];
  assert.equal(img.props.sx.cursor, "zoom-in");
  img.props.onClick();
  assert.deepEqual(seen, [f]);
});

test("the viewer fits the picture, zooms at + and -, and its arrows step through the others", async () => {
  const { PictureDialog } = await ESB(`export { PictureDialog } from "./src/PictureView.jsx";`, { ...BASE, ...ICONS, "./overlays.js": "export const useOverlay = () => {};" });
  let tree, closed = 0; slots = []; draw = () => { at = 0; tree = expand(PictureDialog({ file: THREE[0], files: THREE, onClose: () => closed++ })); }; draw();
  const by = (attr) => find(tree, (n) => n.props?.[attr] != null)[0], shown = () => by("data-tq-picture-big");
  assert.equal(shown().props.src, THREE[0].url);
  assert.equal(words(by("data-tq-picture-at")), "1 of 3");
  assert.equal(words(by("data-tq-zoom-at")), "100%");
  assert.match(shown().props.sx.transform, /scale\(1\)/);
  by("data-tq-zoom-in").props.onClick();
  assert.equal(words(by("data-tq-zoom-at")), "150%"); assert.match(shown().props.sx.transform, /scale\(1\.5\)/);
  by("data-tq-zoom-out").props.onClick();
  assert.equal(words(by("data-tq-zoom-at")), "100%");
  by("data-tq-picture-next").props.onClick();
  assert.equal(shown().props.src, THREE[1].url); assert.equal(words(by("data-tq-picture-at")), "2 of 3");
  by("data-tq-picture-prev").props.onClick(); by("data-tq-picture-prev").props.onClick();
  assert.equal(shown().props.src, THREE[2].url, "back past the first to the last");
  assert.equal(closed, 0);
  // ...one picture alone has no arrows and no count
  slots = []; draw = () => { at = 0; tree = expand(PictureDialog({ file: THREE[0], onClose: () => {} })); }; draw();
  assert.equal(by("data-tq-picture-next"), undefined); assert.equal(by("data-tq-picture-at"), undefined);
});

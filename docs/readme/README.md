# README walkthrough images

The README and product guide share these images. The hero is kept separately at
`docs/hero.webp`: the Assistant's Game view, opening on the whole office and zooming into each room.
Regenerate it with `npm exec --yes --package=node@22 -- node website/capture-hero.mjs` (FFmpeg as below). It is an
animated WebP because smooth camera flights cost 20 MB as a GIF; the capture steps the scene's clock one frame per
screenshot, so every frame is exactly 50 ms apart. `--encode` re-encodes the last frames without a browser. These images follow one invented
vendor-spend request through the current React interface, then show a few key
features. The calendar GIF replays the app's meeting entrance and clock pulse.
`06-morning.png` is its static alternative. The privacy SVG is an illustrated flow.

## Regenerate

From the repository root, with frontend dependencies installed, Node 22+, a local
Chromium browser, and FFmpeg (or Python's `imageio_ffmpeg`):

```powershell
npm exec --yes --package=node@22 -- node website/capture-readme.mjs --extras
$env:TASKUARY_BROWSER_PLAIN_ENV='1'   # a local Windows run; CI never sets it
npm exec --yes --package=node@22 -- node website/capture-readme-app.mjs
npm exec --yes --package=node@22 -- node website/render-readme.mjs
```

The task-view pictures - 02 the task in its three sections, 03 the agent's Result, 04 Close out on the drafted reply,
05 the chat window over the row, 12 an FYI batch, 13 a report, 14 the dashboard - come from `capture-readme-app.mjs`. It
starts the browser harness (`website/browser/harness.mjs`): the real backend on a scratch home seeded with the demo world,
outbound sockets blocked. `website/readme_seed.py` writes Ruth's request into that home, then the agent's finished run on
it - its report, the workbook it made, the reply drafted. Each is the Taskuary pane at 1440x900, the rail left out. To
frame only those, add `--app-only` to the render.

The capture starts and closes its own local Vite server and browser. It uses demo
mode, with a capture-only fixture for the calendar, morning digest, current
Timeline response format, CLI cards, and Hub comments. No live account is read,
connected, or changed. The fixture clock is September 3, 2026, at 10:24 local time.

Raw screenshots and animation frames stay in ignored `.codex-tmp/readme/`. The README links carry a `?v=` cache-buster; change it when the pictures change.
Framing lives in `website/render-readme.mjs`: a plain white page with neutral grey type, so the only colour is the
app's own. Most pictures are cropped to a whole card by `card()` in the capture (the smallest box holding given words,
the window grown until none of it is scrolled away, the rest of the chat hidden), so no frame cuts a card's edge;
the rest keep a clip in the shot list. Screenshots are captured at double resolution and framed at 1200 pixels wide.
Product source files and the deployed demo are unchanged.

The first image is the opening card beside the work rail, in the full demo on a fresh chat. It keeps the
filename `01-timeline-sources-and-times.png` from when it showed the Timeline (removed 2026-10-15), so the
README's links stay put; `--timeline-only` captures nothing current.
The LEARNED.md image uses authored example lessons in the real document editor.
To recapture and frame just those two images, add `--memory-update` to both commands.
For just the CLI connections image (including Qwen Code), use `--cli-only`.
For the four key-feature images (CLI, Hub, handoffs, LEARNED.md), capture and render with `--extras-only` (all of them: `--extras`).
For just the first image (the opening card in the full demo, on a fresh chat), use `--home-only` with both commands.

The Hub capture (08) shows "Nothing posted yet" against the current demo fixture (not yet looked into),
so `08-hub.png` is the earlier frame; check it before replacing it.

Review every final image at README width after regenerating: titles, amounts,
source context, action buttons, and the ends of cards must remain visible.

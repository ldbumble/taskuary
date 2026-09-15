# README walkthrough images

The hero is kept separately at `docs/hero.gif`. These images follow one invented
vendor-spend request through the current React interface, then show a few key
features. The calendar GIF replays the app's meeting entrance and clock pulse.
`06-morning.png` is its static alternative. The privacy SVG is an illustrated flow.

## Regenerate

From the repository root, with frontend dependencies installed, Node 22+, a local
Chromium browser, and FFmpeg (or Python's `imageio_ffmpeg`):

```powershell
npm exec --yes --package=node@22 -- node website/capture-readme.mjs
npm exec --yes --package=node@22 -- node website/render-readme.mjs
```

The capture starts and closes its own local Vite server and browser. It uses demo
mode, with a capture-only fixture for the calendar, morning digest, current
Timeline response format, CLI cards, and Hub comments. No live account is read,
connected, or changed. The fixture clock is September 3, 2026, at 10:24 local time.

Raw screenshots and animation frames stay in ignored `.codex-tmp/readme/`.
Framing and crops live in `website/render-readme.mjs`; screenshots are captured at
double resolution and framed at 1200 pixels wide. The capture widens the Timeline
rail, narrows the Review column, and expands its reply editor for readability.
Product source files and the deployed demo are unchanged.

The first image replaces timestamps with readable source labels for this image only;
SQL report labels reflect the sample reports' SQL Server source configurations.
The LEARNED.md image uses authored example lessons in the real document editor.
To recapture and frame just those two images, add `--memory-update` to both commands.

Review every final image at README width after regenerating: titles, amounts,
source context, action buttons, and the ends of cards must remain visible.

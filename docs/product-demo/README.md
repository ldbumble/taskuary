# General assistant product demo

## A team finds a time (availability view)

`taskuary-availability.webm` (about 36 seconds, no sound; `taskuary-availability.png` is a still of it) shows one
thread where a team looks for an hour next week, and nothing else on the screen: the film is the task's own panel.
The first mail is there; nobody types. The task's agent starts on it by itself, as it does on any arrival, and
draws one view of who can make which times - each person's ranges on a time axis, how many are free in each
stretch, the best slot banded with its count. Each reply lands, and the same view is drawn again under it, moving
from what it was: a new bar grows in, the band travels to the new best slot, the count goes on. No older copy
stays above. It ends on the invite for the best slot, as a card waiting for a press. Nothing is sent.

It is recorded from the demo world, never a live mailbox: `website/record-availability.mjs` starts
`taskuary --demo` itself on a throwaway home and a free port with `TASKUARY_DEMO_SCENE=availability`, which adds
the thread's task and plays the scene once when that task is first opened (`taskuary/demo.py`, `SCENE`). The
people are the repository's invented ones at `northwind.example`. The replies and the agent's turns go through the
roads real ones take, and the view is the spec a real agent hands `show` (`availability`, the same `id` each
time): the counts and the best slot are worked out by the page, not written in the script.

```powershell
# from website/: build the app the demo serves
npm exec --yes --package=node@22 -- node node_modules/vite/bin/vite.js build
# from the repository root; Playwright is not a dependency here, so name its package folder
$env:TASKUARY_PLAYWRIGHT = "<...>\node_modules\playwright"
npm exec --yes --package=node@22 -- node website/record-availability.mjs            # --dark for the dark theme, --out <folder>, --name <file name>
```

The page is drawn at the density that makes the task panel 1440 real pixels wide, and the panel alone is
photographed as it changes (about twenty times a second) - Playwright's own video keeps a page at one pixel a
point whatever its density, so its words came out small or stretched. The frames are put together by the ffmpeg in
Playwright's browsers folder. The recorder fails on a page error or on any request that leaves this computer, and
saves a still of the panel at each beat beside the film.

## Dashboard and Advisor showcase

`website/record-showcase.mjs` records a separate, short tour of the current static
demo: dashboard metrics, channel/range filters, chart-to-table switching, an
Advisor follow-up and its original email, task context, and a prepared reply.
It uses the real interface with fictional data and synthetic narration. It never
presses Send. The final file is `taskuary-showcase.mp4` in `TASKUARY_OUTPUTS`, with
H.264 video, AAC narration, embedded English subtitles and chapter markers.
The original request-to-reply recording below is preserved.

From the repository root (Node 22.12+, the existing frontend dependencies, a
Chromium browser, Windows System.Speech and `imageio_ffmpeg` are required):

```powershell
# Set TASKUARY_OUTPUTS if the task runner has not already supplied it.
npm exec --yes --package=node@22 -- node website/record-showcase.mjs --prepare
powershell -NoProfile -File website/product-demo-voice.ps1 -Scenes .codex-tmp/tq1299/scenes.json -OutputDirectory .codex-tmp/tq1299/audio
Push-Location website
npm exec --yes --package=node@22 -- node node_modules/vite/bin/vite.js build --mode demo --outDir ../.codex-tmp/tq1299/build --base=./
Pop-Location
npm exec --yes --package=node@22 -- node website/record-showcase.mjs --check
npm exec --yes --package=node@22 -- node website/record-showcase.mjs
```

The check follows the actual clicks and verifies the dashboard, Advisor evidence,
task and nonempty reply. Both modes fail on browser exceptions or attempted live
API/external requests. Intermediate media, screenshots, the narration script and
recording provenance stay under ignored `.codex-tmp/tq1299/`. The build is isolated
there too; recording does not alter `site/demo` or publish anything. Subtitles
use approximate sentence timings; the onscreen captions also summarize each step.

## Existing request-to-reply recording

Open `index.html` for the video, captions and chapter navigation, or play
`taskuary-workflow.mp4` directly. The recording shows the real, rebuilt static
application at 1920 × 1080, using invented Northwind data and a synthetic voice.
Use **Play with narration** to start with sound enabled.

The recording starts by clicking **Walk me through my tasks**, bringing Ruth's
request forward without a long opening hold.
The story is for someone new to Taskuary: Ruth asks for the latest vendor spend
numbers; Connections shows the inbox, business data and AI choices; **Send to
agent** opens the general assistant; the prepared reply waits on the task; the
owner approves it. There are no coding tasks in the walkthrough.

The optional static-demo URL is `/demo/?workflow=numbers`. Its authored example
starts the scripted preparation only when **Send to agent** is clicked. Reload
resets it. No AI, database, mailbox, send, or external setup operation runs.
The normal `/demo/` retains its original scenario.

The public website is not deployed by recording the video. The local `site/demo`
bundle is rebuilt from the checkout. `recording.json` records the build asset,
checkout commit, recording time, scenario clock and chapter timings. The scenario
clock uses the fixture's September 3 workday so the invented work retains its
relative ages. The video shows current interface code, not a live account.

## Re-record on Windows

Prerequisites: installed frontend dependencies, Node 22.12+, Chromium/Edge,
Windows System.Speech, and FFmpeg (either `FFMPEG_PATH` or Python's installed
`imageio_ffmpeg`). Override the browser with `TASKUARY_BROWSER_EXECUTABLE`.

From the repository root, generate the narration:

```powershell
powershell -NoProfile -File website/product-demo-voice.ps1 -Scenes docs/product-demo/scenes.json -OutputDirectory .codex-tmp/product-demo/audio
```

Build the demo **from `website/` and wait for completion**:

```powershell
npm exec --yes --package=node@22 -- node node_modules/vite/bin/vite.js build --mode demo --outDir ../site/demo --base=./
```

From the repository root, check the actual clicks, then record:

```powershell
npm exec --yes --package=node@22 -- node website/record-product-demo.mjs --check
npm exec --yes --package=node@22 -- node website/record-product-demo.mjs
python website/product-demo-player.py
```

The recorder starts and closes its own local static server and browser. It saves
intermediate screenshots, narration and scene clips in ignored `.codex-tmp/`.
The final MP4 uses H.264/AAC and supports normal browser playback. The WebVTT
captions have sentence-level approximate timings; the onscreen captions summarize
each step. `scenes.json` contains the editable narration and onscreen text.

Validation includes the focused demo tests, the actual request-to-review browser
flow, and media decoding/playback. The browser check fails if the general answer
does not appear or if the approved draft remains in the pending queue.

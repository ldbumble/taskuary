# Animated Taskuary workspace

A standalone, interactive 3D concept based on the adjacent generated hero image. The geometry, characters, lighting, and animation are built in Three.js; the image is not used as a backdrop. This is an illustrative mockup, not a connection to real agents or email.

The hero centers the interactive room in the space beside the incoming feed, with no visible headline or marketing copy column. On narrow screens the feed moves below the room. A page heading and activity announcements remain available to screen readers. The walking animation resets all orientation axes after leaving a chair so the agent faces forward on both outbound and inbound trips.

The incoming feed and room share the same story state: Milo's task goes from collection to pickup to work at a desk, and Nora's email goes from drafting to waiting for approval to approved. A small task slip flies from the feed toward the doorway at pickup (disabled with reduced motion). Hovering a task highlights its agent; clicking it opens the corresponding work detail or draft. A separate FYI card illustrates a message already handled by a teammate. Messages are examples and task subjects rotate across arrivals.

On Windows, double-click **start-preview.cmd** and keep its window open while viewing the mockup. If the server is already running on port 8766, use the existing preview link.

Alternatively, from the repository root, run:

```powershell
python -m http.server 8766 --bind 127.0.0.1
```

Open http://127.0.0.1:8766/docs/mockups/animated-workspace/ in a browser with WebGL support. Serve the repository root so the app and icon links also resolve. Opening index.html directly with file:// cannot load browser modules reliably.

- Work arrives automatically. Milo walks in, takes a seat, and later heads back out for the next task.
- On opening, the floor, walls, furniture, and agents assemble in a staggered sequence.
- Milo's desk arrives in separate pieces on a growing floor extension. When he leaves to collect more work, it packs away, then flies back in for the new task.
- Click the **floor** to lift the room apart, briefly make it disappear, and rebuild it. The work pauses during this sequence and resumes afterward. Escape skips straight to the assembled room.
- Click the **door itself** to bring the next arrival forward. Milo walks out to collect it, then returns.
- Click **agents or their desks** to peek at the work. Hovering highlights them and reveals a small hint.
- Click **Nora or her desk** when her hand is raised to review her draft. Approve it in the dialog to let her resume. Nothing is sent.
- Click the **arched window** to switch between daylight and evening lighting.
- Click the **plants** to nudge their leaves.
- Click the **wall clock** to pause or resume time.
- Drag to rotate; scroll or pinch to lean in; press Home while an object has keyboard focus to reset the camera.
- Keyboard: Tab focuses objects in the room, Enter activates them, Home restores the camera, and Escape dismisses a detail or draft.
- A system preference for reduced motion starts with a composed, paused scene. Object interactions and approval still work.

The opening construction takes about 4 seconds, followed by a roughly 12-second walk into the expanded room. Milo works for 18 seconds before collecting the next task. A full disappearance/rebuild takes about 6 seconds, and a new desk takes 2.5 seconds to assemble. Nora remains waiting until approved, regardless of other activity. The main scene has no task buttons or control toolbar; the visible 3D objects are the controls. Focusable, visually unobtrusive counterparts provide keyboard access. Reduced motion starts with a complete room and skips construction effects.

No build or internet access is required. Three.js 0.180.0 and its two addons are pinned and vendored with the MIT license in vendor/. The production site is unchanged.

Implementation references: [Three.js installation](https://threejs.org/manual/en/installation.html), [OrbitControls](https://threejs.org/docs/pages/OrbitControls.html), [Raycaster](https://threejs.org/docs/pages/Raycaster.html).

Browser verification, from website/ with its existing dependencies installed:

```powershell
node check-workspace-mockup.mjs
```

The check clicks actual rendered surfaces to verify agents, the door, plants, the window, the clock and floor. It checks opening assembly, desk packing/expansion, disappearance/rebuild, repeated rebuild and Escape, exact restoration of room transforms, and forward walking on the initial arrival, departure and return. It also covers draft approval, feed synchronization, hover/details, separating a drag from a click, camera rotation/zoom, keyboard access, mobile touch, reduced motion, and browser errors. It writes desktop, mobile, assembly and disassembly preview images here.

# Sketch Studio Test Status

Last audited: 2026-10-13

## Gate 0 — Audit

| Check | Result | Evidence |
|---|---|---|
| Application starts | PASS | `main.py` remained in the Kivy event loop for 8 seconds with no exception. |
| Python modules compile | PASS | `main.py`, `project_model.py`, `video_studio.py`, and `sketchApi.py` compile successfully. |
| Existing unit tests | PASS | `python -m unittest discover -s tests -v`: 4/4 passed. |
| Multiple images/scenes | PARTIAL | Scene add/upload paths exist; no automated or complete interactive workflow test. |
| Deterministic cached sketch renderer | FAIL | No pure `render_frame(project, time)` and no cached stroke model. |
| Magnetic scene timeline and resize | PARTIAL | Scene starts are derived and right-edge resize exists; minimum is 0.1s, with no snapping or left-edge behavior. |
| Independent global audio | PARTIAL | Multiple tracks, overlapping mix, mute, volume, trims, and waveform data exist; cross-track drag and overlap rules do not. |
| Synchronized preview/scrubbing | FAIL | Visuals use a Kivy interval clock while audio plays independently from a generated WAV. |
| Scene/audio editing | PARTIAL | Duplicate/delete/reorder buttons and audio split/move/trim exist; scene split, drag reorder, and command history do not. |
| Transitions | PARTIAL | Fade exists; slide and wipe are absent. |
| Save/load/autosave/undo | PARTIAL | JSON save/load exists; media is referenced rather than bundled, and autosave/undo/redo are absent. |
| MP4 export parity | FAIL | An export path exists but preview/export share no frame renderer; no verified MP4 or ffprobe evidence is present. |

Notes:

- `pytest` is not installed in the project virtual environment; the current tests use `unittest`.
- `ffprobe` is not installed or available on `PATH`, so MP4 stream and duration verification cannot currently pass.
- The repository already contained uncommitted source changes before this audit. No source code was modified during Gate 0.

## Browser P0 — Scaffold and timeline engine

| Check | Result | Evidence |
|---|---|---|
| Timeline/model unit tests | PASS | `npm test`: 10/10 Vitest tests passed. |
| Strict TypeScript production build | PASS | `npm run build`: Vite production bundle completed. |
| Real browser startup | PASS | `npm run test:e2e`: Microsoft Edge loaded the harness with no page or console errors. |
| Dependency security audit | PASS | `npm audit`: 0 vulnerabilities. |

P0 covers derived scene starts, duration ripple, minimum scene duration, continuous scene splitting, audio trimming, overlap detection/pushing, cross-track movement, project duration, shared time/pixel conversion, and command-level undo/redo.

## Browser P1 — Sketch engine and pure renderer

| Check | Result | Evidence |
|---|---|---|
| Deterministic frame state | PASS | Vitest verifies equal project/time inputs produce equal frame state. |
| Worker sketch processing | PASS | Edge uploads and traces a generated PNG through the real Web Worker. |
| Progressive scrubbing | PASS | Playwright verifies start and midpoint differ. |
| Identical-time pixels | PASS | Scrubbing away and back produces an identical canvas data URL. |
| Regression/build | PASS | 12/12 Vitest tests, 2/2 Playwright tests, strict production build. |

## Browser P2 — Global audio engine

| Check | Result | Evidence |
|---|---|---|
| Decode and buffer cache | PASS | Two generated WAV files decode and register once in Edge. |
| Multiresolution waveforms | PASS | Worker creates 256/1024/4096-sample levels; known-click bucket test passes. |
| Overlapping playback | PASS | Playwright observes two simultaneously scheduled AudioBufferSourceNodes. |
| Live controls and seek | PASS | Track mute, track volume, seek/reschedule, and pause pass in Edge. |
| Regression/build | PASS | 13/13 Vitest tests, 3/3 Playwright tests, strict production build. |

## Browser P3 — Full timeline interactions

| Check | Result | Evidence |
|---|---|---|
| Shared scale/ruler/playhead/zoom | PASS | One time origin drives every lane; Edge zoom test verifies proportional scene widths. |
| Scene editing | PASS | Edge verifies resize, split, duplicate, reorder, delete, and undo/redo. |
| Audio editing | PASS | Edge verifies trim, cross-track move, split, and delete. |
| Shared horizontal layout | PASS | Sticky headers no longer cover time-zero clips; scenes/audio/playhead share the offset. |
| Regression/build | PASS | 13/13 Vitest tests, 5/5 Playwright tests, strict production build. |

## Browser P4 — Transitions

| Check | Result | Evidence |
|---|---|---|
| Fade/slide/wipe timing | PASS | Vitest verifies transition activation and midpoint progress. |
| Boundary controls | PASS | Edge cycles none/fade/slide/wipe without blocking resize handles. |
| Renderer integration | PASS | Transition composition runs inside the same `renderFrame` used by preview. |
| Regression/build | PASS | 14/14 Vitest tests, 6/6 Playwright tests, strict production build. |

## Browser P5 — Persistence

| Check | Result | Evidence |
|---|---|---|
| IndexedDB autosave | PASS | Edge displays Saving/Saved and persists the project plus original blobs. |
| Reload restore | PASS | A real page reload restores scene, media, sketch data, and render registry. |
| `.sketchproj` download/open | PASS | Playwright downloads the ZIP, deletes the scene, imports it, and recovers the scene and asset. |
| Missing/corrupt handling | PASS | Import validates project.json, document shape, every referenced asset, and sketch data. |
| Regression/build | PASS | 14/14 Vitest tests, 7/7 Playwright tests, strict production build. |

## Browser P6 — MP4 export

| Check | Result | Evidence |
|---|---|---|
| WebCodecs feature/config detection | PASS | Edge confirms H.264 and AAC encoder configurations before export. |
| Real MP4 generation | PASS | Playwright downloads the browser-generated MP4. |
| Stream verification | PASS | ffprobe reports H.264 video and AAC audio. |
| Duration and playback | PASS | ffprobe reports 4.00s; Edge loads and plays the downloaded file. |
| Regression/build | PASS | 14/14 Vitest tests, 8/8 Playwright tests, strict build, 0 audit vulnerabilities. |

`mp4-muxer` emits a deprecation notice in favor of Mediabunny, but remains here because the fixed product specification explicitly requires `mp4-muxer`.

## Browser P7 — Polish and stress

| Check | Result | Evidence |
|---|---|---|
| Large project timeline | PASS | Edge renders and manipulates 60 scenes, four tracks, and 10-minute extents. |
| Timing/waveform stress | PASS | 1,000 timeline calculations plus multiresolution peaks complete below the 1s budget. |
| Transport and accessibility | PASS | Skip, timecode, loop, master mute, editable name, labels, and selected-clip controls are present. |
| Responsive guard | PASS | Windows below 1280px show a larger-screen notice. |
| Final regression | PASS | 15/15 Vitest tests, 9/9 Playwright tests, strict build, 0 audit vulnerabilities. |

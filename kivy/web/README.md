# Sketch Video Studio

## Run

```powershell
npm install
npm run dev
```

Uploads are deliberately non-destructive: importing an image or audio file adds
it to the **Uploads** library but does not change the video. Drag an image onto
the Video lane to create a scene. Drag audio onto the empty audio drop lane (or
an existing audio lane) to position it at that timeline time. The small Add
buttons provide a keyboard-accessible alternative to dragging.

Each scene has two independent timing values in **Design**. Scene duration is
how long the page remains on screen; sketch completion is how quickly its hand
drawing finishes. For example, a 5,000 ms scene with a 1,000 ms sketch duration
draws for one second and holds the completed sketch for the remaining four.
The cyan line inside each scene block visualizes the drawing portion.
Each scene also has its own **Sketch animation** switch. Turning it off shows the
complete image immediately for the whole scene and hides the sketch-duration
handle; audio, transitions, and scene timing are unaffected.

For staged drawing, choose **Select sketch sections** on a scene. Add regions in
playback order, paint each region directly over the image, and assign each one a
millisecond duration. The renderer sketches only the painted areas, one region
after another; image areas that were never painted remain unsketched. Region
masks are saved as editable vector brush strokes rather than flattening the
source image.

The transport bar also has a project-wide **Auto / Slow / Fast** speed control.
Auto is the media's natural 1× rate. Manual speed ranges from 0.25× to 3× and
keeps canvas animation, timeline audio, seeking, looping, saved projects, and
MP4 export synchronized. A 4-second project exported at 2× produces a 2-second
video; at 0.5× it produces an 8-second video.

Open an uploaded image to build a composite. **Image layer** can add any number
of PNG, JPEG, WebP, or SVG overlays. Every overlay remains independently
selectable, movable, resizable, rotatable, reorderable, erasable, and eligible
for background removal. **Use in video** replaces that upload while preserving
all scene references to it.

## AI background removal

The image editor uses a private local `rembg`/U²-Net service for real subject
segmentation. Install it once, then run it in a second terminal:

```powershell
npm run background:setup
npm run background:start
```

The first removal downloads the selected model and is slower. Later removals use
the local model cache. Images stay on the computer. If the service is not
running, the editor falls back to edge-connected color removal, which is useful
for whiteboard art and solid backgrounds but is not an AI segmentation model.

The same service powers the painted Magic Eraser. Paint over an unwanted object,
adjust the brush size, then choose **Remove painted**. The local inpainting route
reconstructs the selected region from surrounding pixels. Without the service,
the editor falls back to transparent removal and tells the user that it did so.

## Open content providers

- Iconify supplies searchable SVG graphics. Icon collections have their own
  licenses.
- Openverse supplies Creative Commons and public-domain images. The editor asks
  for results that permit commercial use and modification, but publishers must
  still verify and follow the displayed source license.
- Wikimedia Commons is the no-key fallback for image and audio search and the
  primary catalog behind the Sketches tab. It is a very large community catalog,
  not a promise that every possible search has a result. Each file keeps its
  source, creator, and license metadata in the search result.

Neither catalog requires a Sketch Studio account, API token, or generated key.
If one provider is unavailable, results from the other remain usable. Remote
audio is first copied to Uploads; it is never inserted into the timeline until
the user places it.

Imported media is flattened into the design before the existing sketch tracer
creates a video scene. The sketch-video project model and export pipeline remain
the source of truth.

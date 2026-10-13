# Sketch Video Studio

## Run

```powershell
npm install
npm run dev
```

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

## Open content providers

- Iconify supplies searchable SVG graphics. Icon collections have their own
  licenses.
- Openverse supplies Creative Commons and public-domain images. The editor asks
  for results that permit commercial use and modification, but publishers must
  still verify and follow the displayed source license.

Imported media is flattened into the design before the existing sketch tracer
creates a video scene. The sketch-video project model and export pipeline remain
the source of truth.

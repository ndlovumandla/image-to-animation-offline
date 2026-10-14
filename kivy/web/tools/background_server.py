"""Local, private background-removal API for Sketch Video Studio."""
from io import BytesIO

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from PIL import Image
from rembg import new_session, remove
import uvicorn
import cv2
import numpy as np

MAX_BYTES = 20 * 1024 * 1024
app = FastAPI(title="Sketch Studio Background Removal", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)
session = None


@app.get("/health")
def health():
    return {"ready": True, "model": "u2net"}


@app.post("/api/remove")
async def remove_background(file: UploadFile = File(...)):
    global session
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "Image is larger than 20 MB")
    try:
        Image.open(BytesIO(content)).verify()
        if session is None:
            session = new_session("u2net")
        result = remove(
            content,
            session=session,
            alpha_matting=True,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=10,
            post_process_mask=True,
        )
        return Response(result, media_type="image/png")
    except Exception as exc:
        raise HTTPException(422, f"Background removal failed: {exc}") from exc


@app.post("/api/inpaint")
async def inpaint_masked_area(image: UploadFile = File(...), mask: UploadFile = File(...)):
    """Fill the user-painted region without sending either image to the cloud."""
    image_bytes = await image.read(MAX_BYTES + 1)
    mask_bytes = await mask.read(MAX_BYTES + 1)
    if len(image_bytes) > MAX_BYTES or len(mask_bytes) > MAX_BYTES:
        raise HTTPException(413, "Image or mask is larger than 20 MB")
    try:
        source = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
        painted = cv2.imdecode(np.frombuffer(mask_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
        if source is None or painted is None:
            raise ValueError("Image or mask could not be decoded")
        if source.shape[:2] != painted.shape[:2]:
            raise ValueError("Image and mask dimensions must match")
        painted = cv2.threshold(painted, 10, 255, cv2.THRESH_BINARY)[1]
        painted = cv2.dilate(painted, np.ones((5, 5), np.uint8), iterations=1)
        alpha = source[:, :, 3] if source.ndim == 3 and source.shape[2] == 4 else None
        color = source[:, :, :3] if source.ndim == 3 else cv2.cvtColor(source, cv2.COLOR_GRAY2BGR)
        result = cv2.inpaint(color, painted, 5, cv2.INPAINT_TELEA)
        if alpha is not None:
            result = np.dstack((result, alpha))
        ok, encoded = cv2.imencode(".png", result)
        if not ok:
            raise ValueError("Result could not be encoded")
        return Response(encoded.tobytes(), media_type="image/png")
    except Exception as exc:
        raise HTTPException(422, f"Inpainting failed: {exc}") from exc


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=7000)

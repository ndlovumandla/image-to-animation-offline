"""Local, private background-removal API for Sketch Video Studio."""
from io import BytesIO
import os
import threading

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from PIL import Image
import uvicorn
import cv2
import numpy as np

MAX_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
    ).split(",")
    if origin.strip()
]

app = FastAPI(title="Sketch Studio Background Removal", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)
session = None
session_lock = threading.Lock()


def _get_session():
    global session
    if session is None:
        with session_lock:
            if session is None:
                from rembg import new_session
                session = new_session("u2net")
    return session


def _run_remove(content: bytes) -> bytes:
    from rembg import remove
    Image.open(BytesIO(content)).verify()
    active_session = _get_session()
    return remove(
        content,
        session=active_session,
        alpha_matting=True,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10,
        alpha_matting_erode_size=10,
        post_process_mask=True,
    )


def _run_inpaint(image_bytes: bytes, mask_bytes: bytes) -> bytes:
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
    return encoded.tobytes()


@app.get("/health")
def health():
    return {"ready": True, "model": "u2net", "session_loaded": session is not None}


@app.post("/api/remove")
async def remove_background(file: UploadFile = File(...)):
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "Image is larger than 20 MB")
    try:
        result = await run_in_threadpool(_run_remove, content)
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
        result = await run_in_threadpool(_run_inpaint, image_bytes, mask_bytes)
        return Response(result, media_type="image/png")
    except Exception as exc:
        raise HTTPException(422, f"Inpainting failed: {exc}") from exc


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "7000"))
    uvicorn.run(app, host=host, port=port)

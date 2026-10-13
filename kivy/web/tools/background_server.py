"""Local, private background-removal API for Sketch Video Studio."""
from io import BytesIO

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from PIL import Image
from rembg import new_session, remove
import uvicorn

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


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=7000)

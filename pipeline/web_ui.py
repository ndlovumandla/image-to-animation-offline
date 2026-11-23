"""Web Studio UI & API for the Narrated Illustrated / Whiteboard Explainer Video Pipeline.

Run on the Ubuntu GPU server (port 8090):
    uvicorn pipeline.web_ui:app --host 0.0.0.0 --port 8090
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from .characters import BANNER_PALETTES, CHARACTER_PRESETS, ENVIRONMENTS, filter_characters
from .config import PipelineConfig
from .stage1_tts import generate_voiceover
from .stage2_whisper import align_audio
from .stage3_director import direct_storyboard
from .stage4_comfyui import generate_scenes, reroll_single_scene
from .stage5_animate import animate_all_scenes
from .stage6_assemble import assemble_video

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline.web_ui")

BASE_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = Path(os.getenv("SKETCH_RUNS_DIR", str(BASE_DIR / "runs"))).resolve()
RUNS_DIR.mkdir(parents=True, exist_ok=True)
GPU_HOST = os.getenv("SKETCH_GPU_HOST", "127.0.0.1")

app = FastAPI(title="AI Explainer & Whiteboard Sketch Studio", version="2.0.0")

_JOBS_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


class CreateJobRequest(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=80)
    script: str = Field(..., min_length=10)
    # Chatterbox TTS settings
    voice: str = "Fiona.wav"
    voice_mode: str = "predefined"
    tts_temperature: float = 0.75
    tts_exaggeration: float = 0.50
    tts_cfg_weight: float = 0.50
    tts_speed_factor: float = 1.00
    tts_paragraph_pause_sec: float = 0.28
    # Character, Environment & Banner Palette
    character_description: str = ""
    cast_characters: list[str] = Field(default_factory=list)
    banner_palette: str = "navy_teal"
    environment_mode: str = "auto"
    # Pipeline options
    ollama_model: str = "gemma3:12b"
    whisper_model: str = "medium"
    image_width: int = 1664
    image_height: int = 928
    use_lightning: bool = True
    enable_vision_qa: bool = True
    review_before_animate: bool = True
    burn_captions: bool = True
    draw_hand: bool = True
    animate_workers: int = 4


class PreviewVoiceRequest(BaseModel):
    voice: str = "Fiona.wav"
    voice_mode: str = "predefined"
    text: str = "Hello! Welcome to your narrated explainer video. Let's walk through today's key ideas together."
    tts_temperature: float = 0.75
    tts_exaggeration: float = 0.50
    tts_cfg_weight: float = 0.50
    tts_speed_factor: float = 1.00


class RerollRequest(BaseModel):
    prompt: str | None = None


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip()).strip("_").lower()
    return slug or f"video_{int(time.time())}"


def _job_state_path(job_id: str) -> Path:
    return RUNS_DIR / job_id / "job_state.json"


def _save_job(job_id: str) -> None:
    with _JOBS_LOCK:
        data = _JOBS.get(job_id)
        if not data:
            return
        p = _job_state_path(job_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _update_job(job_id: str, **kwargs: Any) -> None:
    with _JOBS_LOCK:
        job = _JOBS.setdefault(job_id, {"job_id": job_id, "logs": []})
        job.update(kwargs)
        job["updated_at"] = time.time()
    _save_job(job_id)


def _append_log(job_id: str, msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    logger.info("[%s] %s", job_id, msg)
    with _JOBS_LOCK:
        job = _JOBS.setdefault(job_id, {"job_id": job_id, "logs": []})
        logs = job.setdefault("logs", [])
        logs.append(line)
        if len(logs) > 250:
            del logs[:-250]
    _save_job(job_id)


def _build_cfg(params: dict[str, Any]) -> PipelineConfig:
    return PipelineConfig(
        gpu_host=GPU_HOST,
        voice_id=params.get("voice", "Fiona.wav"),
        voice_mode=params.get("voice_mode", "predefined"),
        tts_temperature=float(params.get("tts_temperature", 0.75)),
        tts_exaggeration=float(params.get("tts_exaggeration", 0.50)),
        tts_cfg_weight=float(params.get("tts_cfg_weight", 0.50)),
        tts_speed_factor=float(params.get("tts_speed_factor", 1.00)),
        tts_paragraph_pause_sec=float(params.get("tts_paragraph_pause_sec", 0.28)),
        character_description=str(params.get("character_description", "")),
        cast_characters=list(params.get("cast_characters") or []),
        banner_palette=str(params.get("banner_palette", "navy_teal")),
        environment_mode=str(params.get("environment_mode", "auto")),
        ollama_model=str(params.get("ollama_model", "gemma3:12b")),
        whisper_model=params.get("whisper_model", "medium"),
        image_width=int(params.get("image_width", 1664)),
        image_height=int(params.get("image_height", 928)),
        use_lightning=bool(params.get("use_lightning", True)),
        enable_vision_qa=bool(params.get("enable_vision_qa", True)),
        review_scenes=False,
        burn_captions=bool(params.get("burn_captions", True)),
        draw_hand=bool(params.get("draw_hand", True)),
        animate_workers=int(params.get("animate_workers", 4)),
    )


def _run_stages_1_to_4(job_id: str) -> None:
    out_dir = RUNS_DIR / job_id
    with _JOBS_LOCK:
        params = dict(_JOBS[job_id]["params"])
    cfg = _build_cfg(params)

    try:
        # Stage 1: Chatterbox TTS
        _update_job(job_id, status="running", stage=1, stage_label="Stage 1/6: Generating Voiceover (Chatterbox TTS)", progress=5)
        _append_log(job_id, f"Stage 1: Voice='{cfg.voice_id}' (temp={cfg.tts_temperature}, exag={cfg.tts_exaggeration}, cfg={cfg.tts_cfg_weight}, speed={cfg.tts_speed_factor})")
        script_text = (out_dir / "script.txt").read_text(encoding="utf-8")
        wav_path = generate_voiceover(
            script_text,
            out_dir,
            cfg,
            progress_cb=lambda cur, tot, msg: (
                _update_job(job_id, progress=5 + int(15 * cur / max(1, tot)), stage_detail=msg),
                _append_log(job_id, msg),
            ),
        )

        # Stage 2: Whisper Alignment
        _update_job(job_id, stage=2, stage_label="Stage 2/6: Word-Level Audio Alignment (Whisper)", progress=22, stage_detail="Transcribing audio...")
        _append_log(job_id, f"Stage 2: Aligning {wav_path.name} with Whisper ({cfg.whisper_model})...")
        alignment = align_audio(wav_path, out_dir, cfg)
        _append_log(job_id, f"Aligned {len(alignment['sentences'])} sentences ({alignment['total_duration']:.1f}s).")

        # Stage 3: Ollama Visual Director
        _update_job(job_id, stage=3, stage_label="Stage 3/6: Visual Director (Ollama qwen2.5:7b)", progress=32, stage_detail=f"Env={cfg.environment_mode}, Palette={cfg.banner_palette}")
        _append_log(job_id, f"Stage 3: Directing rich beats (env={cfg.environment_mode}, palette={cfg.banner_palette})...")
        storyboard = direct_storyboard(
            alignment,
            out_dir,
            cfg,
            progress_cb=lambda cur, tot, msg: (
                _update_job(job_id, progress=32 + int(13 * cur / max(1, tot)), stage_detail=msg),
                _append_log(job_id, msg),
            ),
        )
        _append_log(job_id, f"Created {storyboard['beat_count']} rich visual beats.")

        # Stage 4: ComfyUI Qwen-Image
        mode_str = "8-step Lightning" if cfg.use_lightning else "20-step Standard"
        _update_job(job_id, stage=4, stage_label=f"Stage 4/6: Generating Scenes (Qwen-Image {mode_str})", progress=46, stage_detail="Starting ComfyUI...")
        _append_log(job_id, f"Stage 4: Generating {storyboard['beat_count']} scenes via ComfyUI ({mode_str})...")
        generate_scenes(
            storyboard,
            out_dir,
            cfg,
            progress_cb=lambda cur, tot, msg: (
                _update_job(job_id, progress=46 + int(28 * cur / max(1, tot)), stage_detail=msg),
                _append_log(job_id, msg),
            ),
        )

        if params.get("review_before_animate", True):
            _update_job(
                job_id,
                status="review",
                stage=4,
                stage_label="Review Scenes — Re-roll any scene or click Approve & Animate",
                stage_detail="Waiting for your approval",
                progress=75,
            )
            _append_log(job_id, "Paused for scene review. Inspect scenes and click 'Approve & Animate' when ready.")
            return

        _run_stages_5_to_6(job_id, force_reanimate=False)
    except Exception as exc:
        logger.exception("Pipeline error for %s", job_id)
        _append_log(job_id, f"ERROR: {exc}")
        _update_job(job_id, status="error", error=str(exc))


def _run_stages_5_to_6(job_id: str, force_reanimate: bool = False) -> None:
    out_dir = RUNS_DIR / job_id
    with _JOBS_LOCK:
        params = dict(_JOBS[job_id]["params"])
    cfg = _build_cfg(params)
    if force_reanimate:
        cfg.skip_existing = False

    try:
        storyboard = json.loads((out_dir / "storyboard.json").read_text(encoding="utf-8"))
        wav_path = out_dir / "full_narration.wav"
        srt_path = out_dir / "captions.srt"

        _update_job(job_id, status="running", stage=5, stage_label="Stage 5/6: Element-Complete Sequential Sketch Animation", progress=76, stage_detail="Drawing one object at a time...")
        _append_log(job_id, f"Stage 5: Rendering {storyboard['beat_count']} element-complete clips ({cfg.animate_workers} workers)...")
        clip_paths = animate_all_scenes(
            storyboard,
            out_dir,
            cfg,
            progress_cb=lambda cur, tot, msg: (
                _update_job(job_id, progress=76 + int(18 * cur / max(1, tot)), stage_detail=msg),
                _append_log(job_id, msg),
            ),
        )

        _update_job(job_id, stage=6, stage_label="Stage 6/6: Final FFmpeg Assembly (Captions Below Video)", progress=95, stage_detail="Encoding final 1080p MP4...")
        _append_log(job_id, "Stage 6: Assembling final MP4 with FFmpeg...")
        final_mp4 = assemble_video(
            clip_paths=clip_paths,
            narration_wav=wav_path,
            srt_path=srt_path if srt_path.exists() else None,
            output_dir=out_dir,
            config=cfg,
        )
        size_mb = final_mp4.stat().st_size / (1024 * 1024)
        _append_log(job_id, f"DONE! Final video ready: {final_mp4.name} ({size_mb:.2f} MB)")
        _update_job(
            job_id,
            status="done",
            stage=6,
            stage_label="Complete — Video Ready!",
            stage_detail=f"{size_mb:.2f} MB MP4",
            progress=100,
        )
    except Exception as exc:
        logger.exception("Stages 5-6 error for %s", job_id)
        _append_log(job_id, f"ERROR: {exc}")
        _update_job(job_id, status="error", error=str(exc))


def _load_existing_runs() -> None:
    for d in sorted(RUNS_DIR.iterdir()):
        if not d.is_dir():
            continue
        jid = d.name
        st_path = d / "job_state.json"
        if st_path.exists():
            try:
                _JOBS[jid] = json.loads(st_path.read_text(encoding="utf-8"))
                continue
            except Exception:
                pass
        if (d / "storyboard.json").exists():
            done = (d / "final_video.mp4").exists()
            _JOBS[jid] = {
                "job_id": jid,
                "project_name": jid,
                "status": "done" if done else "review",
                "stage": 6 if done else 4,
                "stage_label": "Complete — Video Ready!" if done else "Ready to Animate",
                "stage_detail": "",
                "progress": 100 if done else 75,
                "params": {
                    "voice": "Fiona.wav",
                    "whisper_model": "medium",
                    "use_lightning": True,
                    "review_before_animate": True,
                    "burn_captions": True,
                    "draw_hand": True,
                    "animate_workers": 4,
                },
                "logs": ["Loaded existing run from disk."],
                "updated_at": d.stat().st_mtime,
            }


_load_existing_runs()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (Path(__file__).parent / "ui" / "index.html").read_text(encoding="utf-8")


@app.get("/api/presets")
def get_presets(race: str = "", gender: str = "", age_group: str = "", role: str = "", search: str = "") -> dict[str, Any]:
    """Return filtered character presets + all facet options + banner palettes + environments."""
    return {
        "characters": filter_characters(race=race, gender=gender, age_group=age_group, role=role, search=search),
        "facets": {
            "races": sorted({c["race"] for c in CHARACTER_PRESETS}),
            "genders": sorted({c["gender"] for c in CHARACTER_PRESETS}),
            "age_groups": sorted({c["age_group"] for c in CHARACTER_PRESETS}),
            "roles": sorted({c["role"] for c in CHARACTER_PRESETS}),
        },
        "banner_palettes": BANNER_PALETTES,
        "environments": ENVIRONMENTS,
    }


@app.get("/api/system")
def system_status() -> dict[str, Any]:
    vram = {"used_mb": 0, "total_mb": 16311, "free_mb": 16311, "gpu_name": "RTX 5060 Ti"}
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,memory.free", "--format=csv,noheader,nounits"],
            text=True,
            timeout=5,
        ).strip()
        parts = [x.strip() for x in out.split(",")]
        if len(parts) >= 4:
            vram = {
                "gpu_name": parts[0],
                "used_mb": int(parts[1]),
                "total_mb": int(parts[2]),
                "free_mb": int(parts[3]),
            }
    except Exception:
        pass

    voices = ["Fiona.wav", "Emily.wav", "Adrian.wav", "Abigail.wav", "Elena.wav"]
    ref_voices: list[str] = []
    try:
        r = requests.get(f"http://{GPU_HOST}:8004/get_predefined_voices", timeout=4)
        if r.ok:
            data = r.json()
            if isinstance(data, list) and data:
                voices = [v["filename"] if isinstance(v, dict) else str(v) for v in data]
    except Exception:
        pass
    try:
        r2 = requests.get(f"http://{GPU_HOST}:8004/get_reference_files", timeout=4)
        if r2.ok and isinstance(r2.json(), list):
            ref_voices = [str(x) for x in r2.json()]
    except Exception:
        pass

    return {"vram": vram, "voices": voices, "reference_voices": ref_voices}


@app.post("/api/preview-voice")
def preview_voice(req: PreviewVoiceRequest) -> Response:
    """Synthesize a quick 3-second Chatterbox voice sample (auto-reloads model if unloaded)."""
    base_url = f"http://{GPU_HOST}:8004"
    h = requests.get(f"{base_url}/health", timeout=10).json()
    if not h.get("ready"):
        requests.post(f"{base_url}/restart_server", timeout=180).raise_for_status()

    payload: dict[str, Any] = {
        "text": req.text[:280],
        "voice_mode": req.voice_mode,
        "output_format": "wav",
        "split_text": False,
        "temperature": req.tts_temperature,
        "exaggeration": req.tts_exaggeration,
        "cfg_weight": req.tts_cfg_weight,
        "speed_factor": req.tts_speed_factor,
    }
    if req.voice_mode == "clone":
        payload["reference_audio_filename"] = req.voice
    else:
        payload["predefined_voice_id"] = req.voice

    r = requests.post(f"{base_url}/tts", json=payload, timeout=120)
    r.raise_for_status()
    return Response(content=r.content, media_type="audio/wav")


@app.get("/api/jobs")
def list_jobs() -> list[dict[str, Any]]:
    with _JOBS_LOCK:
        items = list(_JOBS.values())
    items.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
    return items


@app.post("/api/jobs")
def create_job(req: CreateJobRequest) -> dict[str, Any]:
    job_id = f"{_slugify(req.project_name)}_{time.strftime('%H%M%S')}"
    out_dir = RUNS_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "script.txt").write_text(req.script.strip(), encoding="utf-8")

    job = {
        "job_id": job_id,
        "project_name": req.project_name.strip(),
        "status": "queued",
        "stage": 0,
        "stage_label": "Queued...",
        "stage_detail": "",
        "progress": 0,
        "params": req.model_dump(exclude={"script", "project_name"}),
        "logs": [],
        "updated_at": time.time(),
    }
    with _JOBS_LOCK:
        _JOBS[job_id] = job
    _save_job(job_id)

    threading.Thread(target=_run_stages_1_to_4, args=(job_id,), daemon=True).start()
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    out_dir = RUNS_DIR / job_id
    sb_path = out_dir / "storyboard.json"
    storyboard = json.loads(sb_path.read_text(encoding="utf-8")) if sb_path.exists() else None
    scenes_dir = out_dir / "scenes"
    ready_scenes: dict[str, int] = {}
    if scenes_dir.exists():
        for p in scenes_dir.glob("scene_*.png"):
            m = re.match(r"scene_(\d+)\.png$", p.name)
            if m and p.stat().st_size > 1000:
                ready_scenes[str(int(m.group(1)))] = int(p.stat().st_mtime)
    return {
        **job,
        "storyboard": storyboard,
        "ready_scenes": ready_scenes,
        "has_video": (out_dir / "final_video.mp4").exists(),
        "has_audio": (out_dir / "full_narration.wav").exists(),
    }


@app.post("/api/jobs/{job_id}/reroll/{beat_id}")
def reroll_scene_endpoint(job_id: str, beat_id: int, req: RerollRequest) -> dict[str, Any]:
    out_dir = RUNS_DIR / job_id
    sb_path = out_dir / "storyboard.json"
    if not sb_path.exists():
        raise HTTPException(404, "Storyboard not found")
    with _JOBS_LOCK:
        params = dict(_JOBS[job_id]["params"])
    cfg = _build_cfg(params)
    storyboard = json.loads(sb_path.read_text(encoding="utf-8"))

    _append_log(job_id, f"Re-rolling scene_{beat_id:02d}.png ...")
    reroll_single_scene(storyboard, beat_id, out_dir, cfg, new_prompt=req.prompt, unload_after=True)
    (out_dir / "clips" / f"clip_{beat_id:02d}.mp4").unlink(missing_ok=True)
    _append_log(job_id, f"Re-rolled scene_{beat_id:02d}.png successfully.")
    return {"status": "ok", "beat_id": beat_id, "ts": int(time.time())}


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str) -> dict[str, Any]:
    with _JOBS_LOCK:
        if job_id not in _JOBS:
            raise HTTPException(404, "Job not found")
        _JOBS[job_id]["status"] = "queued"
        _JOBS[job_id]["error"] = None
    _save_job(job_id)
    threading.Thread(target=_run_stages_1_to_4, args=(job_id,), daemon=True).start()
    return {"status": "restarted", "job_id": job_id}


@app.post("/api/jobs/{job_id}/approve")
def approve_and_animate(job_id: str, force_reanimate: bool = False) -> dict[str, Any]:
    with _JOBS_LOCK:
        if job_id not in _JOBS:
            raise HTTPException(404, "Job not found")
    threading.Thread(target=_run_stages_5_to_6, args=(job_id, force_reanimate), daemon=True).start()
    return {"status": "started", "job_id": job_id}


@app.get("/api/jobs/{job_id}/scene/{beat_id}")
def get_scene_image(job_id: str, beat_id: int) -> FileResponse:
    p = RUNS_DIR / job_id / "scenes" / f"scene_{beat_id:02d}.png"
    if not p.exists():
        raise HTTPException(404, "Scene image not found")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/jobs/{job_id}/video")
def get_final_video(job_id: str) -> FileResponse:
    p = RUNS_DIR / job_id / "final_video.mp4"
    if not p.exists():
        raise HTTPException(404, "Final video not found")
    return FileResponse(p, media_type="video/mp4", filename=f"{job_id}.mp4")


@app.get("/api/jobs/{job_id}/audio")
def get_narration_audio(job_id: str) -> FileResponse:
    p = RUNS_DIR / job_id / "full_narration.wav"
    if not p.exists():
        raise HTTPException(404, "Narration audio not found")
    return FileResponse(p, media_type="audio/wav", filename=f"{job_id}_narration.wav")

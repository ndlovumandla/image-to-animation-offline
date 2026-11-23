"""Stage 1: Paragraph-chunked Voiceover generation via Chatterbox TTS (scales to 15+ min scripts)."""

from __future__ import annotations

import logging
import re
import wave
from pathlib import Path
from typing import Callable

import requests

from .config import PipelineConfig

logger = logging.getLogger("pipeline.stage1_tts")


def _split_script_into_chunks(script_text: str, max_chars: int = 650) -> list[str]:
    """Split a long script along paragraph/sentence boundaries into safe TTS chunks."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", script_text.strip()) if p.strip()]
    chunks: list[str] = []

    for para in paragraphs:
        if len(para) <= max_chars:
            chunks.append(para)
            continue
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", para) if s.strip()]
        buf = ""
        for sent in sentences:
            if buf and len(buf) + 1 + len(sent) > max_chars:
                chunks.append(buf)
                buf = sent
            else:
                buf = f"{buf} {sent}".strip() if buf else sent
        if buf:
            chunks.append(buf)

    return chunks


def _stitch_wav_files(chunk_paths: list[Path], out_wav: Path, pause_sec: float = 0.28) -> float:
    """Concatenate PCM WAV chunks with a natural breath pause between paragraphs."""
    if not chunk_paths:
        raise ValueError("No WAV chunks to stitch.")

    with wave.open(str(chunk_paths[0]), "rb") as first:
        params = first.getparams()
        nchannels = first.getnchannels()
        sampwidth = first.getsampwidth()
        framerate = first.getframerate()

    silence_frames = int(round(max(0.0, pause_sec) * framerate))
    silence_bytes = b"\x00" * (silence_frames * nchannels * sampwidth)

    total_frames = 0
    with wave.open(str(out_wav), "wb") as out:
        out.setparams(params)
        for idx, cp in enumerate(chunk_paths):
            with wave.open(str(cp), "rb") as wf:
                data = wf.readframes(wf.getnframes())
                out.writeframes(data)
                total_frames += wf.getnframes()
            if idx < len(chunk_paths) - 1 and silence_bytes:
                out.writeframes(silence_bytes)
                total_frames += silence_frames

    return total_frames / float(framerate)


def generate_voiceover(
    script_text: str,
    output_dir: Path,
    config: PipelineConfig,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> Path:
    """Synthesize full_narration.wav via chunked Chatterbox TTS (resume-safe) and unload VRAM."""
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir = output_dir / "tts_chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    wav_path = output_dir / "full_narration.wav"

    # 1. Verify Chatterbox is reachable; auto-reload if previously unloaded from VRAM
    base_url = config.chatterbox_url.rstrip("/")
    health_url = f"{base_url}/health"
    logger.info("Checking Chatterbox health at %s ...", health_url)
    resp = requests.get(health_url, timeout=15)
    resp.raise_for_status()
    health = resp.json()
    logger.info("Chatterbox status: %s", health)

    if not health.get("ready"):
        logger.info("Chatterbox model is unloaded — reloading onto GPU via /restart_server ...")
        if progress_cb:
            progress_cb(0, 1, "Reloading Chatterbox TTS model onto GPU...")
        reload_resp = requests.post(f"{base_url}/restart_server", timeout=180)
        reload_resp.raise_for_status()
        logger.info("Chatterbox reloaded: %s", reload_resp.text[:200])

    chunks = _split_script_into_chunks(script_text, max_chars=config.tts_paragraph_max_chars)
    logger.info(
        "Synthesizing %d chars across %d TTS chunk(s) (voice=%s) ...",
        len(script_text),
        len(chunks),
        config.voice_id,
    )

    tts_url = f"{config.chatterbox_url.rstrip('/')}/tts"
    chunk_paths: list[Path] = []

    try:
        for idx, chunk_text in enumerate(chunks, start=1):
            cpath = chunks_dir / f"chunk_{idx:03d}.wav"
            if config.skip_existing and cpath.exists() and cpath.stat().st_size > 2048:
                logger.info("Skipping existing TTS chunk %d/%d (%s)", idx, len(chunks), cpath.name)
                chunk_paths.append(cpath)
                if progress_cb:
                    progress_cb(idx, len(chunks), f"Reused TTS chunk {idx}/{len(chunks)}")
                continue

            payload = {
                "text": chunk_text,
                "voice_mode": config.voice_mode,
                "output_format": "wav",
                "split_text": True,
                "chunk_size": config.tts_chunk_size,
                "temperature": config.tts_temperature,
                "exaggeration": config.tts_exaggeration,
                "cfg_weight": config.tts_cfg_weight,
                "speed_factor": config.tts_speed_factor,
            }
            if config.voice_mode == "clone":
                payload["reference_audio_filename"] = config.voice_id
            else:
                payload["predefined_voice_id"] = config.voice_id

            logger.info("TTS chunk %d/%d (%d chars) ...", idx, len(chunks), len(chunk_text))
            r = requests.post(tts_url, json=payload, timeout=600)
            r.raise_for_status()
            cpath.write_bytes(r.content)
            chunk_paths.append(cpath)
            if progress_cb:
                progress_cb(idx, len(chunks), f"Generated TTS chunk {idx}/{len(chunks)}")
    finally:
        if config.unload_chatterbox:
            unload_chatterbox(config)

    total_sec = _stitch_wav_files(chunk_paths, wav_path, pause_sec=config.tts_paragraph_pause_sec)
    size_mb = wav_path.stat().st_size / (1024 * 1024)
    logger.info("Saved %s (%.2f MB, %.2fs / %.2f min)", wav_path, size_mb, total_sec, total_sec / 60.0)
    return wav_path


def unload_chatterbox(config: PipelineConfig) -> None:
    """Ask Chatterbox to release its GPU VRAM."""
    unload_url = f"{config.chatterbox_url.rstrip('/')}/api/unload"
    try:
        r = requests.post(unload_url, timeout=30)
        if r.ok:
            logger.info("Chatterbox VRAM unloaded successfully (%s).", r.text[:120])
        else:
            logger.warning("Chatterbox /api/unload returned HTTP %s: %s", r.status_code, r.text[:200])
    except Exception as exc:
        logger.warning("Could not unload Chatterbox VRAM: %s", exc)

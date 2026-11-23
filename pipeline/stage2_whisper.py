"""Stage 2: Word-level audio alignment via OpenAI Whisper (or faster-whisper)."""

from __future__ import annotations

import gc
import json
import logging
import re
import wave
from pathlib import Path
from typing import Any

from .config import PipelineConfig

logger = logging.getLogger("pipeline.stage2_whisper")


def _get_wav_duration(wav_path: Path) -> float:
    with wave.open(str(wav_path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / float(rate)


def _format_srt_time(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _group_words_into_sentences(words: list[dict[str, Any]], total_duration: float) -> list[dict[str, Any]]:
    """Build exact sentence-level start/end timestamps from word-level Whisper output."""
    if not words:
        return []

    sentences: list[dict[str, Any]] = []
    buf: list[dict[str, Any]] = []
    sentence_end_re = re.compile(r"[.!?][\"')\]]*$")

    for w in words:
        buf.append(w)
        token = w["word"].strip()
        if sentence_end_re.search(token):
            text = " ".join(x["word"].strip() for x in buf).strip()
            text = re.sub(r"\s+([,.;:!?])", r"\1", text)
            sentences.append({
                "index": len(sentences),
                "text": text,
                "start": round(float(buf[0]["start"]), 3),
                "end": round(float(buf[-1]["end"]), 3),
                "words": buf,
            })
            buf = []

    if buf:
        text = " ".join(x["word"].strip() for x in buf).strip()
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        sentences.append({
            "index": len(sentences),
            "text": text,
            "start": round(float(buf[0]["start"]), 3),
            "end": round(float(buf[-1]["end"]), 3),
            "words": buf,
        })

    # Make sentence boundaries contiguous so video clips sum to exact audio duration
    if sentences:
        sentences[0]["start"] = 0.0
        for i in range(len(sentences) - 1):
            midpoint = round((sentences[i]["end"] + sentences[i + 1]["start"]) / 2.0, 3)
            sentences[i]["end"] = midpoint
            sentences[i + 1]["start"] = midpoint
        sentences[-1]["end"] = round(max(sentences[-1]["end"], total_duration), 3)
        for s in sentences:
            s["duration"] = round(max(0.5, s["end"] - s["start"]), 3)

    return sentences


def _write_srt(sentences: list[dict[str, Any]], srt_path: Path, max_words_per_cue: int = 10) -> None:
    """Write clean, readable synced captions.srt from word timestamps."""
    cues: list[tuple[float, float, str]] = []
    for sent in sentences:
        wlist = sent.get("words") or []
        if not wlist:
            cues.append((sent["start"], sent["end"], sent["text"]))
            continue
        for i in range(0, len(wlist), max_words_per_cue):
            chunk = wlist[i : i + max_words_per_cue]
            c_start = float(chunk[0]["start"])
            c_end = float(chunk[-1]["end"])
            c_text = " ".join(x["word"].strip() for x in chunk).strip()
            c_text = re.sub(r"\s+([,.;:!?])", r"\1", c_text)
            cues.append((c_start, max(c_end, c_start + 0.2), c_text))

    lines: list[str] = []
    for idx, (st, en, txt) in enumerate(cues, start=1):
        lines.append(str(idx))
        lines.append(f"{_format_srt_time(st)} --> {_format_srt_time(en)}")
        lines.append(txt)
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def align_audio(wav_path: Path, output_dir: Path, config: PipelineConfig) -> dict[str, Any]:
    """Transcribe wav_path with word-level timestamps, write alignment.json & captions.srt, and free VRAM."""
    alignment_path = output_dir / "alignment.json"
    srt_path = output_dir / "captions.srt"
    total_duration = _get_wav_duration(wav_path)
    logger.info("Aligning %s (duration=%.2fs) with Whisper model='%s' ...", wav_path, total_duration, config.whisper_model)

    words: list[dict[str, Any]] = []
    full_text = ""

    # Prefer faster-whisper if installed; fall back to openai-whisper
    used_backend = None
    try:
        from faster_whisper import WhisperModel  # type: ignore

        device = config.whisper_device
        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        logger.info("Using faster-whisper (device=%s, compute_type=%s)", device, compute_type)
        model = WhisperModel(config.whisper_model, device=device, compute_type=compute_type)
        segments, _info = model.transcribe(
            str(wav_path),
            language=config.whisper_language,
            word_timestamps=True,
            vad_filter=True,
        )
        text_parts = []
        for seg in segments:
            text_parts.append(seg.text.strip())
            if seg.words:
                for w in seg.words:
                    words.append({
                        "word": w.word.strip(),
                        "start": round(float(w.start), 3),
                        "end": round(float(w.end), 3),
                    })
        full_text = " ".join(text_parts).strip()
        used_backend = "faster-whisper"
        del model
    except ImportError:
        import torch
        import whisper  # type: ignore

        device = config.whisper_device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Using openai-whisper (device=%s)", device)
        model = whisper.load_model(config.whisper_model, device=device)
        result = model.transcribe(
            str(wav_path),
            language=config.whisper_language,
            word_timestamps=True,
            fp16=(device == "cuda"),
        )
        full_text = (result.get("text") or "").strip()
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                words.append({
                    "word": str(w.get("word", "")).strip(),
                    "start": round(float(w["start"]), 3),
                    "end": round(float(w["end"]), 3),
                })
        used_backend = "openai-whisper"
        del model

    # Free GPU memory immediately
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass

    sentences = _group_words_into_sentences(words, total_duration)
    alignment = {
        "audio_file": str(wav_path),
        "backend": used_backend,
        "total_duration": round(total_duration, 3),
        "full_text": full_text,
        "sentences": sentences,
    }
    alignment_path.write_text(json.dumps(alignment, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_srt(sentences, srt_path)
    logger.info(
        "Alignment complete: %d words -> %d sentences -> %s & %s",
        len(words),
        len(sentences),
        alignment_path.name,
        srt_path.name,
    )
    return alignment

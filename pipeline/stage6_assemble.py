"""Stage 6: Final FFmpeg assembly — stitch clips, mux full_narration.wav, optionally burn captions."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from .config import PipelineConfig

logger = logging.getLogger("pipeline.stage6_assemble")


def _escape_ffmpeg_subtitles_path(srt_path: Path) -> str:
    """Escape a path for FFmpeg's libass subtitles filter on Windows and Linux."""
    s = str(srt_path.resolve()).replace("\\", "/")
    s = s.replace(":", "\\:")
    s = s.replace("'", "\\'")
    return s


def assemble_video(
    clip_paths: list[Path],
    narration_wav: Path,
    srt_path: Path | None,
    output_dir: Path,
    config: PipelineConfig,
) -> Path:
    """Concatenate paced clips, mux narration audio, optionally burn captions -> final_video.mp4."""
    if not clip_paths:
        raise ValueError("No animated clips provided for assembly.")

    ffmpeg = shutil.which(config.ffmpeg_bin) or config.ffmpeg_bin
    concat_file = output_dir / "clips_concat.txt"
    lines = [f"file '{p.resolve().as_posix()}'" for p in clip_paths]
    concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    final_mp4 = output_dir / "final_video.mp4"

    cmd = [
        ffmpeg,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-i", str(narration_wav),
    ]

    vf_filters = [f"fps={config.fps}"]
    if config.burn_captions and srt_path and srt_path.exists():
        # Place a dedicated 120px dark caption bar BELOW the whiteboard inside exact 1920x1080
        # so captions NEVER cover any part of the hand-drawn sketches.
        w = config.video_width
        h = config.video_height
        bar_h = max(100, int(round(h * 0.11)))  # ~120px at 1080p
        if bar_h % 2 != 0:
            bar_h += 1
        canvas_h = h - bar_h
        escaped = _escape_ffmpeg_subtitles_path(srt_path)
        style = (
            "FontName=DejaVu Sans,FontSize=16,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,BorderStyle=1,Outline=1,Shadow=0,"
            "MarginL=40,MarginR=40,MarginV=12,Alignment=2"
        )
        vf_filters.extend([
            f"scale={w}:{canvas_h}:force_original_aspect_ratio=decrease",
            f"pad={w}:{canvas_h}:(ow-iw)/2:(oh-ih)/2:color=white",
            f"pad={w}:{h}:0:0:color=#0f172a",
            f"subtitles='{escaped}':force_style='{style}'",
        ])
    vf_filters.append("format=yuv420p")

    cmd += [
        "-vf", ",".join(vf_filters),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", str(config.video_crf),
        "-c:a", "aac",
        "-b:a", config.audio_bitrate,
        "-movflags", "+faststart",
        "-shortest",
        str(final_mp4),
    ]

    logger.info("Assembling final video with FFmpeg -> %s", final_mp4)
    logger.debug("FFmpeg command: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)
    size_mb = final_mp4.stat().st_size / (1024 * 1024)
    logger.info("Finished! Output video: %s (%.2f MB)", final_mp4, size_mb)
    return final_mp4

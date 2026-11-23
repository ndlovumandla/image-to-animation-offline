#!/usr/bin/env python3
"""
Narrated Whiteboard Explainer Video Pipeline (CLI)
==================================================
Supports short & 15+ minute scripts with crash-safe resume across all 6 stages:
  Stage 1: Paragraph-chunked Chatterbox TTS -> full_narration.wav + unload VRAM
  Stage 2: Whisper word-level alignment     -> alignment.json + captions.srt
  Stage 3: Batched Ollama qwen2.5:7b        -> storyboard.json + unload VRAM
  Stage 4: ComfyUI Qwen-Image (8-step/20)   -> scenes/scene_XX.png (+ review) + unload VRAM
  Stage 5: Smooth contour-tracing animator  -> clips/clip_XX.mp4 (two-pass, exact Whisper pacing)
  Stage 6: FFmpeg final assembly            -> final_video.mp4 (+ optional burned captions)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .config import PipelineConfig
from .stage1_tts import generate_voiceover
from .stage2_whisper import align_audio
from .stage3_director import direct_storyboard
from .stage4_comfyui import generate_scenes
from .stage5_animate import animate_all_scenes
from .stage6_assemble import assemble_video


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Script -> Narrated Whiteboard Explainer Video Pipeline")
    p.add_argument("--script", type=Path, required=True, help="Path to input .txt script file")
    p.add_argument("--output-dir", type=Path, required=True, help="Directory for all pipeline outputs")
    p.add_argument(
        "--gpu-host",
        default=os.getenv("SKETCH_GPU_HOST", "127.0.0.1"),
        help="GPU server IP/hostname hosting Chatterbox, Ollama, and ComfyUI (default: 127.0.0.1)",
    )
    p.add_argument("--voice", default="Fiona.wav", help="Chatterbox predefined voice filename (default: Fiona.wav)")
    p.add_argument("--voice-mode", choices=["predefined", "clone"], default="predefined")
    p.add_argument("--whisper-model", default="medium", help="Whisper model size (tiny/base/small/medium/large-v3)")
    p.add_argument("--ollama-model", default="gemma3:12b", help="Ollama Visual Director model (default: gemma3:12b)")
    p.add_argument("--no-lightning", action="store_true", help="Use full 20-step Qwen-Image instead of 8-step Lightning LoRA")
    p.add_argument("--workflow", type=Path, default=None, help="Custom ComfyUI API workflow JSON path")
    p.add_argument("--workers", type=int, default=4, help="Parallel CPU workers for Stage 5 animation (default: 4)")
    p.add_argument("--no-skip", action="store_true", help="Force regenerate existing chunks/scenes/clips")
    p.add_argument("--review", action="store_true", help="Pause after Stage 4 to inspect and re-roll any scene")
    p.add_argument("--burn-captions", action="store_true", help="Burn synced Whisper captions into final MP4")
    p.add_argument("--no-hand", action="store_true", help="Disable drawing hand overlay in Stage 5")
    p.add_argument("--from-stage", type=int, default=1, choices=[1, 2, 3, 4, 5, 6], help="Start from stage N (resume)")
    p.add_argument("--to-stage", type=int, default=6, choices=[1, 2, 3, 4, 5, 6], help="Stop after stage N")
    p.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("pipeline")

    out_dir: Path = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = PipelineConfig(
        gpu_host=args.gpu_host,
        voice_mode=args.voice_mode,
        voice_id=args.voice,
        whisper_model=args.whisper_model,
        ollama_model=args.ollama_model,
        use_lightning=not args.no_lightning,
        animate_workers=args.workers,
        skip_existing=not args.no_skip,
        review_scenes=args.review,
        burn_captions=args.burn_captions,
        draw_hand=not args.no_hand,
    )
    if args.workflow:
        cfg.comfyui_workflow_path = args.workflow.resolve()

    wav_path = out_dir / "full_narration.wav"
    alignment_path = out_dir / "alignment.json"
    srt_path = out_dir / "captions.srt"
    storyboard_path = out_dir / "storyboard.json"

    if args.from_stage <= 1 <= args.to_stage:
        logger.info("=== STAGE 1/6: Voiceover Generation (Chatterbox TTS) ===")
        script_text = args.script.read_text(encoding="utf-8").strip()
        if not script_text:
            raise ValueError(f"Script file is empty: {args.script}")
        wav_path = generate_voiceover(script_text, out_dir, cfg)

    alignment = None
    if args.from_stage <= 2 <= args.to_stage:
        logger.info("=== STAGE 2/6: Audio Alignment (Whisper Word Timestamps) ===")
        alignment = align_audio(wav_path, out_dir, cfg)
    elif alignment_path.exists():
        alignment = json.loads(alignment_path.read_text(encoding="utf-8"))

    storyboard = None
    if args.from_stage <= 3 <= args.to_stage:
        logger.info("=== STAGE 3/6: Visual Director (Ollama %s) ===", cfg.ollama_model)
        if alignment is None:
            raise FileNotFoundError(f"Missing {alignment_path}. Run Stage 2 first.")
        storyboard = direct_storyboard(alignment, out_dir, cfg)
    elif storyboard_path.exists():
        storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))

    if args.from_stage <= 4 <= args.to_stage:
        logger.info("=== STAGE 4/6: Scene Generation (ComfyUI Qwen-Image) ===")
        if storyboard is None:
            raise FileNotFoundError(f"Missing {storyboard_path}. Run Stage 3 first.")
        generate_scenes(storyboard, out_dir, cfg)

    clip_paths = []
    if args.from_stage <= 5 <= args.to_stage:
        logger.info("=== STAGE 5/6: Smooth Contour-Tracing Whiteboard Animation ===")
        if storyboard is None:
            raise FileNotFoundError(f"Missing {storyboard_path}. Run Stage 3 first.")
        clip_paths = animate_all_scenes(storyboard, out_dir, cfg)
    elif storyboard is not None:
        clip_paths = [
            out_dir / "clips" / f"clip_{int(b['beat_id']):02d}.mp4"
            for b in storyboard["beats"]
        ]

    if args.from_stage <= 6 <= args.to_stage:
        logger.info("=== STAGE 6/6: Final Assembly (FFmpeg) ===")
        if not clip_paths:
            raise FileNotFoundError("No animated clips found. Run Stage 5 first.")
        final_mp4 = assemble_video(
            clip_paths=clip_paths,
            narration_wav=wav_path,
            srt_path=srt_path if srt_path.exists() else None,
            output_dir=out_dir,
            config=cfg,
        )
        logger.info("ALL DONE! Final explainer video: %s", final_mp4)

    return 0


if __name__ == "__main__":
    sys.exit(main())

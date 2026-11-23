"""Central configuration for the Narrated Illustrated / Whiteboard Explainer Video Pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .characters import get_environment

WHITEBOARD_STYLE_SUFFIX = (
    "hand drawn colored marker sketch style, whiteboard-animation look, "
    "white background, bold outlines, flat watercolour-like fills"
)


@dataclass
class PipelineConfig:
    """Configuration for all 6 pipeline stages (supports short & 15+ minute scripts)."""

    # Local or remote GPU host (defaults to localhost so forks work out of the box)
    gpu_host: str = field(default_factory=lambda: os.getenv("SKETCH_GPU_HOST", "127.0.0.1"))
    chatterbox_url: str = ""
    ollama_url: str = ""
    comfyui_url: str = ""

    # Stage 1: Chatterbox TTS (paragraph-chunked for 15+ min scripts)
    voice_mode: str = "predefined"  # "predefined" or "clone"
    voice_id: str = "Fiona.wav"
    tts_temperature: float = 0.75
    tts_exaggeration: float = 0.5
    tts_cfg_weight: float = 0.5
    tts_speed_factor: float = 1.0
    tts_chunk_size: int = 240
    tts_paragraph_max_chars: int = 650
    tts_paragraph_pause_sec: float = 0.28
    unload_chatterbox: bool = True

    # Stage 2: Whisper Audio Alignment
    whisper_model: str = "medium"  # tiny, base, small, medium, large-v3
    whisper_device: str = "auto"   # auto, cuda, cpu
    whisper_language: str = "en"

    # Stage 3: Ollama Visual Director (batched for 15+ min scripts)
    ollama_model: str = "gemma3:12b"
    target_beat_min_sec: float = 7.0
    target_beat_max_sec: float = 16.0
    director_batch_sentences: int = 16
    unload_ollama: bool = True

    # Visual Creative Direction (Characters, Banner Palette, Environment)
    character_description: str = ""
    cast_characters: list[str] = field(default_factory=list)
    banner_palette: str = "navy_teal"       # navy_teal, charcoal_gold, emerald_slate, royal_coral, terracotta_navy, minimal_ink, auto
    environment_mode: str = "auto"          # auto, office, outdoor, classroom, whiteboard, mixed_editorial

    # Stage 4: ComfyUI Qwen-Image INT8/FP8 (native 1664x928 16:9 + Vision Auto-QA Critic)
    use_lightning: bool = True
    comfyui_workflow_path: Path | None = None
    image_width: int = 1664
    image_height: int = 928
    image_steps: int = 8
    image_cfg: float = 1.0
    image_shift: float = 3.1
    base_seed: int = 42000
    enable_vision_qa: bool = True
    vision_qa_max_retries: int = 2
    review_scenes: bool = False
    unload_comfyui: bool = True

    # Stage 5: Audio-Synced Sequential Element-Complete Whiteboard Animation
    vision_sync_model: str = "gemma3:12b"
    enable_vision_sync: bool = True
    fps: int = 30
    video_width: int = 1920
    video_height: int = 1080
    draw_hand: bool = True
    end_color: bool = True
    min_hold_sec: float = 1.0
    animate_workers: int = 4
    skip_existing: bool = True

    # Stage 6: FFmpeg Assembly
    burn_captions: bool = False
    ffmpeg_bin: str = field(default_factory=lambda: os.getenv("FFMPEG_BIN", "ffmpeg"))
    ffprobe_bin: str = field(default_factory=lambda: os.getenv("FFPROBE_BIN", "ffprobe"))
    video_crf: int = 19
    audio_bitrate: str = "192k"

    @property
    def style_suffix(self) -> str:
        return get_environment(self.environment_mode)["style_suffix"]

    def __post_init__(self) -> None:
        if not self.chatterbox_url:
            self.chatterbox_url = os.getenv("CHATTERBOX_URL", f"http://{self.gpu_host}:8004")
        if not self.ollama_url:
            self.ollama_url = os.getenv("OLLAMA_URL", f"http://{self.gpu_host}:11434")
        if not self.comfyui_url:
            self.comfyui_url = os.getenv("COMFYUI_URL", f"http://{self.gpu_host}:8188")
        if self.comfyui_workflow_path is None:
            wf_dir = Path(__file__).parent / "workflows"
            if self.use_lightning:
                self.comfyui_workflow_path = wf_dir / "qwen_image_lightning8.json"
                if self.image_steps == 20:
                    self.image_steps = 8
                if self.image_cfg == 2.5:
                    self.image_cfg = 1.0
            else:
                self.comfyui_workflow_path = wf_dir / "qwen_image_int8.json"
                if self.image_steps == 8:
                    self.image_steps = 20
                if self.image_cfg == 1.0:
                    self.image_cfg = 2.5

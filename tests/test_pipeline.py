"""Offline unit & integration tests for the 6-Stage AI Explainer & Whiteboard Sketch Studio.

Designed to run in GitHub Actions and on any developer laptop with ZERO GPU or external AI
services required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from pipeline.characters import (
    BANNER_PALETTES,
    CHARACTER_PRESETS,
    ENVIRONMENTS,
    filter_characters,
    get_environment,
    get_palette,
)
from pipeline.config import PipelineConfig
from pipeline.stage3_director import _compile_spatial_prompt, _extract_json
from pipeline.stage4_comfyui import NEGATIVE_PROMPT, _patch_workflow
from pipeline.stage5_animate import (
    _extract_ink_and_color_masks,
    _render_single_beat_worker,
    _segment_scene_objects,
)
from pipeline.web_ui import app

WORKFLOWS_DIR = REPO_ROOT / "pipeline" / "workflows"


def test_config_portable_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SKETCH_GPU_HOST", raising=False)
    monkeypatch.delenv("CHATTERBOX_URL", raising=False)
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.delenv("COMFYUI_URL", raising=False)

    cfg = PipelineConfig()
    assert cfg.gpu_host == "127.0.0.1"
    assert cfg.chatterbox_url == "http://127.0.0.1:8004"
    assert cfg.ollama_url == "http://127.0.0.1:11434"
    assert cfg.comfyui_url == "http://127.0.0.1:8188"
    assert cfg.image_width == 1664
    assert cfg.image_height == 928
    assert cfg.comfyui_workflow_path is not None
    assert cfg.comfyui_workflow_path.exists()


def test_config_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKETCH_GPU_HOST", "10.0.0.5")
    cfg = PipelineConfig(use_lightning=False)
    assert cfg.chatterbox_url == "http://10.0.0.5:8004"
    assert cfg.ollama_url == "http://10.0.0.5:11434"
    assert cfg.comfyui_url == "http://10.0.0.5:8188"
    assert cfg.comfyui_workflow_path is not None
    assert cfg.comfyui_workflow_path.name == "qwen_image_int8.json"


def test_character_presets_and_uniform_banner_palettes() -> None:
    assert len(CHARACTER_PRESETS) >= 20
    assert len(ENVIRONMENTS) >= 5
    assert len(BANNER_PALETTES) >= 6

    sample_gender = CHARACTER_PRESETS[0]["gender"]
    filtered = filter_characters(gender=sample_gender)
    assert len(filtered) > 0
    assert all(c["gender"].lower() == sample_gender.lower() for c in filtered)

    # Every non-auto banner palette must enforce single-color lettering without accent leaks
    for pal in BANNER_PALETTES:
        if pal["id"] == "auto":
            continue
        prompt = pal["prompt"].lower()
        assert "uniform" in prompt or "solid black" in prompt
        assert "accented with" not in prompt

    assert get_palette("navy_teal")["id"] == "navy_teal"
    assert get_environment("office")["id"] == "office"


def test_stage3_spatial_prompt_no_all_caps_header_leak() -> None:
    cfg = PipelineConfig(
        character_description="friendly presenter wearing a navy sweater",
        banner_palette="navy_teal",
        environment_mode="office",
    )
    blueprint = {
        "banner_title": "WELCOME BACK",
        "setting_name": "modern sunlit office with glass walls and potted plants",
        "character_pose": "smiling and gesturing toward the board",
        "speech_bubble_text": "LET'S BEGIN!",
        "background_props": ["wall calendar", "desk monitor", "desk lamp", "coffee mug"],
        "foreground_objects": [
            {"object": "checklist", "label": "TASKS"},
            {"object": "clock icon", "label": "TIME"},
        ],
    }
    prompt = _compile_spatial_prompt(
        beat_blueprint=blueprint,
        recurring_character=cfg.character_description,
        cast_characters=[],
        config=cfg,
    )

    assert '"WELCOME BACK"' in prompt
    assert "BEGIN!" in prompt
    # Regression guard: uppercase section headers must never appear in prompts
    for forbidden in ("TOP BANNER:", "SPEECH BUBBLE:", "LEFT SIDE:", "RIGHT SIDE:", "BACKGROUND:"):
        assert forbidden not in prompt


def test_stage3_extract_json_handles_fenced_blocks() -> None:
    raw = 'Here is the plan:\n```json\n{"beats": [{"beat_id": 1, "banner_title": "INTRO"}]}\n```'
    parsed = _extract_json(raw)
    assert parsed["beats"][0]["banner_title"] == "INTRO"


def test_stage4_workflows_and_negative_prompt_guards() -> None:
    assert "multicolored letters" in NEGATIVE_PROMPT.lower()
    assert "multicolored text" in NEGATIVE_PROMPT.lower()

    cfg = PipelineConfig()
    for wf_name in ("qwen_image_lightning8.json", "qwen_image_int8.json"):
        wf_path = WORKFLOWS_DIR / wf_name
        assert wf_path.exists(), f"Missing workflow: {wf_path}"
        wf = json.loads(wf_path.read_text(encoding="utf-8"))
        patched = _patch_workflow(
            template=wf,
            prompt_text="Clean educational office illustration",
            seed=42001,
            filename_prefix="test_scene_01",
            config=cfg,
        )
        assert isinstance(patched, dict)
        assert len(patched) > 0


def test_stage5_whole_object_segmentation_and_render(tmp_path: Path) -> None:
    # Create a synthetic whiteboard scene with banner, character box, and diagram icons
    img = np.full((540, 960, 3), 255, dtype=np.uint8)
    # Top navy banner
    cv2.rectangle(img, (0, 0), (960, 75), (120, 45, 20), -1)
    cv2.putText(img, "TEAMWORK", (320, 52), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 4)
    # Left character silhouette (head + torso connected)
    cv2.circle(img, (210, 210), 48, (30, 30, 30), 4)
    cv2.rectangle(img, (150, 260), (270, 460), (140, 70, 30), -1)
    cv2.rectangle(img, (150, 260), (270, 460), (20, 20, 20), 4)
    # Right diagram elements
    cv2.rectangle(img, (520, 170), (660, 300), (20, 20, 20), 4)
    cv2.circle(img, (790, 235), 60, (40, 150, 200), -1)
    cv2.circle(img, (790, 235), 60, (20, 20, 20), 4)

    ink_mask, color_mask = _extract_ink_and_color_masks(img)
    assert int(np.count_nonzero(ink_mask)) > 500
    assert int(np.count_nonzero(color_mask)) > 500

    objects = _segment_scene_objects(img, ink_mask)
    assert len(objects) >= 2

    scene_path = tmp_path / "scene_01.png"
    clip_path = tmp_path / "clip_01.mp4"
    cv2.imwrite(str(scene_path), img)

    out = _render_single_beat_worker(
        (
            str(scene_path),
            str(clip_path),
            2.0,
            [],
            {
                "fps": 12,
                "video_width": 640,
                "video_height": 360,
                "draw_hand": True,
                "end_color": True,
                "min_hold_sec": 0.4,
                "enable_vision_sync": False,
            },
        )
    )
    assert Path(out).exists()
    assert Path(out).stat().st_size > 1000


def test_web_ui_endpoints() -> None:
    client = TestClient(app)

    r_home = client.get("/")
    assert r_home.status_code == 200
    assert "text/html" in r_home.headers["content-type"]

    r_presets = client.get("/api/presets")
    assert r_presets.status_code == 200
    data = r_presets.json()
    assert len(data["characters"]) >= 20
    assert len(data["banner_palettes"]) >= 6
    assert len(data["environments"]) >= 5

    r_jobs = client.get("/api/jobs")
    assert r_jobs.status_code == 200
    assert isinstance(r_jobs.json(), list)

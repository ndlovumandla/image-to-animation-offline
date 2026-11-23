"""Stage 4: Scene generation via ComfyUI API (Qwen-Image FP8/INT8) + Vision Auto-QA Critic & Auto-Reroll."""

from __future__ import annotations

import base64
import copy
import json
import logging
import random
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import cv2
import requests

from .config import PipelineConfig

logger = logging.getLogger("pipeline.stage4_comfyui")

NEGATIVE_PROMPT = (
    "powerpoint slide, empty speech bubble, blank speech bubble, blank thought bubble, "
    "missing person, rainbow banner, rainbow gradient, multicolor rainbow ribbon, "
    "multicolored letters, multicolored text, alternating letter colors, "
    "sparse empty composition, dark black background, photorealistic photo, 3d render, "
    "blurry text, garbled letters, misspelled text, watermarks, low contrast"
)


def _patch_workflow(
    template: dict[str, Any],
    prompt_text: str,
    seed: int,
    filename_prefix: str,
    config: PipelineConfig,
) -> dict[str, Any]:
    wf = copy.deepcopy(template)
    for _node_id, node in wf.items():
        if not isinstance(node, dict):
            continue
        cls = node.get("class_type", "")
        inputs = node.get("inputs", {})
        meta_title = (node.get("_meta") or {}).get("title", "").lower()

        if cls in ("CLIPTextEncode", "TextEncodeQwenImageEdit") and isinstance(inputs.get("text"), str):
            if "negative" in meta_title or "__NEGATIVE_PROMPT__" in inputs["text"]:
                inputs["text"] = NEGATIVE_PROMPT
            elif "positive" in meta_title or "__POSITIVE_PROMPT__" in inputs["text"]:
                inputs["text"] = prompt_text
        elif cls in ("EmptySD3LatentImage", "EmptyLatentImage"):
            inputs["width"] = config.image_width
            inputs["height"] = config.image_height
            inputs["batch_size"] = 1
        elif cls == "ModelSamplingAuraFlow":
            inputs["shift"] = config.image_shift
        elif cls == "KSampler":
            inputs["seed"] = seed
            inputs["steps"] = config.image_steps
            inputs["cfg"] = config.image_cfg
        elif cls == "SaveImage":
            inputs["filename_prefix"] = filename_prefix
    return wf


def _submit_and_download(
    workflow: dict[str, Any],
    dest_path: Path,
    config: PipelineConfig,
    timeout_sec: int = 900,
) -> Path:
    base_url = config.comfyui_url.rstrip("/")
    client_id = str(uuid.uuid4())

    r = requests.post(
        f"{base_url}/prompt",
        json={"prompt": workflow, "client_id": client_id},
        timeout=30,
    )
    r.raise_for_status()
    prompt_id = r.json()["prompt_id"]
    logger.info("Queued ComfyUI job %s -> %s", prompt_id, dest_path.name)

    deadline = time.time() + timeout_sec
    image_info = None
    while time.time() < deadline:
        hist_r = requests.get(f"{base_url}/history/{prompt_id}", timeout=30)
        hist_r.raise_for_status()
        hist = hist_r.json()
        if prompt_id in hist:
            entry = hist[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI execution failed for {prompt_id}: {status}")
            outputs = entry.get("outputs", {})
            for _nid, out in outputs.items():
                images = out.get("images") or []
                if images:
                    image_info = images[0]
                    break
            if image_info:
                break
        time.sleep(1.5)

    if not image_info:
        raise TimeoutError(f"ComfyUI job {prompt_id} did not produce an image within {timeout_sec}s.")

    params = {
        "filename": image_info["filename"],
        "subfolder": image_info.get("subfolder", ""),
        "type": image_info.get("type", "output"),
    }
    img_r = requests.get(f"{base_url}/view", params=params, timeout=60)
    img_r.raise_for_status()
    dest_path.write_bytes(img_r.content)
    logger.info("Saved %s (%.1f KB)", dest_path, dest_path.stat().st_size / 1024.0)
    return dest_path


def unload_comfyui(config: PipelineConfig) -> None:
    """Ask ComfyUI to unload models and free GPU VRAM."""
    url = f"{config.comfyui_url.rstrip('/')}/free"
    try:
        r = requests.post(url, json={"unload_models": True, "free_memory": True}, timeout=30)
        if r.ok:
            logger.info("ComfyUI VRAM freed (unload_models=True, free_memory=True).")
        else:
            logger.warning("ComfyUI /free returned HTTP %s: %s", r.status_code, r.text[:200])
    except Exception as exc:
        logger.warning("Could not free ComfyUI VRAM: %s", exc)


def _encode_qa_jpeg_b64(img_path: Path) -> str:
    img = cv2.imread(str(img_path))
    if img is None:
        raise FileNotFoundError(f"Cannot read {img_path}")
    small = cv2.resize(img, (960, 540), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    if not ok:
        raise RuntimeError(f"JPEG encode failed for {img_path}")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _run_vision_qa_critic(
    storyboard: dict[str, Any],
    scenes_dir: Path,
    config: PipelineConfig,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> list[tuple[int, str]]:
    """Inspect all generated scenes with gemma3:12b Vision (while ComfyUI is unloaded) and flag any defects."""
    beats = storyboard["beats"]
    recurring = storyboard.get("recurring_character", "")
    chat_url = f"{config.ollama_url.rstrip('/')}/api/chat"
    failed: list[tuple[int, str]] = []

    logger.info("Running Vision Auto-QA Critic (%s) across %d scene(s) ...", config.vision_sync_model, len(beats))
    try:
        for idx, beat in enumerate(beats, start=1):
            beat_id = int(beat["beat_id"])
            img_path = scenes_dir / f"scene_{beat_id:02d}.png"
            if not img_path.exists():
                continue

            b64 = _encode_qa_jpeg_b64(img_path)
            banner_expected = str(beat.get("banner_title") or "").strip().upper()
            bubble_expected = str(beat.get("speech_bubble_text") or "").strip().upper()
            setting_expected = beat.get("setting", "")
            qa_prompt = (
                f"You are a strict OCR & visual QA critic for an illustrated explainer video.\n"
                f"Expected presenter: {recurring}\n"
                f"Expected setting: {setting_expected}\n"
                f"Expected top banner text (EXACT): \"{banner_expected}\"\n"
                f"Expected speech bubble text: \"{bubble_expected}\"\n\n"
                f"Inspect this image carefully:\n"
                f"1. Transcribe the EXACT letters/words currently visible on the top banner into 'observed_banner_text' (include any gibberish, numbers, or typos verbatim!).\n"
                f"2. Transcribe the EXACT letters/words inside the speech bubble into 'observed_bubble_text' (empty string if blank).\n"
                f"3. character_present: Is the presenter clearly visible?\n"
                f"4. bubbles_filled: Are ALL speech/thought bubbles filled with real, correctly spelled English words (NO blank bubbles, NO gibberish)?\n"
                f"5. text_clean: Is ALL visible text on the banner and labels real, sensible, correctly spelled English with NO random numbers, stray symbols, or garbled words?\n"
                f"6. rich_objects: Are there at least 4 distinct objects/props/diagrams?\n"
                f"7. banner_clean: Is the top banner solid/cohesive (NOT rainbow)?\n"
                f"Return ONLY JSON: "
                f'{{"observed_banner_text": "", "observed_bubble_text": "", "character_present": true, "bubbles_filled": true, "text_clean": true, "rich_objects": true, "banner_clean": true}}'
            )

            try:
                r = requests.post(
                    chat_url,
                    json={
                        "model": config.vision_sync_model,
                        "format": "json",
                        "stream": False,
                        "keep_alive": "2m" if idx < len(beats) else 0,
                        "options": {"temperature": 0.0, "num_ctx": 4096},
                        "messages": [{"role": "user", "content": qa_prompt, "images": [b64]}],
                    },
                    timeout=120,
                )
                r.raise_for_status()
                raw = r.json()["message"]["content"]
                parsed = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
                beat["qa_report"] = parsed

                # Deterministic Python OCR verification on the top banner text!
                obs_banner = "".join(ch for ch in str(parsed.get("observed_banner_text") or "").upper() if ch.isalnum() or ch == " ").strip()
                exp_banner = "".join(ch for ch in banner_expected if ch.isalnum() or ch == " ").strip()
                banner_text_ok = True
                if exp_banner and obs_banner:
                    # Reject if observed banner has extra junk words or major mismatch
                    exp_words = set(exp_banner.split())
                    obs_words = set(obs_banner.split())
                    extra_words = obs_words - exp_words
                    missing_words = exp_words - obs_words
                    if extra_words or len(missing_words) > max(0, len(exp_words) // 3):
                        banner_text_ok = False
                elif exp_banner and not obs_banner:
                    banner_text_ok = False

                passed = bool(
                    parsed.get("character_present", True)
                    and parsed.get("bubbles_filled", True)
                    and parsed.get("text_clean", True)
                    and parsed.get("rich_objects", True)
                    and parsed.get("banner_clean", True)
                    and banner_text_ok
                )
                if not passed:
                    fixes = []
                    if not banner_text_ok or not parsed.get("text_clean", True):
                        fixes.append(f"top banner must display ONLY the exact cleanly spelled words \"{banner_expected}\" with no extra numbers, symbols, or garbled text")
                    if not parsed.get("character_present", True):
                        fixes.append(f"draw the presenter ({recurring}) prominently on the left foreground")
                    if not parsed.get("bubbles_filled", True):
                        fixes.append(f"speech bubble must clearly display \"{bubble_expected}\" with no blank bubbles")
                    if not parsed.get("rich_objects", True):
                        fixes.append("include 6 detailed real-world props and labelled diagrams")
                    if not parsed.get("banner_clean", True):
                        fixes.append("use a single solid dark banner with crisp white lettering and no rainbow colors")
                    fix_str = "; ".join(fixes)
                    failed.append((beat_id, fix_str))
                    logger.warning(
                        "Vision QA flagged scene_%02d.png (observed banner='%s' vs expected='%s'): %s",
                        beat_id,
                        obs_banner,
                        exp_banner,
                        fix_str,
                    )
                else:
                    logger.info("Vision QA PASSED scene_%02d.png (banner='%s')", beat_id, obs_banner)
            except Exception as exc:
                logger.warning("Vision QA skipped for scene_%02d: %s", beat_id, exc)

            if progress_cb:
                progress_cb(idx, len(beats), f"Vision QA checked scene_{beat_id:02d} ({idx}/{len(beats)})")
    finally:
        try:
            requests.post(
                f"{config.ollama_url.rstrip('/')}/api/generate",
                json={"model": config.vision_sync_model, "keep_alive": 0},
                timeout=30,
            )
            logger.info("Unloaded Vision QA model '%s' from VRAM.", config.vision_sync_model)
        except Exception:
            pass

    return failed


def reroll_single_scene(
    storyboard: dict[str, Any],
    beat_id: int,
    output_dir: Path,
    config: PipelineConfig,
    new_prompt: str | None = None,
    seed: int | None = None,
    unload_after: bool = True,
) -> Path:
    scenes_dir = output_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    matching = [b for b in storyboard["beats"] if int(b["beat_id"]) == int(beat_id)]
    if not matching:
        raise ValueError(f"Beat {beat_id} not found in storyboard.")
    beat = matching[0]

    if new_prompt and new_prompt.strip():
        beat["image_prompt"] = new_prompt.strip()
    use_seed = seed if seed is not None else random.randint(1000, 9_999_999)

    template = json.loads(config.comfyui_workflow_path.read_text(encoding="utf-8"))
    dest = scenes_dir / f"scene_{int(beat_id):02d}.png"
    wf = _patch_workflow(
        template=template,
        prompt_text=beat["image_prompt"],
        seed=use_seed,
        filename_prefix=f"whiteboard_scene_{int(beat_id):02d}_reroll",
        config=config,
    )
    try:
        _submit_and_download(wf, dest, config)
        beat["seed"] = use_seed
        (output_dir / "storyboard.json").write_text(
            json.dumps(storyboard, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    finally:
        if unload_after and config.unload_comfyui:
            unload_comfyui(config)

    return dest


def generate_scenes(
    storyboard: dict[str, Any],
    output_dir: Path,
    config: PipelineConfig,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> list[Path]:
    """Generate scene_XX.png for every beat, run Vision Auto-QA Critic + Auto-Reroll, then free VRAM."""
    scenes_dir = output_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    base_url = config.comfyui_url.rstrip("/")
    logger.info("Checking ComfyUI API at %s ...", base_url)
    requests.get(f"{base_url}/system_stats", timeout=15).raise_for_status()

    template = json.loads(config.comfyui_workflow_path.read_text(encoding="utf-8"))
    beats = storyboard["beats"]
    scene_paths: list[Path] = []

    try:
        for idx, beat in enumerate(beats, start=1):
            beat_id = int(beat["beat_id"])
            dest = scenes_dir / f"scene_{beat_id:02d}.png"
            if config.skip_existing and dest.exists() and dest.stat().st_size > 10_000:
                logger.info("Skipping existing scene_%02d.png (%d/%d)", beat_id, idx, len(beats))
                scene_paths.append(dest)
                if progress_cb:
                    progress_cb(idx, len(beats), f"Reused scene_{beat_id:02d}.png ({idx}/{len(beats)})")
                continue

            seed = config.base_seed + beat_id * 101
            wf = _patch_workflow(
                template=template,
                prompt_text=beat["image_prompt"],
                seed=seed,
                filename_prefix=f"whiteboard_scene_{beat_id:02d}",
                config=config,
            )
            logger.info(
                "Generating scene_%02d.png (%d/%d, %dx%d) — Banner: '%s'",
                beat_id,
                idx,
                len(beats),
                config.image_width,
                config.image_height,
                beat["banner_title"],
            )
            _submit_and_download(wf, dest, config)
            beat["seed"] = seed
            scene_paths.append(dest)
            if progress_cb:
                progress_cb(idx, len(beats), f"Generated scene_{beat_id:02d}.png ({idx}/{len(beats)})")

        # Free ComfyUI VRAM BEFORE loading gemma3:12b Vision QA Critic (zero VRAM collision!)
        if config.enable_vision_qa and config.vision_qa_max_retries > 0:
            unload_comfyui(config)
            for attempt in range(config.vision_qa_max_retries):
                failed = _run_vision_qa_critic(storyboard, scenes_dir, config, progress_cb=progress_cb)
                if not failed:
                    logger.info("Vision Auto-QA: ALL scenes passed quality inspection!")
                    break
                logger.info("Vision Auto-QA auto-rerolling %d scene(s) (pass %d/%d) ...", len(failed), attempt + 1, config.vision_qa_max_retries)
                for f_idx, (beat_id, fix_str) in enumerate(failed, start=1):
                    beat = next(b for b in beats if int(b["beat_id"]) == beat_id)
                    fixed_prompt = f"{beat['image_prompt']} Important correction: {fix_str}."
                    reroll_single_scene(
                        storyboard,
                        beat_id,
                        output_dir,
                        config,
                        new_prompt=fixed_prompt,
                        unload_after=False,
                    )
                    if progress_cb:
                        progress_cb(f_idx, len(failed), f"Auto-fixed scene_{beat_id:02d}.png ({f_idx}/{len(failed)})")
                if attempt + 1 < config.vision_qa_max_retries:
                    unload_comfyui(config)

        (output_dir / "storyboard.json").write_text(
            json.dumps(storyboard, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    finally:
        if config.unload_comfyui:
            unload_comfyui(config)

    return scene_paths

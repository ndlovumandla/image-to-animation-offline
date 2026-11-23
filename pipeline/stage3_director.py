"""Stage 3: Structured World-Building Visual Director + Deterministic Spatial Prompt Compiler.

Instead of letting an LLM write loose prose prompts (which often drop characters, leave speech
bubbles empty, or produce sparse generic rooms), this stage:
  1. Uses gemma3:12b (or qwen2.5:7b) to output a strict SPATIAL BLUEPRINT JSON per beat:
     - exact real-world setting matching the script
     - 5-7 concrete world/environment props (furniture, equipment, tools, decor)
     - exact character pose & handheld prop
     - 4-6 labelled foreground visual objects/diagrams
     - exact short 2-4 word speech bubble text (never blank!)
  2. Deterministically compiles every blueprint into a high-precision Qwen-Image prompt with
     the primary character anchored in the first 30 words, zero rainbow banners, and crisp quoted text.
  3. Unloads the Ollama model from VRAM (keep_alive=0) immediately when done.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

import requests

from .characters import get_environment, get_palette
from .config import PipelineConfig

logger = logging.getLogger("pipeline.stage3_director")


def _build_system_prompt(config: PipelineConfig) -> str:
    env = get_environment(config.environment_mode)

    return f"""You are an elite Visual Explainer Video Director designing ultra-rich, detailed, script-accurate illustrated scenes.

STRICT BLUEPRINT RULES:
1. ENVIRONMENT ACCURACY:
   {env['director_rule']}
   Read the exact topic of each beat and pick a specific, concrete real-world setting (NOT a generic empty room).
   Include 5 to 7 concrete, recognizable real-world objects/equipment in "background_props" (for example: in an office -> dual-monitor workstation, ergonomic chair, wall calendar, filing cabinet, potted plant, coffee mug, desk lamp, glass meeting room; on a site -> safety cones, hard hats, hazard sign, toolbox, clipboard, scaffolding; in a clinic -> reception desk, medical chart, stethoscope, medicine cabinet, wall clock).
2. INFORMATION-RICH FOREGROUND (4 to 6 LABELLED OBJECTS):
   Every beat MUST have 4 to 6 distinct, specific foreground visual objects in "foreground_objects" that directly illustrate EVERY concept, step, example, or number mentioned in the narration (checklists, bar charts, comparison cards, numbered steps, equipment diagrams, calendars, clocks, laptops, notebooks, colleagues collaborating).
   Every foreground object MUST have a short, crisp 1-4 word uppercase "label".
3. SPEECH BUBBLE TEXT (NEVER BLANK!):
   Every beat MUST include a short, punchy 2-4 word ALL-CAPS "speech_bubble_text" summarizing the beat's key takeaway (e.g. "PLAN FIRST!", "CHECK EVERY STEP!", "STAY FOCUSED!"). NEVER leave it empty.
4. CHARACTER ACTION & PROP:
   Describe a specific, dynamic "character_pose" for the primary presenter (e.g. "standing in the left foreground holding a clipboard and gesturing toward the timeline chart").
5. BEAT GROUPING:
   Group consecutive sentences into visual beats targeting ~7 to 16 seconds per beat.
   Every sentence index given in the input MUST appear in exactly one beat, in strictly ascending order, with no gaps and no overlaps.

Return ONLY valid JSON matching this EXACT schema (no markdown fences, no commentary):
{{
  "recurring_character": "exact visual description of primary presenter",
  "beats": [
    {{
      "beat_id": 1,
      "sentence_indices": [0, 1],
      "banner_title": "SHORT TITLE",
      "setting_name": "bright modern open-plan corporate office",
      "background_props": [
        "dual-monitor workstation desk",
        "wall calendar with circled dates",
        "filing cabinet and inbox trays",
        "potted monstera plant",
        "desk lamp and ceramic coffee mug",
        "glass-walled meeting room in background"
      ],
      "character_pose": "standing prominently in the left foreground holding a marker and clipboard, smiling and pointing toward the workflow diagram",
      "foreground_objects": [
        {{"object": "standing flipchart with 3 checked boxes", "label": "SET PRIORITIES"}},
        {{"object": "open laptop showing a rising bar chart", "label": "TRACK PROGRESS"}},
        {{"object": "wall clock and daily planner notebook", "label": "TIME BLOCKING"}},
        {{"object": "two colleagues collaborating over sticky notes", "label": "TEAM SYNC"}}
      ],
      "speech_bubble_text": "PLAN YOUR DAY!"
    }}
  ]
}}"""


def _compile_spatial_prompt(
    beat_blueprint: dict[str, Any],
    recurring_character: str,
    cast_characters: list[str],
    config: PipelineConfig,
) -> str:
    """Deterministically compile a structured beat blueprint into a rich, consistent Qwen-Image prompt."""
    palette = get_palette(config.banner_palette)
    style_suffix = config.style_suffix

    banner_title = str(beat_blueprint.get("banner_title") or "KEY CONCEPT").strip().upper().replace("'", "")
    setting_name = str(beat_blueprint.get("setting_name") or "bright modern illustrated workspace").strip()
    char_pose = str(
        beat_blueprint.get("character_pose")
        or "standing prominently in the left foreground, smiling and pointing toward the key visual diagram"
    ).strip()

    # Background world props (guarantee rich environment density)
    bg_props = [str(p).strip() for p in (beat_blueprint.get("background_props") or []) if str(p).strip()]
    if len(bg_props) < 4 and config.environment_mode != "whiteboard":
        bg_props.extend(["desk with laptop and notebook", "wall calendar", "potted plant", "bookshelf and desk lamp"])
    bg_props_text = ", ".join(bg_props[:7])

    # Foreground labelled objects
    fg_items_raw = beat_blueprint.get("foreground_objects") or []
    fg_phrases: list[str] = []
    for item in fg_items_raw[:6]:
        if isinstance(item, dict):
            obj = str(item.get("object") or "").strip()
            lbl = str(item.get("label") or "").strip().upper().replace("'", "")
            if obj and lbl:
                fg_phrases.append(f"{obj} with bold crisp label reading '{lbl}'")
            elif obj:
                fg_phrases.append(obj)
        elif str(item).strip():
            fg_phrases.append(str(item).strip())
    if not fg_phrases:
        fg_phrases = [
            f"illustrated diagram card with bold crisp label reading '{banner_title}'",
            "checklist clipboard with green checkmarks labelled 'KEY STEPS'",
            "progress bar chart labelled 'RESULTS'",
        ]
    fg_text = "; ".join(fg_phrases)

    # Mandatory non-empty speech bubble text
    bubble_txt = str(beat_blueprint.get("speech_bubble_text") or "").strip().upper().replace("'", "")
    if not bubble_txt or len(bubble_txt) < 2:
        bubble_txt = banner_title[:24]

    cast_clause = ""
    if cast_characters:
        cast_clause = f" In the right foreground, supporting colleague ({cast_characters[0]}) engaging with the scene."

    env_clause = (
        "Pure clean white whiteboard canvas background."
        if config.environment_mode == "whiteboard"
        else f"Richly detailed illustrated setting: {setting_name}, populated with recognizable everyday objects including {bg_props_text}."
    )

    # Natural lowercase descriptive prose — reserve UPPERCASE strictly for exact quoted text
    # to be rendered in the image (prevents prompt meta-headers like "SPEECH BUBBLE:" from leaking onto banners!).
    prompt = (
        f"Wide 16:9 richly detailed illustrated educational explainer scene. "
        f"On the left foreground, {recurring_character}, {char_pose}, clearly visible from the waist up with a friendly expressive face and consistent outfit. "
        f"Across the top, a {palette['prompt']} displaying only the exact text \"{banner_title}\" and no other words. "
        f"Beside the presenter, a clean white speech bubble with a bold black outline displaying only the exact text \"{bubble_txt}\". "
        f"Across the center and right foreground, arranged left to right with clean directional arrows: {fg_text}.{cast_clause} "
        f"Setting: {env_clause} "
        f"{style_suffix}."
    )
    # Strip any accidental rainbow wording
    prompt = re.sub(r"\brainbow\b", "cohesive brand-colored", prompt, flags=re.IGNORECASE)
    return prompt


def _extract_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in Ollama output: {raw[:300]}")
    return json.loads(raw[start : end + 1])


def _normalize_batch(
    raw_storyboard: dict[str, Any],
    batch_sentences: list[dict[str, Any]],
    fallback_character: str,
    config: PipelineConfig,
) -> tuple[str, list[dict[str, Any]]]:
    valid_indices = [int(s["index"]) for s in batch_sentences]
    valid_set = set(valid_indices)
    recurring = str(raw_storyboard.get("recurring_character") or fallback_character).strip() or fallback_character
    if config.character_description.strip():
        recurring = config.character_description.strip()

    used: set[int] = set()
    cleaned: list[dict[str, Any]] = []

    for b in raw_storyboard.get("beats") or []:
        idxs = sorted({int(i) for i in (b.get("sentence_indices") or []) if int(i) in valid_set and int(i) not in used})
        if not idxs:
            continue
        used.update(idxs)
        compiled_prompt = _compile_spatial_prompt(b, recurring, config.cast_characters, config)
        fg_objs = b.get("foreground_objects") or []
        elements_summary = [
            f"{x.get('object', '')} ({x.get('label', '')})" if isinstance(x, dict) else str(x)
            for x in fg_objs
        ]
        cleaned.append({
            "sentence_indices": idxs,
            "setting": str(b.get("setting_name") or config.environment_mode).strip(),
            "background_props": [str(p).strip() for p in (b.get("background_props") or []) if str(p).strip()],
            "banner_title": str(b.get("banner_title") or "KEY IDEA").strip().upper(),
            "speech_bubble_text": str(b.get("speech_bubble_text") or "").strip().upper(),
            "elements": elements_summary,
            "image_prompt": compiled_prompt,
        })

    missing = [i for i in valid_indices if i not in used]
    if missing:
        if cleaned:
            cleaned[-1]["sentence_indices"] = sorted(cleaned[-1]["sentence_indices"] + missing)
        else:
            fallback_bp = {
                "banner_title": "KEY OVERVIEW",
                "setting_name": "bright modern illustrated workspace",
                "background_props": ["desk with dual monitors", "wall calendar", "filing cabinet", "potted plant", "coffee mug"],
                "character_pose": "standing in the left foreground holding a clipboard and pointing at the board",
                "foreground_objects": [
                    {"object": "checklist board", "label": "KEY STEPS"},
                    {"object": "bar chart screen", "label": "RESULTS"},
                    {"object": "workflow arrows", "label": "ACTION PLAN"},
                ],
                "speech_bubble_text": "KEY TAKEAWAY!",
            }
            cleaned.append({
                "sentence_indices": missing,
                "setting": fallback_bp["setting_name"],
                "background_props": fallback_bp["background_props"],
                "banner_title": "KEY OVERVIEW",
                "speech_bubble_text": "KEY TAKEAWAY!",
                "elements": ["checklist board (KEY STEPS)", "bar chart screen (RESULTS)"],
                "image_prompt": _compile_spatial_prompt(fallback_bp, recurring, config.cast_characters, config),
            })

    cleaned.sort(key=lambda b: b["sentence_indices"][0])
    return recurring, cleaned


def unload_ollama(config: PipelineConfig) -> None:
    """Immediately unload the Ollama model from GPU VRAM (keep_alive=0)."""
    url = f"{config.ollama_url.rstrip('/')}/api/generate"
    try:
        r = requests.post(url, json={"model": config.ollama_model, "keep_alive": 0}, timeout=30)
        if r.ok:
            logger.info("Unloaded Ollama model '%s' from VRAM (keep_alive=0).", config.ollama_model)
        else:
            logger.warning("Ollama unload returned HTTP %s: %s", r.status_code, r.text[:200])
    except Exception as exc:
        logger.warning("Could not unload Ollama model: %s", exc)


def direct_storyboard(
    alignment: dict[str, Any],
    output_dir: Path,
    config: PipelineConfig,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Call Ollama in batches to build structured spatial blueprints, compile crisp prompts, then unload VRAM."""
    sentences = alignment.get("sentences") or []
    total_duration = float(alignment.get("total_duration") or 0.0)
    if not sentences:
        raise ValueError("Alignment contains no sentences to direct.")

    sent_by_idx = {int(s["index"]): s for s in sentences}
    batch_size = max(8, config.director_batch_sentences)
    batches = [sentences[i : i + batch_size] for i in range(0, len(sentences), batch_size)]

    system_prompt = _build_system_prompt(config)
    chat_url = f"{config.ollama_url.rstrip('/')}/api/chat"
    logger.info(
        "Calling Structured Visual Director (%s, env=%s, palette=%s) across %d batch(es) ...",
        config.ollama_model,
        config.environment_mode,
        config.banner_palette,
        len(batches),
    )

    recurring_character = (
        config.character_description.strip()
        or "confident Black South African woman facilitator in her 30s with neat braided updo, round glasses, wearing a tailored teal blazer over a white shirt"
    )

    all_raw_beats: list[dict[str, Any]] = []

    try:
        for b_idx, batch in enumerate(batches, start=1):
            lines = [
                f"[{s['index']}] ({s['start']:.2f}s - {s['end']:.2f}s, {s['duration']:.2f}s): {s['text']}"
                for s in batch
            ]
            user_prompt = (
                f"Batch {b_idx} of {len(batches)}.\n"
                f"Target beat length: {config.target_beat_min_sec:.0f}s to {config.target_beat_max_sec:.0f}s per beat.\n"
                f"Primary presenter: \"{recurring_character}\".\n"
                f"Use ONLY these exact sentence indices ({batch[0]['index']} to {batch[-1]['index']}):\n\n"
                + "\n".join(lines)
                + "\n\nReturn the structured spatial blueprint JSON for this batch now."
            )

            payload = {
                "model": config.ollama_model,
                "format": "json",
                "stream": False,
                "keep_alive": "2m" if b_idx < len(batches) else 0,
                "options": {
                    "temperature": 0.4,
                    "num_ctx": 8192,
                    "num_predict": 4096,
                },
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            logger.info("Directing batch %d/%d (sentences %d..%d) ...", b_idx, len(batches), batch[0]["index"], batch[-1]["index"])
            resp = requests.post(chat_url, json=payload, timeout=600)
            resp.raise_for_status()
            parsed = _extract_json(resp.json()["message"]["content"])
            found_char, batch_beats = _normalize_batch(parsed, batch, recurring_character, config)
            if b_idx == 1 and not config.character_description.strip() and found_char:
                recurring_character = found_char
            all_raw_beats.extend(batch_beats)
            if progress_cb:
                progress_cb(b_idx, len(batches), f"Directed batch {b_idx}/{len(batches)} ({len(all_raw_beats)} beats)")
    finally:
        if config.unload_ollama:
            unload_ollama(config)

    all_raw_beats.sort(key=lambda b: b["sentence_indices"][0])
    final_beats: list[dict[str, Any]] = []
    for idx, b in enumerate(all_raw_beats, start=1):
        s_idxs = b["sentence_indices"]
        start_t = float(sent_by_idx[s_idxs[0]]["start"])
        end_t = float(sent_by_idx[s_idxs[-1]]["end"])
        narration = " ".join(sent_by_idx[i]["text"] for i in s_idxs).strip()
        sentence_timings = [
            {
                "text": sent_by_idx[i]["text"],
                "rel_start": round(max(0.0, float(sent_by_idx[i]["start"]) - start_t), 3),
                "rel_end": round(max(0.1, float(sent_by_idx[i]["end"]) - start_t), 3),
                "duration": round(max(0.3, float(sent_by_idx[i]["duration"])), 3),
            }
            for i in s_idxs
        ]
        final_beats.append({
            "beat_id": idx,
            "scene_filename": f"scene_{idx:02d}.png",
            "sentence_indices": s_idxs,
            "start": round(start_t, 3),
            "end": round(end_t, 3),
            "duration": round(max(1.0, end_t - start_t), 3),
            "narration_text": narration,
            "sentence_timings": sentence_timings,
            "setting": b["setting"],
            "background_props": b["background_props"],
            "banner_title": b["banner_title"],
            "speech_bubble_text": b["speech_bubble_text"],
            "elements": b["elements"],
            "image_prompt": b["image_prompt"],
        })

    if final_beats:
        final_beats[0]["start"] = 0.0
        for i in range(len(final_beats) - 1):
            final_beats[i]["end"] = final_beats[i + 1]["start"]
            final_beats[i]["duration"] = round(max(1.0, final_beats[i]["end"] - final_beats[i]["start"]), 3)
        final_beats[-1]["end"] = round(max(final_beats[-1]["end"], total_duration), 3)
        final_beats[-1]["duration"] = round(max(1.0, final_beats[-1]["end"] - final_beats[-1]["start"]), 3)

    storyboard = {
        "recurring_character": recurring_character,
        "banner_palette": config.banner_palette,
        "environment_mode": config.environment_mode,
        "total_duration": round(total_duration, 3),
        "beat_count": len(final_beats),
        "beats": final_beats,
    }
    storyboard_path = output_dir / "storyboard.json"
    storyboard_path.write_text(json.dumps(storyboard, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "Storyboard saved to %s (%d beats covering %.2fs).",
        storyboard_path,
        storyboard["beat_count"],
        storyboard["total_duration"],
    )
    return storyboard

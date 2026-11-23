"""Stage 5: Vision-Guided Audio-Synced Sequential Whiteboard Animator.

Uses gemma3:12b (Vision) on Ollama to literally LOOK at each generated scene_XX.png
with numbered bounding boxes (Set-of-Mark) and match EVERY visual object to the EXACT
Whisper spoken phrase timestamp (rel_start -> rel_end).

Then renders each scene with:
  1. Exact Whisper timestamp locking: each visual object is drawn during the exact
     seconds the narrator is talking about it!
  2. Element-complete two-pass drawing: finishes 100% of one object (ink outlines ->
     diagonal watercolor fill) before smoothly gliding to the next object.
  3. Zero pixel squares: continuous anti-aliased vector contour strokes (LINE_AA).
  4. Works on both pure whiteboards and rich illustrated environments (office/outdoor).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
import requests

from .config import PipelineConfig

logger = logging.getLogger("pipeline.stage5_animate")

_IMAGES_DIR = Path(__file__).resolve().parent.parent / "kivy" / "data" / "images"
_HAND_PATH = _IMAGES_DIR / "drawing-hand.png"
_HAND_MASK_PATH = _IMAGES_DIR / "hand-mask.png"


def _resize_with_white_padding(img: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    h, w = img.shape[:2]
    scale = min(target_w / float(w), target_h / float(h))
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    canvas = np.full((target_h, target_w, 3), 255, dtype=np.uint8)
    y0 = (target_h - nh) // 2
    x0 = (target_w - nw) // 2
    canvas[y0 : y0 + nh, x0 : x0 + nw] = resized
    return canvas


def _load_hand_sprite(target_h: int) -> tuple[np.ndarray, np.ndarray] | None:
    if not _HAND_PATH.exists() or not _HAND_MASK_PATH.exists():
        return None
    hand = cv2.imread(str(_HAND_PATH))
    mask = cv2.imread(str(_HAND_MASK_PATH), cv2.IMREAD_GRAYSCALE)
    if hand is None or mask is None:
        return None

    ys, xs = np.where(mask > 127)
    if len(xs) == 0:
        return None
    x1, x2 = int(xs.min()), int(xs.max()) + 1
    y1, y2 = int(ys.min()), int(ys.max()) + 1
    hand = hand[y1:y2, x1:x2]
    mask = mask[y1:y2, x1:x2]

    desired_h = max(120, int(target_h * 0.42))
    scale = desired_h / float(hand.shape[0])
    new_w = max(1, int(round(hand.shape[1] * scale)))
    hand = cv2.resize(hand, (new_w, desired_h), interpolation=cv2.INTER_AREA)
    mask = cv2.resize(mask, (new_w, desired_h), interpolation=cv2.INTER_AREA)

    alpha = (mask.astype(np.float32) / 255.0)[..., None]
    inv_alpha = 1.0 - alpha
    hand_premult = hand.astype(np.float32) * alpha
    return hand_premult, inv_alpha


def _overlay_hand(frame: np.ndarray, sprite: tuple[np.ndarray, np.ndarray] | None, tip_x: int, tip_y: int) -> None:
    if sprite is None:
        return
    hand_premult, inv_alpha = sprite
    fh, fw = frame.shape[:2]
    hh, hw = hand_premult.shape[:2]

    x0 = max(0, min(fw - 1, tip_x))
    y0 = max(0, min(fh - 1, tip_y))
    crop_w = min(hw, fw - x0)
    crop_h = min(hh, fh - y0)
    if crop_w <= 0 or crop_h <= 0:
        return

    roi = frame[y0 : y0 + crop_h, x0 : x0 + crop_w].astype(np.float32)
    blended = roi * inv_alpha[:crop_h, :crop_w] + hand_premult[:crop_h, :crop_w]
    frame[y0 : y0 + crop_h, x0 : x0 + crop_w] = np.clip(blended, 0, 255).astype(np.uint8)


def _extract_ink_and_color_masks(img_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    adapt = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 10)
    dark = (gray < 120).astype(np.uint8) * 255
    edges = cv2.Canny(gray, 60, 160)
    ink_mask = cv2.bitwise_or(dark, cv2.bitwise_and(adapt, (gray < 185).astype(np.uint8) * 255))
    ink_mask = cv2.bitwise_or(ink_mask, edges)

    non_white = ((val < 245) | (sat > 16)).astype(np.uint8) * 255
    color_mask = cv2.bitwise_and(non_white, cv2.bitwise_not(ink_mask))
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_OPEN, k3)
    return ink_mask, color_mask


def _segment_scene_objects(img_bgr: np.ndarray, ink_mask: np.ndarray) -> list[dict[str, Any]]:
    """Segment an illustration into WHOLE, UNCUT semantic objects (NEVER slicing a person/object with a grid!).

    Uses bold-ink + strong-color connected components with solid contour flood-filling,
    parent-child containment merging (so text inside banners/speech-bubbles/flipcharts stays
    inside its parent object), and nearby label merging.
    Returns list of dicts: {box_id, bbox: (x1,y1,x2,y2), is_banner, mask}.
    """
    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]

    # 1. Whole-image foreground mask (bold ink, dark neutral greys like trousers/keyboards, + strong foreground colors)
    bold_ink = (gray < 135).astype(np.uint8) * 255
    strong_color = ((sat > 55) & (gray < 218)).astype(np.uint8) * 255
    fg = cv2.bitwise_or(bold_ink, strong_color)

    def _extract_components(fg_src: np.ndarray, close_k: int, dil_k: int) -> list[dict[str, Any]]:
        k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_k, close_k))
        closed = cv2.morphologyEx(fg_src, cv2.MORPH_CLOSE, k_close)
        k_dil = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dil_k, dil_k))
        grouped = cv2.dilate(closed, k_dil, iterations=1)
        num, labels, stats, _cents = cv2.connectedComponentsWithStats(grouped, connectivity=8)
        min_area = int(h * w * 0.0004)  # keep small arrows/numbers so they merge into their parent object!
        out: list[dict[str, Any]] = []
        for i in range(1, num):
            if int(stats[i, cv2.CC_STAT_AREA]) < min_area:
                continue
            x, y = int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP])
            bw, bh = int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT])
            raw_m = (labels == i).astype(np.uint8) * 255
            # Flood-fill external contours so 100% of each person/icon/speech-bubble interior is solid!
            cnts, _ = cv2.findContours(raw_m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            solid_m = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(solid_m, cnts, -1, 255, thickness=cv2.FILLED)
            out.append({"bbox": [x, y, x + bw, y + bh], "mask": solid_m, "area": int(np.count_nonzero(solid_m))})
        return out

    objs = _extract_components(fg, close_k=19, dil_k=13)

    # If a horizontal desk/floor edge glued all body objects into 1 giant blob (>82% width & >60% height),
    # re-segment with a tighter kernel while temporarily ignoring the bottom 8% desk/floor bridge line
    # so standing characters/icons separate cleanly into WHOLE uncut vertical objects!
    giant_body = [
        o for o in objs
        if (o["bbox"][2] - o["bbox"][0]) > w * 0.82
        and (o["bbox"][3] - o["bbox"][1]) > h * 0.58
        and o["bbox"][1] > h * 0.15
    ]
    if giant_body:
        fg_nobridge = fg.copy()
        fg_nobridge[int(h * 0.90) :, :] = 0
        tight_objs = _extract_components(fg_nobridge, close_k=11, dil_k=7)
        if len(tight_objs) > len(objs):
            # Re-attach bottom 10% desk pixels to whichever object sits directly above them
            objs = tight_objs
            for o in objs:
                if o["bbox"][3] >= int(h * 0.88):
                    o["bbox"][3] = h
                    o["mask"][int(h * 0.88) :, o["bbox"][0] : o["bbox"][2]] = 255

    # 2. Merge any child object that sits >= 65% inside a larger parent object (e.g. text inside speech bubble/flipchart)
    objs.sort(key=lambda o: o["area"], reverse=True)
    kept: list[dict[str, Any]] = []
    for o in objs:
        x1, y1, x2, y2 = o["bbox"]
        merged = False
        for p in kept:
            px1, py1, px2, py2 = p["bbox"]
            ix1, iy1 = max(x1, px1), max(y1, py1)
            ix2, iy2 = min(x2, px2), min(y2, py2)
            inter_bb = max(0, ix2 - ix1) * max(0, iy2 - iy1)
            own_bb = max(1, (x2 - x1) * (y2 - y1))
            if inter_bb / own_bb >= 0.65:
                p["mask"] = cv2.bitwise_or(p["mask"], o["mask"])
                p["bbox"] = [min(px1, x1), min(py1, y1), max(px2, x2), max(py2, y2)]
                p["area"] = int(np.count_nonzero(p["mask"]))
                merged = True
                break
        if not merged:
            kept.append(o)

    # 3. Merge small nearby text labels/words directly underneath or beside their parent icon/object
    changed = True
    while changed:
        changed = False
        for i in range(len(kept)):
            a = kept[i]
            ax1, ay1, ax2, ay2 = a["bbox"]
            if (ay2 - ay1) > h * 0.14:
                continue
            best_j = -1
            best_dist = 1e9
            for j in range(len(kept)):
                if i == j:
                    continue
                b = kept[j]
                bx1, by1, bx2, by2 = b["bbox"]
                if by1 < h * 0.22 and (bx2 - bx1) > w * 0.45:
                    continue  # never glue body text into the top banner
                dx = max(0, max(ax1 - bx2, bx1 - ax2))
                dy = max(0, max(ay1 - by2, by1 - ay2))
                dist = (dx * dx + dy * dy) ** 0.5
                if dist < h * 0.085 and dist < best_dist:
                    best_dist = dist
                    best_j = j
            if best_j >= 0:
                b = kept[best_j]
                bx1, by1, bx2, by2 = b["bbox"]
                b["mask"] = cv2.bitwise_or(b["mask"], a["mask"])
                b["bbox"] = [min(ax1, bx1), min(ay1, by1), max(ax2, bx2), max(ay2, by2)]
                b["area"] = int(np.count_nonzero(b["mask"]))
                kept.pop(i)
                changed = True
                break

    # Cap over-fragmented scenes at 9 clean objects by merging smallest non-banner into nearest non-banner
    while len(kept) > 9:
        non_banners = [i for i, o in enumerate(kept) if not (o["bbox"][1] < h * 0.22 and (o["bbox"][2] - o["bbox"][0]) > w * 0.45)]
        if len(non_banners) < 2:
            break
        sm_i = min(non_banners, key=lambda i: kept[i]["area"])
        a = kept.pop(sm_i)
        ax = (a["bbox"][0] + a["bbox"][2]) * 0.5
        ay = (a["bbox"][1] + a["bbox"][3]) * 0.5
        cand = [i for i, o in enumerate(kept) if not (o["bbox"][1] < h * 0.22 and (o["bbox"][2] - o["bbox"][0]) > w * 0.45)]
        if not cand:
            kept.append(a)
            break
        best_j = min(cand, key=lambda i: ((kept[i]["bbox"][0] + kept[i]["bbox"][2]) * 0.5 - ax) ** 2 + ((kept[i]["bbox"][1] + kept[i]["bbox"][3]) * 0.5 - ay) ** 2)
        b = kept[best_j]
        b["mask"] = cv2.bitwise_or(b["mask"], a["mask"])
        b["bbox"] = [min(a["bbox"][0], b["bbox"][0]), min(a["bbox"][1], b["bbox"][1]), max(a["bbox"][2], b["bbox"][2]), max(a["bbox"][3], b["bbox"][3])]
        b["area"] = int(np.count_nonzero(b["mask"]))

    if not kept:
        kept.append({"bbox": [0, 0, w, h], "mask": np.full((h, w), 255, dtype=np.uint8), "area": h * w})

    # Tag top banner and sort: Banner first, then left-to-right
    for o in kept:
        x1, y1, x2, y2 = o["bbox"]
        o["is_banner"] = bool(y1 < h * 0.22 and (x2 - x1) > w * 0.45 and (y2 - y1) < h * 0.35)
    kept.sort(key=lambda o: (0 if o["is_banner"] else 1, o["bbox"][0]))

    objects: list[dict[str, Any]] = []
    for idx, o in enumerate(kept, start=1):
        objects.append({
            "box_id": idx,
            "is_banner": o["is_banner"],
            "bbox": tuple(o["bbox"]),
            "mask": o["mask"],
        })
    return objects


def _extract_spoken_phrases(
    beat: dict[str, Any],
    alignment: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build fine-grained 2.5s-4.5s spoken phrase cues from Whisper word timestamps inside this beat."""
    beat_start = float(beat["start"])
    beat_dur = float(beat["duration"])

    # Gather exact Whisper words for this beat's sentence_indices if alignment.json is available
    beat_words: list[dict[str, Any]] = []
    if alignment and alignment.get("sentences"):
        sent_by_idx = {int(s["index"]): s for s in alignment["sentences"]}
        for si in beat.get("sentence_indices") or []:
            s = sent_by_idx.get(int(si))
            if s and s.get("words"):
                beat_words.extend(s["words"])

    if not beat_words:
        # Fallback to sentence_timings or single beat cue
        st = beat.get("sentence_timings") or []
        if st:
            return [
                {"rel_start": float(x["rel_start"]), "rel_end": float(x["rel_end"]), "text": x["text"]}
                for x in st
            ]
        return [{"rel_start": 0.0, "rel_end": beat_dur, "text": beat.get("narration_text", "")}]

    phrases: list[dict[str, Any]] = []
    buf: list[dict[str, Any]] = []
    punct_re = re.compile(r"[,.;:!?][\"')\]]*$")

    for i, w in enumerate(beat_words):
        buf.append(w)
        p_start = max(0.0, float(buf[0]["start"]) - beat_start)
        p_end = min(beat_dur, float(buf[-1]["end"]) - beat_start)
        p_dur = p_end - p_start
        next_gap = 0.0
        if i + 1 < len(beat_words):
            next_gap = float(beat_words[i + 1]["start"]) - float(w["end"])

        should_cut = (
            (p_dur >= 2.2 and (punct_re.search(w["word"].strip()) or next_gap >= 0.25))
            or p_dur >= 4.2
        )
        if should_cut:
            txt = " ".join(x["word"].strip() for x in buf)
            phrases.append({"rel_start": round(p_start, 2), "rel_end": round(p_end, 2), "text": txt})
            buf = []

    if buf:
        p_start = max(0.0, float(buf[0]["start"]) - beat_start)
        p_end = min(beat_dur, float(buf[-1]["end"]) - beat_start)
        txt = " ".join(x["word"].strip() for x in buf)
        phrases.append({"rel_start": round(p_start, 2), "rel_end": round(p_end, 2), "text": txt})

    if phrases:
        phrases[0]["rel_start"] = 0.0
        phrases[-1]["rel_end"] = round(beat_dur, 2)
    return phrases


def _make_som_jpeg_b64(img_bgr: np.ndarray, objects: list[dict[str, Any]]) -> str:
    """Create a 960x540 Set-of-Mark JPEG with crisp numbered red boxes [1]..[K] for gemma3:12b Vision."""
    vis = img_bgr.copy()
    for obj in objects:
        x1, y1, x2, y2 = obj["bbox"]
        bid = obj["box_id"]
        cv2.rectangle(vis, (x1 + 3, y1 + 3), (x2 - 3, y2 - 3), (0, 0, 230), 5)
        label = str(bid)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 1.8, 4)
        bx = max(6, min(vis.shape[1] - tw - 24, x1 + 8))
        by = max(th + 16, min(vis.shape[0] - 10, y1 + th + 16))
        cv2.rectangle(vis, (bx - 8, by - th - 10), (bx + tw + 12, by + 10), (0, 0, 230), -1)
        cv2.putText(vis, label, (bx, by), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (255, 255, 255), 4, cv2.LINE_AA)

    small = cv2.resize(vis, (960, 540), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise RuntimeError("Failed to encode Set-of-Mark JPEG")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _plan_vision_audio_sync(
    storyboard: dict[str, Any],
    alignment: dict[str, Any] | None,
    output_dir: Path,
    config: PipelineConfig,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> dict[int, list[dict[str, Any]]]:
    """Use gemma3:12b Vision on Ollama to map each visual box [1..K] to its EXACT spoken Whisper timestamp."""
    scenes_dir = output_dir / "scenes"
    beats = storyboard["beats"]
    cue_map: dict[int, list[dict[str, Any]]] = {}

    if not config.enable_vision_sync:
        return cue_map

    chat_url = f"{config.ollama_url.rstrip('/')}/api/chat"
    logger.info("Running Vision-Guided Audio Sync (%s) across %d scene(s) ...", config.vision_sync_model, len(beats))

    try:
        for idx, beat in enumerate(beats, start=1):
            beat_id = int(beat["beat_id"])
            scene_path = scenes_dir / f"scene_{beat_id:02d}.png"
            if not scene_path.exists():
                continue

            img_raw = cv2.imread(str(scene_path))
            if img_raw is None:
                continue
            img = _resize_with_white_padding(img_raw, config.video_width, config.video_height)
            ink_mask, _ = _extract_ink_and_color_masks(img)
            objects = _segment_scene_objects(img, ink_mask)
            phrases = _extract_spoken_phrases(beat, alignment)
            beat_dur = float(beat["duration"])

            if len(objects) <= 1:
                cue_map[beat_id] = [{"box_id": 1, "start": 0.0, "end": max(0.8, beat_dur - 0.8)}]
                continue

            som_b64 = _make_som_jpeg_b64(img, objects)
            phrase_lines = [
                f"  - [{p['rel_start']:.2f}s to {p['rel_end']:.2f}s]: \"{p['text']}\""
                for p in phrases
            ]
            box_ids = [o["box_id"] for o in objects]
            banner_ids = [o["box_id"] for o in objects if o["is_banner"]]

            prompt = (
                f"You are synchronizing an animated drawing hand to a voiceover.\n"
                f"This illustration has {len(objects)} red numbered boxes: {box_ids}.\n"
                f"{f'Box {banner_ids[0]} is the top title banner.' if banner_ids else ''}\n"
                f"Total scene duration: {beat_dur:.2f}s.\n\n"
                f"Spoken narration phrases (exact Whisper timestamps):\n"
                + "\n".join(phrase_lines)
                + "\n\n"
                f"LOOK CAREFULLY at the text labels, icons, and characters inside EACH red numbered box.\n"
                f"Assign EVERY box_id in {box_ids} an exact [start, end] time window (in seconds, within 0.0 to {max(1.0, beat_dur - 0.7):.2f}) "
                f"so the drawing hand draws each box AT THE EXACT MOMENT the narrator mentions that concept!\n"
                f"Rules:\n"
                f"1. Draw the top banner box first quickly at 0.0s (e.g. 0.0 to 1.4s).\n"
                f"2. Each remaining box MUST appear in the exact order its concept/label is spoken in the narration.\n"
                f"3. Every single box_id in {box_ids} MUST appear ONCE in 'cues', in strictly ascending non-overlapping time order.\n"
                f"Return ONLY valid JSON: {{\"cues\": [{{\"box_id\": 1, \"start\": 0.0, \"end\": 1.4, \"reason\": \"banner\"}}]}}"
            )

            try:
                r = requests.post(
                    chat_url,
                    json={
                        "model": config.vision_sync_model,
                        "format": "json",
                        "stream": False,
                        "options": {"temperature": 0.1, "num_ctx": 4096},
                        "messages": [{"role": "user", "content": prompt, "images": [som_b64]}],
                    },
                    timeout=180,
                )
                r.raise_for_status()
                raw_txt = r.json()["message"]["content"]
                start_i = raw_txt.find("{")
                end_i = raw_txt.rfind("}")
                parsed = json.loads(raw_txt[start_i : end_i + 1])
                raw_cues = parsed.get("cues") or []
            except Exception as exc:
                logger.warning("Vision sync fallback for scene_%02d: %s", beat_id, exc)
                raw_cues = []

            # Sanitize & guarantee every box_id 1..K has a valid, non-overlapping time window
            valid_set = set(box_ids)
            seen: set[int] = set()
            clean_cues: list[dict[str, Any]] = []
            max_draw_end = max(1.0, beat_dur - min(config.min_hold_sec, beat_dur * 0.12))

            for c in raw_cues:
                bid = int(c.get("box_id", -1))
                if bid not in valid_set or bid in seen:
                    continue
                st = max(0.0, min(max_draw_end - 0.3, float(c.get("start", 0.0))))
                en = max(st + 0.35, min(max_draw_end, float(c.get("end", st + 1.5))))
                seen.add(bid)
                clean_cues.append({
                    "box_id": bid,
                    "start": round(st, 3),
                    "end": round(en, 3),
                    "reason": str(c.get("reason", ""))[:80],
                })

            # Append any box not listed by Vision
            for bid in box_ids:
                if bid not in seen:
                    prev_end = clean_cues[-1]["end"] if clean_cues else 0.0
                    clean_cues.append({
                        "box_id": bid,
                        "start": round(prev_end, 3),
                        "end": round(max_draw_end, 3),
                        "reason": "auto-included",
                    })

            clean_cues.sort(key=lambda x: x["start"])
            # Make windows strictly non-overlapping and spanning [0.0, max_draw_end]
            if clean_cues:
                clean_cues[0]["start"] = 0.0
                for j in range(len(clean_cues) - 1):
                    if clean_cues[j]["end"] > clean_cues[j + 1]["start"]:
                        mid = round((clean_cues[j]["end"] + clean_cues[j + 1]["start"]) / 2.0, 3)
                        clean_cues[j]["end"] = max(clean_cues[j]["start"] + 0.3, mid)
                        clean_cues[j + 1]["start"] = clean_cues[j]["end"]
                clean_cues[-1]["end"] = round(max(clean_cues[-1]["start"] + 0.35, max_draw_end), 3)

            cue_map[beat_id] = clean_cues
            beat["audio_sync_cues"] = clean_cues
            logger.info("Vision-synced scene_%02d.png (%d/%d): %s", beat_id, idx, len(beats), [(c["box_id"], c["start"], c["end"]) for c in clean_cues])
            if progress_cb:
                progress_cb(idx, len(beats), f"Vision audio-synced scene_{beat_id:02d} ({idx}/{len(beats)})")
    finally:
        # Unload gemma3:12b from GPU VRAM immediately
        try:
            requests.post(
                f"{config.ollama_url.rstrip('/')}/api/generate",
                json={"model": config.vision_sync_model, "keep_alive": 0},
                timeout=30,
            )
            logger.info("Unloaded Vision model '%s' from VRAM.", config.vision_sync_model)
        except Exception:
            pass

    (output_dir / "storyboard.json").write_text(json.dumps(storyboard, indent=2, ensure_ascii=False), encoding="utf-8")
    return cue_map


def _build_ink_polylines_for_element(ink_mask: np.ndarray, elem_mask: np.ndarray) -> list[np.ndarray]:
    region = cv2.bitwise_and(ink_mask, elem_mask)
    contours, _ = cv2.findContours(region, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return []
    valid = [c.reshape(-1, 2) for c in contours if len(c) >= 6]
    if not valid:
        return []

    valid.sort(key=lambda c: len(c), reverse=True)
    ordered: list[np.ndarray] = [valid.pop(0)]
    cur_pt = ordered[0][-1].astype(np.float32)

    while valid:
        best_i = 0
        best_d = 1e18
        reverse_best = False
        for i, c in enumerate(valid):
            d_start = float(np.sum((c[0].astype(np.float32) - cur_pt) ** 2))
            d_end = float(np.sum((c[-1].astype(np.float32) - cur_pt) ** 2))
            if d_start < best_d:
                best_d = d_start
                best_i = i
                reverse_best = False
            if d_end < best_d:
                best_d = d_end
                best_i = i
                reverse_best = True
        nxt = valid.pop(best_i)
        if reverse_best:
            nxt = nxt[::-1]
        ordered.append(nxt)
        cur_pt = nxt[-1].astype(np.float32)

    return ordered


def _build_watercolor_sweeps_for_element(color_mask: np.ndarray, elem_mask: np.ndarray, step: int = 16) -> list[np.ndarray]:
    region = cv2.bitwise_and(color_mask, elem_mask)
    ys, xs = np.where(region > 0)
    if len(xs) < 25:
        return []

    x_min, x_max = int(xs.min()), int(xs.max())
    y_min, y_max = int(ys.min()), int(ys.max())
    bw = x_max - x_min + 1
    bh = y_max - y_min + 1

    strokes: list[np.ndarray] = []
    flip = False
    for d in range(0, bw + bh, step):
        x_start = max(x_min, x_min + d - bh + 1)
        x_end = min(x_max, x_min + d)
        if x_end < x_start:
            continue
        xs_line = np.arange(x_start, x_end + 1, 2, dtype=np.int32)
        ys_line = (x_min + y_min + d) - xs_line
        valid = (ys_line >= y_min) & (ys_line <= y_max)
        xs_line = xs_line[valid]
        ys_line = ys_line[valid]
        if len(xs_line) == 0:
            continue
        hits = region[ys_line, xs_line] > 0
        if not np.any(hits):
            continue
        pts = np.stack([xs_line[hits], ys_line[hits]], axis=1)
        if flip:
            pts = pts[::-1]
        flip = not flip
        strokes.append(pts)

    return strokes


def _flatten_strokes(polylines: list[np.ndarray], subsample: int = 2) -> list[tuple[int, int, bool]]:
    steps: list[tuple[int, int, bool]] = []
    for poly in polylines:
        if subsample > 1 and len(poly) > subsample:
            pts = poly[::subsample]
            if not np.array_equal(pts[-1], poly[-1]):
                pts = np.vstack([pts, poly[-1:]])
        else:
            pts = poly
        for i, (px, py) in enumerate(pts):
            steps.append((int(px), int(py), i == 0))
    return steps


def _render_single_beat_worker(args: tuple[str, str, float, list[dict[str, Any]], dict[str, Any]]) -> str:
    """Render one clip locking EVERY visual object strictly to its Whisper/Vision [start, end] window."""
    image_path_str, clip_path_str, target_duration_sec, cues, cfg = args
    image_path = Path(image_path_str)
    clip_path = Path(clip_path_str)

    img_raw = cv2.imread(str(image_path))
    if img_raw is None:
        raise FileNotFoundError(f"Could not read scene image: {image_path}")

    w = int(cfg["video_width"])
    h = int(cfg["video_height"])
    fps = int(cfg["fps"])
    draw_hand = bool(cfg["draw_hand"])
    end_color = bool(cfg["end_color"])
    min_hold_sec = float(cfg["min_hold_sec"])

    img = _resize_with_white_padding(img_raw, w, h)
    hand_sprite = _load_hand_sprite(h) if draw_hand else None

    ink_mask, color_mask = _extract_ink_and_color_masks(img)
    objects = _segment_scene_objects(img, ink_mask)
    obj_by_id = {o["box_id"]: o for o in objects}

    ink_canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    ink_canvas[ink_mask > 0] = img[ink_mask > 0]

    total_frames = max(fps, int(round(target_duration_sec * fps)))
    max_draw_end = max(1.0, target_duration_sec - min(min_hold_sec, target_duration_sec * 0.12))

    # Build ordered cue list (use Vision cues if present; otherwise sequential fallback)
    if not cues:
        step_sec = max_draw_end / float(max(1, len(objects)))
        cues = [
            {"box_id": o["box_id"], "start": i * step_sec, "end": (i + 1) * step_sec}
            for i, o in enumerate(objects)
        ]

    # Prepare per-cue stroke plans with exact start_frame and end_frame
    scheduled: list[dict[str, Any]] = []
    for c in cues:
        obj = obj_by_id.get(int(c["box_id"]))
        if not obj:
            continue
        elem_mask = obj["mask"]
        ink_steps = _flatten_strokes(_build_ink_polylines_for_element(ink_mask, elem_mask), subsample=2)
        color_steps = _flatten_strokes(_build_watercolor_sweeps_for_element(color_mask, elem_mask, step=16), subsample=2) if end_color else []
        if not ink_steps and not color_steps:
            continue
        sf = max(0, min(total_frames - 2, int(round(float(c["start"]) * fps))))
        ef = max(sf + 2, min(total_frames - 1, int(round(float(c["end"]) * fps))))
        scheduled.append({
            "mask": elem_mask,
            "ink_steps": ink_steps,
            "color_steps": color_steps,
            "start_frame": sf,
            "end_frame": ef,
        })

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(clip_path), fourcc, fps, (w, h))

    ink_reveal = np.zeros((h, w), dtype=np.uint8)
    color_reveal = np.zeros((h, w), dtype=np.uint8)
    white_bg = np.full((h, w, 3), 255, dtype=np.uint8)

    ink_brush_r = max(4, int(round(min(w, h) * 0.006)))
    fill_brush_r = max(14, int(round(min(w, h) * 0.018)))

    last_pt = (w // 2, h // 4)
    smooth_x: float | None = None
    smooth_y: float | None = None
    cur_frame = 0

    def _compose_frame(hx: int, hy: int, show_hand: bool = True) -> np.ndarray:
        frame = np.where((ink_reveal > 0)[..., None], ink_canvas, white_bg)
        frame = np.where((color_reveal > 0)[..., None], img, frame)
        if show_hand:
            _overlay_hand(frame, hand_sprite, hx, hy)
        return frame

    def _track_hand(px: int, py: int) -> tuple[int, int]:
        nonlocal smooth_x, smooth_y
        if smooth_x is None or smooth_y is None:
            smooth_x, smooth_y = float(px), float(py)
        else:
            smooth_x = 0.55 * px + 0.45 * smooth_x
            smooth_y = 0.55 * py + 0.45 * smooth_y
        return int(round(smooth_x)), int(round(smooth_y))

    for idx_s, item in enumerate(scheduled):
        sf = item["start_frame"]
        ef = item["end_frame"]
        elem_mask = item["mask"]
        ink_steps = item["ink_steps"]
        color_steps = item["color_steps"]
        target_start = (ink_steps[0][0], ink_steps[0][1]) if ink_steps else (color_steps[0][0], color_steps[0][1])

        # If there is a spoken pause before this element starts, hold calmly & glide into position right on cue
        if sf > cur_frame:
            gap = sf - cur_frame
            glide_n = min(6, gap)
            hold_n = gap - glide_n
            for _ in range(hold_n):
                writer.write(_compose_frame(int(smooth_x or last_pt[0]), int(smooth_y or last_pt[1]), show_hand=False))
                cur_frame += 1
            sx, sy = (smooth_x or last_pt[0]), (smooth_y or last_pt[1])
            for g in range(1, glide_n + 1):
                t = g / float(glide_n)
                t_e = t * t * (3.0 - 2.0 * t)
                gx = int(round(sx + (target_start[0] - sx) * t_e))
                gy = int(round(sy + (target_start[1] - sy) * t_e))
                smooth_x, smooth_y = float(gx), float(gy)
                writer.write(_compose_frame(gx, gy, show_hand=True))
                cur_frame += 1
        elif idx_s > 0:
            # Brief 4-frame smooth glide inside the start of this cue
            glide_n = min(4, max(1, (ef - cur_frame) // 4))
            sx, sy = (smooth_x or last_pt[0]), (smooth_y or last_pt[1])
            for g in range(1, glide_n + 1):
                t = g / float(glide_n)
                t_e = t * t * (3.0 - 2.0 * t)
                gx = int(round(sx + (target_start[0] - sx) * t_e))
                gy = int(round(sy + (target_start[1] - sy) * t_e))
                smooth_x, smooth_y = float(gx), float(gy)
                writer.write(_compose_frame(gx, gy, show_hand=True))
                cur_frame += 1

        e_frames = max(2, ef - cur_frame)
        if end_color and color_steps and ink_steps:
            p1_frames = max(1, int(round(e_frames * 0.65)))
            p2_frames = max(1, e_frames - p1_frames)
        elif ink_steps:
            p1_frames = e_frames
            p2_frames = 0
        else:
            p1_frames = 0
            p2_frames = e_frames

        # Pass 1 (ink outlines for THIS spoken object — strictly clipped to elem_mask so neighbors never bleed!)
        elem_bool = elem_mask > 0
        elem_ink_draw = np.zeros((h, w), dtype=np.uint8)
        n1 = len(ink_steps)
        prev_idx = 0
        for f in range(p1_frames):
            cur_idx = int(round(((f + 1) / float(p1_frames)) * n1))
            prev_pt: tuple[int, int] | None = None
            for idx in range(prev_idx, cur_idx):
                px, py, is_new = ink_steps[idx]
                if is_new or prev_pt is None:
                    cv2.circle(elem_ink_draw, (px, py), ink_brush_r, 255, -1, lineType=cv2.LINE_AA)
                else:
                    cv2.line(elem_ink_draw, prev_pt, (px, py), 255, ink_brush_r * 2, lineType=cv2.LINE_AA)
                prev_pt = (px, py)
                last_pt = (px, py)
            prev_idx = cur_idx
            ink_reveal[elem_bool & (elem_ink_draw > 0)] = 255
            hx, hy = _track_hand(last_pt[0], last_pt[1])
            writer.write(_compose_frame(hx, hy, show_hand=True))
            cur_frame += 1

        ink_reveal[elem_bool] = 255

        # Pass 2 (diagonal watercolor fill for THIS spoken object — strictly clipped to elem_mask!)
        elem_color_draw = np.zeros((h, w), dtype=np.uint8)
        n2 = len(color_steps)
        prev_idx = 0
        for f in range(p2_frames):
            cur_idx = int(round(((f + 1) / float(p2_frames)) * n2))
            prev_pt = None
            for idx in range(prev_idx, cur_idx):
                px, py, is_new = color_steps[idx]
                if is_new or prev_pt is None:
                    cv2.circle(elem_color_draw, (px, py), fill_brush_r, 255, -1, lineType=cv2.LINE_AA)
                else:
                    cv2.line(elem_color_draw, prev_pt, (px, py), 255, fill_brush_r * 2, lineType=cv2.LINE_AA)
                prev_pt = (px, py)
                last_pt = (px, py)
            prev_idx = cur_idx
            color_reveal[elem_bool & (elem_color_draw > 0)] = 255
            hx, hy = _track_hand(last_pt[0], last_pt[1])
            writer.write(_compose_frame(hx, hy, show_hand=True))
            cur_frame += 1

        if end_color:
            color_reveal[elem_bool] = 255

    # Smoothly fade in any soft illustrated environment backdrop (walls/windows) behind finished foreground objects
    fg_finished = _compose_frame(int(last_pt[0]), int(last_pt[1]), show_hand=False)
    fade_frames = min(8, max(0, total_frames - cur_frame - 2))
    for k_f in range(1, fade_frames + 1):
        alpha = k_f / float(fade_frames)
        blended = cv2.addWeighted(img, alpha, fg_finished, 1.0 - alpha, 0.0)
        writer.write(blended)
        cur_frame += 1

    # Final clean hold for remaining frames up to exact Whisper duration
    while cur_frame < total_frames:
        writer.write(img)
        cur_frame += 1

    writer.release()
    return str(clip_path)


def animate_all_scenes(
    storyboard: dict[str, Any],
    output_dir: Path,
    config: PipelineConfig,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> list[Path]:
    """Run Vision-Guided Audio Sync (gemma3:12b) then render all scenes in parallel."""
    scenes_dir = output_dir / "scenes"
    clips_dir = output_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    alignment_path = output_dir / "alignment.json"
    alignment = json.loads(alignment_path.read_text(encoding="utf-8")) if alignment_path.exists() else None

    beats = storyboard["beats"]

    # Step 1: Vision-Guided Audio Sync (gemma3:12b looks at each scene and maps boxes -> Whisper timestamps)
    cue_map = _plan_vision_audio_sync(storyboard, alignment, output_dir, config, progress_cb=progress_cb)

    # Step 2: Parallel contour-tracing render locked to exact Vision/Whisper timestamps
    cfg_dict = {
        "video_width": config.video_width,
        "video_height": config.video_height,
        "fps": config.fps,
        "draw_hand": config.draw_hand,
        "end_color": config.end_color,
        "min_hold_sec": config.min_hold_sec,
    }

    jobs: list[tuple[int, tuple[str, str, float, list[dict[str, Any]], dict[str, Any]]]] = []
    clip_paths: list[Path] = []
    done_count = 0

    for beat in beats:
        beat_id = int(beat["beat_id"])
        scene_path = scenes_dir / f"scene_{beat_id:02d}.png"
        clip_path = clips_dir / f"clip_{beat_id:02d}.mp4"
        clip_paths.append(clip_path)

        if config.skip_existing and clip_path.exists() and clip_path.stat().st_size > 10_000:
            done_count += 1
            if progress_cb:
                progress_cb(done_count, len(beats), f"Reused {clip_path.name} ({done_count}/{len(beats)})")
            continue

        cues = cue_map.get(beat_id) or beat.get("audio_sync_cues") or []
        jobs.append((beat_id, (str(scene_path), str(clip_path), float(beat["duration"]), cues, cfg_dict)))

    if jobs:
        workers = max(1, min(config.animate_workers, len(jobs), os.cpu_count() or 2))
        logger.info("Rendering %d audio-synced scene(s) (%d worker(s)) ...", len(jobs), workers)
        if workers == 1:
            for beat_id, job_args in jobs:
                _render_single_beat_worker(job_args)
                done_count += 1
                if progress_cb:
                    progress_cb(done_count, len(beats), f"Animated clip_{beat_id:02d}.mp4 ({done_count}/{len(beats)})")
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                fut_map = {pool.submit(_render_single_beat_worker, job_args): beat_id for beat_id, job_args in jobs}
                for fut in as_completed(fut_map):
                    beat_id = fut_map[fut]
                    fut.result()
                    done_count += 1
                    logger.info("Animated clip_%02d.mp4 (%d/%d)", beat_id, done_count, len(beats))
                    if progress_cb:
                        progress_cb(done_count, len(beats), f"Animated clip_{beat_id:02d}.mp4 ({done_count}/{len(beats)})")

    return clip_paths

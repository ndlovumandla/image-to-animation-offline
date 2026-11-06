import os
import sys
import time
import datetime
from collections import deque
from fractions import Fraction
import wave
import cv2
import numpy as np
import av
from pathlib import Path
from kivy.core.audio import SoundLoader

import sketchApi
from project_model import AudioClip, Project, SceneData


EXPORT_AUDIO_RATE = 48000
EXPORT_AUDIO_BIT_RATE = 256000
EXPORT_AUDIO_PEAK = 0.98


def get_audio_info(audio_path):
    """
    Returns metadata dict for an audio file:
    {
        'duration': float (seconds),
        'channels': int,
        'rate': int,
        'format': str
    }
    """
    if not audio_path or not os.path.isfile(audio_path):
        return {"duration": 0.0, "channels": 2, "rate": 44100, "format": "none"}

    duration = 0.0
    channels = 2
    rate = 44100

    try:
        with av.open(audio_path) as container:
            if container.duration:
                duration = float(container.duration) / 1000000.0
            if container.streams.audio:
                audio_stream = container.streams.audio[0]
                if audio_stream.duration and audio_stream.time_base and duration <= 0:
                    duration = float(audio_stream.duration * audio_stream.time_base)
                if hasattr(audio_stream, 'channels'):
                    channels = audio_stream.channels or 2
                if hasattr(audio_stream, 'rate'):
                    rate = audio_stream.rate or 44100
    except Exception as e:
        print(f"PyAV audio read error for {audio_path}: {e}")
        # Fallback to Kivy SoundLoader
        try:
            snd = SoundLoader.load(audio_path)
            if snd:
                duration = float(snd.length) if snd.length else 0.0
                snd.unload()
        except Exception as e2:
            print(f"SoundLoader fallback failed: {e2}")

    return {
        "duration": max(0.0, float(duration)),
        "channels": channels,
        "rate": rate,
    }


def mux_video_and_audio(raw_video_path, audio_path, output_path, target_duration=0.0, platform="linux"):
    """
    Encodes raw sketch video (from cv2 VideoWriter) to H.264,
    adds audio (from audio_path or silent AAC),
    and pads the last video frame if sketch finishes before the audio ends.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    out_container = av.open(output_path, mode="w")

    # Read raw video stream info
    raw_container = av.open(raw_video_path, mode="r")
    raw_v_stream = raw_container.streams.video[0]
    width = raw_v_stream.codec_context.width
    height = raw_v_stream.codec_context.height
    fps = raw_v_stream.average_rate or 25

    # Add output video stream
    codec_name = "libx264" if platform == "android" else "h264"
    try:
        out_v_stream = out_container.add_stream(codec_name, rate=fps)
    except Exception:
        out_v_stream = out_container.add_stream("libx264", rate=fps)

    out_v_stream.width = width
    out_v_stream.height = height
    out_v_stream.pix_fmt = "yuv420p"
    out_v_stream.options = {"crf": "20"}

    # Add output audio stream (AAC 48000 stereo, 256 kbps)
    out_a_stream = out_container.add_stream("aac", rate=EXPORT_AUDIO_RATE)
    out_a_stream.layout = "stereo"
    out_a_stream.codec_context.bit_rate = EXPORT_AUDIO_BIT_RATE
    resampler = av.AudioResampler(format="fltp", layout="stereo", rate=EXPORT_AUDIO_RATE)

    # Decode and retime the sketch so the scene bar controls exact duration.
    raw_frames = list(raw_container.decode(video=0))
    raw_container.close()
    fps_val = float(fps)
    target_frames = max(1, int(round((target_duration or len(raw_frames) / fps_val) * fps_val)))
    if not raw_frames:
        raise ValueError("Sketch renderer produced no video frames")
    indices = np.linspace(0, len(raw_frames) - 1, target_frames).astype(np.int64)
    for index in indices:
        frame = raw_frames[int(index)]
        frame.pts = None
        for packet in out_v_stream.encode(frame):
            out_container.mux(packet)
    frame_count = target_frames

    # Flush video encoder
    for packet in out_v_stream.encode():
        out_container.mux(packet)

    # Encode audio
    has_audio_file = audio_path and os.path.isfile(audio_path)
    if has_audio_file:
        try:
            stereo_samples = _limit_audio_peaks(decode_audio_stereo(audio_path, EXPORT_AUDIO_RATE), EXPORT_AUDIO_RATE)
            chunk_size = 1024
            for start in range(0, stereo_samples.shape[1], chunk_size):
                values = np.ascontiguousarray(stereo_samples[:, start:start + chunk_size], dtype=np.float32)
                frame = av.AudioFrame.from_ndarray(values, format="fltp", layout="stereo")
                frame.sample_rate = EXPORT_AUDIO_RATE
                frame.pts = start
                frame.time_base = Fraction(1, EXPORT_AUDIO_RATE)
                for packet in out_a_stream.encode(frame):
                    out_container.mux(packet)
        except Exception as e:
            print(f"Error encoding audio track {audio_path}: {e}")
            has_audio_file = False

    if not has_audio_file:
        # Generate silence matching the video duration
        total_audio_samples = int(round((frame_count / fps_val) * EXPORT_AUDIO_RATE))
        written_samples = 0
        while written_samples < total_audio_samples:
            chunk = min(1024, total_audio_samples - written_samples)
            silent_frame = av.AudioFrame(format="s16", layout="stereo", samples=chunk)
            silent_frame.sample_rate = EXPORT_AUDIO_RATE
            for rf in resampler.resample(silent_frame):
                rf.pts = None
                for packet in out_a_stream.encode(rf):
                    out_container.mux(packet)
            written_samples += chunk

        for rf in resampler.resample(None):
            rf.pts = None
            for packet in out_a_stream.encode(rf):
                out_container.mux(packet)

    # Flush audio encoder
    for packet in out_a_stream.encode():
        out_container.mux(packet)

    out_container.close()
    return output_path


def render_scene_clip(scene, output_dir, platform="linux", progress_callback=None):
    """
    Renders whiteboard sketch animation for a single SceneData instance,
    with audio matched according to Smart Timing.
    """
    if not scene.image_path or not os.path.isfile(scene.image_path):
        raise ValueError(f"Scene image not found: {scene.image_path}")

    scene.refresh_audio_info()
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_video_path = os.path.join(output_dir, f"raw_scene_{scene.id}_{timestamp}.mp4")
    final_scene_path = os.path.join(output_dir, f"scene_{scene.id}_{timestamp}_muxed.mp4")

    # Smart Timing calculation
    target_dur = scene.effective_duration
    drawing_hold_sec = 2

    if scene.audio_path and scene.audio_duration > 0:
        # Estimate sketch drawing time
        try:
            estim_drawing = sketchApi.estimate_video_duration_seconds(
                image_path=scene.image_path,
                split_len=scene.split_len,
                frame_rate=scene.frame_rate,
                object_skip_rate=scene.object_skip_rate,
                bg_object_skip_rate=scene.bg_object_skip_rate,
                main_img_duration=1,
                end_color=scene.end_color,
                draw_hand=scene.draw_hand,
                max_1080p=scene.max_1080p,
                fill_speed=scene.fill_speed,
                gap_px=scene.gap_px,
            )
            # If drawing takes less than audio, calculate remaining hold time
            if estim_drawing < scene.audio_duration:
                drawing_hold_sec = max(1, int(round(scene.audio_duration - estim_drawing)))
            else:
                drawing_hold_sec = 1
        except Exception as e:
            print(f"Error estimating duration: {e}")
            drawing_hold_sec = 2
    else:
        drawing_hold_sec = max(1, int(round(scene.custom_duration / 2)))

    # Whiteboard drawing
    image_bgr = cv2.imread(scene.image_path)
    img_ht, img_wd = image_bgr.shape[0], image_bgr.shape[1]

    if scene.max_1080p:
        img_wd, img_ht = 1920, 1080
        image_bgr = sketchApi.resize_with_padding(
            img=image_bgr,
            target_width=img_wd,
            target_height=img_ht,
        )
    else:
        aspect_ratio = img_wd / img_ht
        img_ht = sketchApi.find_nearest_res(img_ht)
        new_aspect_wd = int(img_ht * aspect_ratio)
        img_wd = sketchApi.find_nearest_res(new_aspect_wd)

    variables = sketchApi.AllVariables(
        frame_rate=scene.frame_rate,
        resize_wd=img_wd,
        resize_ht=img_ht,
        split_len=scene.split_len,
        object_skip_rate=scene.object_skip_rate,
        bg_object_skip_rate=scene.bg_object_skip_rate,
        end_gray_img_duration_in_sec=drawing_hold_sec,
        draw_hand=scene.draw_hand,
        draw_color=False,
        two_pass=scene.end_color,
        fill_speed_multiplier=scene.fill_speed,
        white_gap_threshold=scene.gap_px,
        end_color=scene.end_color,
    )

    if progress_callback:
        progress_callback("Drawing whiteboard animation...")

    sketchApi.draw_whiteboard_animations(
        img=image_bgr,
        mask_path=None,
        hand_path=sketchApi.hand_path,
        hand_mask_path=sketchApi.hand_mask_path,
        save_video_path=raw_video_path,
        variables=variables,
        end_color=scene.end_color,
    )

    if progress_callback:
        progress_callback("Synchronizing audio & encoding...")

    # Mux video + audio with smart timing padding
    mux_video_and_audio(
        raw_video_path=raw_video_path,
        audio_path=scene.audio_path,
        output_path=final_scene_path,
        target_duration=target_dur,
        platform=platform,
    )

    if os.path.exists(raw_video_path):
        try:
            os.remove(raw_video_path)
        except Exception:
            pass

    scene.rendered_video = final_scene_path
    scene.dirty = False
    return final_scene_path


def concatenate_scenes(scene_clips, output_path, platform="linux", progress_callback=None, transitions=None):
    """
    Concatenates multiple scene MP4 clips (video + audio) into one master video file.
    """
    if not scene_clips:
        raise ValueError("No scene clips provided to concatenate.")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    out_container = av.open(output_path, mode="w")

    # Inspect first clip for video dimensions and rate
    first_clip = scene_clips[0]
    with av.open(first_clip) as probe:
        v_stream = probe.streams.video[0]
        width = v_stream.codec_context.width
        height = v_stream.codec_context.height
        fps = v_stream.average_rate or 25

    codec_name = "libx264" if platform == "android" else "h264"
    try:
        out_v_stream = out_container.add_stream(codec_name, rate=fps)
    except Exception:
        out_v_stream = out_container.add_stream("libx264", rate=fps)

    out_v_stream.width = width
    out_v_stream.height = height
    out_v_stream.pix_fmt = "yuv420p"
    out_v_stream.options = {"crf": "20"}

    out_a_stream = out_container.add_stream("aac", rate=EXPORT_AUDIO_RATE)
    out_a_stream.layout = "stereo"
    out_a_stream.codec_context.bit_rate = EXPORT_AUDIO_BIT_RATE
    resampler = av.AudioResampler(format="fltp", layout="stereo", rate=EXPORT_AUDIO_RATE)

    total_scenes = len(scene_clips)
    transitions = transitions or []
    previous_tail = []
    previous_fade_frames = 0
    for idx, clip_path in enumerate(scene_clips):
        if progress_callback:
            progress_callback(f"Stitching scene {idx + 1} of {total_scenes}...")

        with av.open(clip_path) as inp:
            # Video frames
            current_transition = transitions[idx] if idx < len(transitions) else None
            fade_frames = int(round(float(getattr(current_transition, "duration", 0.0)) * float(fps))) \
                if getattr(current_transition, "kind", "none") == "fade" else 0
            current_tail = deque(maxlen=max(1, fade_frames))
            video_index = 0
            for vf in inp.decode(video=0):
                if previous_fade_frames and video_index < previous_fade_frames and video_index < len(previous_tail):
                    alpha = (video_index + 1) / max(1, previous_fade_frames)
                    incoming = vf.to_ndarray(format="bgr24").astype(np.float32)
                    blended = previous_tail[video_index].astype(np.float32) * (1.0 - alpha) + incoming * alpha
                    vf = av.VideoFrame.from_ndarray(blended.astype(np.uint8), format="bgr24")
                vf.pts = None
                for packet in out_v_stream.encode(vf):
                    out_container.mux(packet)
                if fade_frames:
                    current_tail.append(vf.to_ndarray(format="bgr24"))
                video_index += 1
            previous_tail = list(current_tail)
            previous_fade_frames = min(fade_frames, len(previous_tail))

            # Audio frames (seek back to 0)
            inp.seek(0)
            if inp.streams.audio:
                for af in inp.decode(audio=0):
                    for rf in resampler.resample(af):
                        rf.pts = None
                        for packet in out_a_stream.encode(rf):
                            out_container.mux(packet)

    # Flush resampler
    for rf in resampler.resample(None):
        rf.pts = None
        for packet in out_a_stream.encode(rf):
            out_container.mux(packet)

    # Flush encoders
    for packet in out_v_stream.encode():
        out_container.mux(packet)
    for packet in out_a_stream.encode():
        out_container.mux(packet)

    out_container.close()
    return output_path


def export_full_project(scenes, output_path, output_dir, platform="linux", progress_callback=None):
    """
    Renders all scenes in sequence and concatenates them into a master video.
    """
    if not scenes:
        raise ValueError("Project has no scenes.")

    rendered_clips = []
    total = len(scenes)

    for i, scene in enumerate(scenes):
        scene_num = i + 1
        if progress_callback:
            progress_callback(f"Rendering Scene {scene_num}/{total}...", (i / total) * 0.8)

        # Render scene clip
        clip_path = render_scene_clip(
            scene=scene,
            output_dir=output_dir,
            platform=platform,
            progress_callback=lambda msg, s_num=scene_num: progress_callback(
                f"Scene {s_num}/{total}: {msg}", ((s_num - 1) / total) * 0.8
            ) if progress_callback else None,
        )
        rendered_clips.append(clip_path)

    if progress_callback:
        progress_callback("Stitching all scenes into final video...", 0.85)

    final_video = concatenate_scenes(
        scene_clips=rendered_clips,
        output_path=output_path,
        platform=platform,
        progress_callback=lambda msg: progress_callback(msg, 0.95) if progress_callback else None,
        transitions=[scene.transition for scene in scenes],
    )

    if progress_callback:
        progress_callback("Final video ready!", 1.0)

    return final_video


def decode_audio_stereo(path, sample_rate=EXPORT_AUDIO_RATE):
    """Decode audio to normalized float32 stereo samples without downmixing it."""
    if not path or not os.path.isfile(path):
        raise ValueError(f"Audio file not found: {path}")
    chunks = []
    with av.open(path) as container:
        if not container.streams.audio:
            raise ValueError(f"No audio stream found: {path}")
        audio_stream = container.streams.audio[0]
        is_mono = (getattr(audio_stream, "channels", None) or getattr(audio_stream.codec_context, "channels", 2)) == 1
        target_layout = "mono" if is_mono else "stereo"
        resampler = av.AudioResampler(format="fltp", layout=target_layout, rate=sample_rate)
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                arr = converted.to_ndarray().astype(np.float32)
                chunks.append(np.vstack([arr.reshape(1, -1), arr.reshape(1, -1)]) if is_mono else arr.reshape(2, -1))
        for converted in resampler.resample(None):
            arr = converted.to_ndarray().astype(np.float32)
            chunks.append(np.vstack([arr.reshape(1, -1), arr.reshape(1, -1)]) if is_mono else arr.reshape(2, -1))
    return np.concatenate(chunks, axis=1) if chunks else np.zeros((2, 0), dtype=np.float32)


def decode_audio_mono(path, sample_rate=EXPORT_AUDIO_RATE):
    """Decode audio for callers that explicitly need a mono representation."""
    stereo = decode_audio_stereo(path, sample_rate)
    return stereo.mean(axis=0, dtype=np.float32)


def generate_waveform(path, points=600):
    """Return bounded peak values suitable for drawing a timeline waveform."""
    samples = decode_audio_stereo(path)
    if samples.size == 0:
        return []
    points = max(16, int(points))
    frame_count = samples.shape[1]
    stride = max(1, int(np.ceil(frame_count / points)))
    peaks = [
        float(np.max(np.abs(samples[:, i:i + stride])))
        for i in range(0, frame_count, stride)
    ]
    maximum = max(peaks, default=1.0) or 1.0
    return [round(value / maximum, 4) for value in peaks[:points]]


def _limit_audio_peaks(samples, sample_rate, ceiling=EXPORT_AUDIO_PEAK, release_ms=0.0):
    """Constrain only clipping frames; never apply gain changes over time."""
    if samples.size == 0:
        return samples
    frame_peaks = np.max(np.abs(samples), axis=0)
    gain = np.ones(frame_peaks.shape, dtype=np.float32)
    clipping = frame_peaks > ceiling
    gain[clipping] = ceiling / frame_peaks[clipping]
    return samples * gain[np.newaxis, :]


def mix_project_audio(project, sample_rate=EXPORT_AUDIO_RATE):
    """Mix the project's master and overlay tracks into stereo float samples."""
    total_samples = max(1, int(np.ceil(project.duration * sample_rate)))
    mix = np.zeros((2, total_samples), dtype=np.float32)
    for track in project.audio_tracks:
        if track.muted or track.volume <= 0:
            continue
        for clip in track.clips:
            if clip.muted or clip.volume <= 0 or not os.path.isfile(clip.source_path):
                continue
            source = decode_audio_stereo(clip.source_path, sample_rate)
            start_src = int(round(clip.trim_in * sample_rate))
            end_src = int(round((clip.trim_out or clip.source_duration) * sample_rate))
            source = source[:, start_src:end_src]
            if source.size == 0:
                continue
            gain = float(track.volume) * float(clip.volume)
            source = source * gain
            fade_in = min(source.shape[1], int(round(clip.fade_in * sample_rate)))
            fade_out = min(source.shape[1], int(round(clip.fade_out * sample_rate)))
            if fade_in:
                source[:, :fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
            if fade_out:
                source[:, -fade_out:] *= np.linspace(1.0, 0.0, fade_out, dtype=np.float32)
            dst_start = int(round(clip.start * sample_rate))
            dst_end = min(total_samples, dst_start + source.shape[1])
            if dst_start < total_samples and dst_end > dst_start:
                mix[:, dst_start:dst_end] += source[:, :dst_end - dst_start]
    return _limit_audio_peaks(mix, sample_rate)


def write_mix_preview(project, output_path, sample_rate=EXPORT_AUDIO_RATE, start_time=0.0):
    """Write the current project mix to a WAV file for synchronized preview."""
    mix = mix_project_audio(project, sample_rate)
    start_sample = max(0, int(round(float(start_time) * sample_rate)))
    mix = mix[:, start_sample:]
    pcm = np.clip(mix.T, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with wave.open(output_path, "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm.tobytes())
    return output_path


def replace_audio(video_path, project, output_path, platform="linux", progress_callback=None):
    """Copy/re-encode timeline video and attach the mixed project audio."""
    if progress_callback:
        progress_callback("Mixing master and overlay audio...", 0.96)
    mix = mix_project_audio(project)
    with av.open(video_path) as source:
        in_video = source.streams.video[0]
        fps = in_video.average_rate or project.frame_rate
        output = av.open(output_path, mode="w")
        try:
            try:
                out_video = output.add_stream("h264", rate=fps)
            except Exception:
                out_video = output.add_stream("libx264", rate=fps)
            out_video.width = in_video.codec_context.width
            out_video.height = in_video.codec_context.height
            out_video.pix_fmt = "yuv420p"
            out_video.options = {"crf": "20"}
            out_audio = output.add_stream("aac", rate=EXPORT_AUDIO_RATE)
            out_audio.layout = "stereo"
            out_audio.codec_context.bit_rate = EXPORT_AUDIO_BIT_RATE
            out_audio.time_base = Fraction(1, EXPORT_AUDIO_RATE)
            out_audio.codec_context.time_base = Fraction(1, EXPORT_AUDIO_RATE)
            for frame in source.decode(video=0):
                frame.pts = None
                for packet in out_video.encode(frame):
                    output.mux(packet)
            for packet in out_video.encode():
                output.mux(packet)

            chunk_size = 1024
            for start in range(0, mix.shape[1], chunk_size):
                values = np.ascontiguousarray(mix[:, start:start + chunk_size], dtype=np.float32)
                frame = av.AudioFrame.from_ndarray(values, format="fltp", layout="stereo")
                frame.sample_rate = EXPORT_AUDIO_RATE
                frame.pts = start
                frame.time_base = Fraction(1, EXPORT_AUDIO_RATE)
                for packet in out_audio.encode(frame):
                    output.mux(packet)
            for packet in out_audio.encode():
                output.mux(packet)
        finally:
            output.close()
    return output_path


def export_timeline_project(project, output_path, output_dir, platform="linux", progress_callback=None):
    """Export an immutable Project snapshot with its independent audio tracks."""
    if not isinstance(project, Project):
        raise TypeError("export_timeline_project expects a Project")
    snapshot = project.snapshot()
    if snapshot.master_duration > snapshot.scene_duration:
        snapshot.scenes[-1].set_duration(
            snapshot.scenes[-1].effective_duration + snapshot.master_duration - snapshot.scene_duration
        )
    missing = [scene.image_path for scene in snapshot.scenes if not os.path.isfile(scene.image_path)]
    if missing:
        raise ValueError(f"Missing scene media: {missing[0]}")
    os.makedirs(output_dir, exist_ok=True)
    silent_path = os.path.join(output_dir, f"timeline_silent_{int(time.time())}.mp4")
    export_full_project(
        snapshot.scenes,
        silent_path,
        output_dir,
        platform,
        progress_callback=(lambda msg, pct: progress_callback(msg, pct * 0.94)) if progress_callback else None,
    )
    try:
        return replace_audio(silent_path, snapshot, output_path, platform, progress_callback)
    finally:
        try:
            os.remove(silent_path)
        except OSError:
            pass

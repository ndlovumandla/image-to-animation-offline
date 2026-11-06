"""Serializable project model for the Sketch Studio timeline.

The model deliberately has no Kivy dependencies.  UI code can take immutable
snapshots while background render jobs are running and tests can exercise all
timeline behaviour without opening a window.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
import copy
import json
import os
import uuid


PROJECT_VERSION = 1
MIN_DURATION = 0.1


def new_id() -> str:
    return uuid.uuid4().hex


def _clamp(value: float, low: float, high: float | None = None) -> float:
    value = max(low, float(value))
    return min(value, high) if high is not None else value


@dataclass
class Transition:
    kind: str = "none"
    duration: float = 0.0

    def normalize(self, scene_duration: float) -> None:
        if self.kind not in {"none", "fade"}:
            self.kind = "none"
        if self.kind == "none":
            self.duration = 0.0
        else:
            self.duration = _clamp(self.duration or 0.5, MIN_DURATION, scene_duration / 2)


@dataclass
class SceneData:
    id: str = field(default_factory=new_id)
    image_path: str = ""
    custom_duration: float = 4.0
    split_len: int = 10
    end_color: bool = True
    draw_hand: bool = True
    max_1080p: bool = True
    object_skip_rate: int = 8
    bg_object_skip_rate: int = 14
    fill_speed: int = 8
    gap_px: int = 4
    frame_rate: int = 25
    transition: Transition = field(default_factory=Transition)
    rendered_video: str | None = None
    render_key: str = ""
    dirty: bool = True

    # Legacy fields are retained as read-only compatibility data while the UI
    # is migrated away from attaching sound directly to a scene.
    audio_path: str = ""
    audio_duration: float = 0.0

    def __post_init__(self) -> None:
        self.custom_duration = _clamp(self.custom_duration, MIN_DURATION)
        if isinstance(self.transition, dict):
            self.transition = Transition(**self.transition)
        self.transition.normalize(self.custom_duration)

    @property
    def effective_duration(self) -> float:
        return _clamp(self.custom_duration, MIN_DURATION)

    def set_duration(self, value: float) -> None:
        self.custom_duration = _clamp(value, MIN_DURATION)
        self.transition.normalize(self.custom_duration)
        self.dirty = True

    def refresh_audio_info(self) -> None:
        """Compatibility no-op for the old scene renderer."""
        self.audio_duration = 0.0

    def clone(self) -> "SceneData":
        duplicate = copy.deepcopy(self)
        duplicate.id = new_id()
        duplicate.rendered_video = None
        duplicate.render_key = ""
        duplicate.dirty = True
        return duplicate


@dataclass
class AudioClip:
    id: str = field(default_factory=new_id)
    source_path: str = ""
    start: float = 0.0
    source_duration: float = 0.0
    trim_in: float = 0.0
    trim_out: float = 0.0
    volume: float = 1.0
    muted: bool = False
    fade_in: float = 0.0
    fade_out: float = 0.0
    waveform: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.normalize()

    @property
    def duration(self) -> float:
        end = self.trim_out if self.trim_out > 0 else self.source_duration
        return max(0.0, end - self.trim_in)

    @property
    def end(self) -> float:
        return self.start + self.duration

    def normalize(self) -> None:
        self.start = max(0.0, float(self.start))
        self.source_duration = max(0.0, float(self.source_duration))
        self.trim_in = _clamp(self.trim_in, 0.0, self.source_duration or None)
        if self.trim_out <= 0:
            self.trim_out = self.source_duration
        self.trim_out = _clamp(self.trim_out, self.trim_in, self.source_duration or None)
        self.volume = _clamp(self.volume, 0.0, 2.0)
        self.fade_in = _clamp(self.fade_in, 0.0, self.duration)
        self.fade_out = _clamp(self.fade_out, 0.0, self.duration)

    def split(self, timeline_time: float) -> "AudioClip":
        offset = float(timeline_time) - self.start
        if offset < MIN_DURATION or self.duration - offset < MIN_DURATION:
            raise ValueError("Playhead must be inside the clip, away from its edges")
        right = copy.deepcopy(self)
        right.id = new_id()
        right.start = float(timeline_time)
        right.trim_in = self.trim_in + offset
        # A split is seamless: the original fade-in belongs only to the left
        # edge and the original fade-out belongs only to the right edge.
        right.fade_in = 0.0
        self.trim_out = right.trim_in
        self.fade_out = 0.0
        self.normalize()
        right.normalize()
        return right


@dataclass
class AudioTrack:
    id: str = field(default_factory=new_id)
    name: str = "Audio"
    role: str = "overlay"  # exactly one track is promoted to master
    volume: float = 1.0
    muted: bool = False
    clips: list[AudioClip] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.volume = _clamp(self.volume, 0.0, 2.0)
        self.clips = [c if isinstance(c, AudioClip) else AudioClip(**c) for c in self.clips]

    @property
    def end(self) -> float:
        return max((clip.end for clip in self.clips), default=0.0)


@dataclass
class Project:
    version: int = PROJECT_VERSION
    id: str = field(default_factory=new_id)
    name: str = "Untitled Project"
    width: int = 1920
    height: int = 1080
    frame_rate: int = 25
    scenes: list[SceneData] = field(default_factory=list)
    audio_tracks: list[AudioTrack] = field(default_factory=list)
    project_path: str = ""
    dirty: bool = False

    def __post_init__(self) -> None:
        self.scenes = [s if isinstance(s, SceneData) else SceneData(**s) for s in self.scenes]
        self.audio_tracks = [t if isinstance(t, AudioTrack) else AudioTrack(**t) for t in self.audio_tracks]
        if not self.scenes:
            self.scenes.append(SceneData(frame_rate=self.frame_rate))
        self.ensure_single_master()

    @property
    def scene_duration(self) -> float:
        return sum(scene.effective_duration for scene in self.scenes)

    @property
    def master_track(self) -> AudioTrack | None:
        return next((track for track in self.audio_tracks if track.role == "master"), None)

    @property
    def master_duration(self) -> float:
        track = self.master_track
        return track.end if track else 0.0

    @property
    def duration(self) -> float:
        # The master waveform defines the end when present. Scenes that extend
        # beyond it are retained and exported rather than silently discarded.
        return max(self.scene_duration, self.master_duration)

    def ensure_single_master(self) -> None:
        masters = [track for track in self.audio_tracks if track.role == "master"]
        if not masters and self.audio_tracks:
            self.audio_tracks[0].role = "master"
            masters = [self.audio_tracks[0]]
        for duplicate in masters[1:]:
            duplicate.role = "overlay"

    def add_audio_track(self, name: str = "Audio", master: bool = False) -> AudioTrack:
        if master:
            for track in self.audio_tracks:
                track.role = "overlay"
        track = AudioTrack(name=name, role="master" if master or not self.audio_tracks else "overlay")
        self.audio_tracks.append(track)
        self.dirty = True
        return track

    def scene_at(self, timeline_time: float) -> tuple[int, SceneData, float]:
        cursor = 0.0
        for index, scene in enumerate(self.scenes):
            end = cursor + scene.effective_duration
            if timeline_time < end or index == len(self.scenes) - 1:
                return index, scene, max(0.0, timeline_time - cursor)
            cursor = end
        return len(self.scenes) - 1, self.scenes[-1], 0.0

    def snapshot(self) -> "Project":
        return copy.deepcopy(self)

    def to_dict(self, base_dir: str | None = None) -> dict[str, Any]:
        data = asdict(self)
        data.pop("dirty", None)
        data.pop("project_path", None)
        if base_dir:
            for scene in data["scenes"]:
                scene["image_path"] = _portable_path(scene["image_path"], base_dir)
                if scene.get("rendered_video"):
                    scene["rendered_video"] = _portable_path(scene["rendered_video"], base_dir)
            for track in data["audio_tracks"]:
                for clip in track["clips"]:
                    clip["source_path"] = _portable_path(clip["source_path"], base_dir)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any], base_dir: str | None = None) -> "Project":
        payload = copy.deepcopy(data)
        version = int(payload.get("version", 0))
        if version != PROJECT_VERSION:
            raise ValueError(f"Unsupported project version: {version}")
        for scene in payload.get("scenes", []):
            scene["transition"] = Transition(**scene.get("transition", {}))
            if base_dir:
                scene["image_path"] = _resolved_path(scene.get("image_path", ""), base_dir)
                if scene.get("rendered_video"):
                    scene["rendered_video"] = _resolved_path(scene["rendered_video"], base_dir)
        for track in payload.get("audio_tracks", []):
            track["clips"] = [AudioClip(**clip) for clip in track.get("clips", [])]
            if base_dir:
                for clip in track["clips"]:
                    clip.source_path = _resolved_path(clip.source_path, base_dir)
        project = cls(**payload)
        project.dirty = False
        return project

    def save(self, path: str) -> str:
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            json.dump(self.to_dict(str(target.parent)), handle, indent=2)
        self.project_path = str(target)
        self.name = target.stem
        self.dirty = False
        return str(target)

    @classmethod
    def load(cls, path: str) -> "Project":
        target = Path(path).expanduser().resolve()
        with target.open("r", encoding="utf-8") as handle:
            project = cls.from_dict(json.load(handle), str(target.parent))
        project.project_path = str(target)
        project.name = target.stem
        return project


def find_clip(tracks: Iterable[AudioTrack], clip_id: str) -> tuple[AudioTrack, AudioClip] | tuple[None, None]:
    for track in tracks:
        for clip in track.clips:
            if clip.id == clip_id:
                return track, clip
    return None, None


def _portable_path(path: str, base_dir: str) -> str:
    if not path:
        return ""
    try:
        return os.path.relpath(os.path.abspath(path), os.path.abspath(base_dir))
    except ValueError:
        return os.path.abspath(path)


def _resolved_path(path: str, base_dir: str) -> str:
    if not path or os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(base_dir, path))

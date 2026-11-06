import math
import os
import struct
import tempfile
import unittest
import wave

from project_model import AudioClip, Project
import numpy as np

from video_studio import (
    EXPORT_AUDIO_RATE,
    _limit_audio_peaks,
    decode_audio_stereo,
    generate_waveform,
    mix_project_audio,
)


def make_tone(path, duration=1.0, frequency=440, rate=44100):
    with wave.open(path, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        frames = bytearray()
        for index in range(int(duration * rate)):
            value = int(12000 * math.sin(2 * math.pi * frequency * index / rate))
            frames.extend(struct.pack("<h", value))
        output.writeframes(frames)


def make_stereo_tone(path, duration=0.1, rate=48000):
    with wave.open(path, "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(rate)
        frames = bytearray()
        for index in range(int(duration * rate)):
            left = int(10000 * math.sin(2 * math.pi * 440 * index / rate))
            right = int(6000 * math.sin(2 * math.pi * 880 * index / rate))
            frames.extend(struct.pack("<hh", left, right))
        output.writeframes(frames)


class ProjectModelTests(unittest.TestCase):
    def test_master_audio_defines_longer_project(self):
        project = Project()
        project.scenes[0].set_duration(2)
        track = project.add_audio_track("Master", master=True)
        track.clips.append(AudioClip(source_duration=7, trim_out=7))
        self.assertEqual(project.master_duration, 7)
        self.assertEqual(project.duration, 7)

    def test_split_preserves_source_range_and_timeline(self):
        clip = AudioClip(start=2, source_duration=10, trim_in=1, trim_out=9, fade_in=1, fade_out=2)
        right = clip.split(5)
        self.assertAlmostEqual(clip.duration, 3)
        self.assertAlmostEqual(right.start, 5)
        self.assertAlmostEqual(right.duration, 5)
        self.assertAlmostEqual(right.trim_in, 4)
        self.assertEqual(clip.fade_in, 1)
        self.assertEqual(clip.fade_out, 0)
        self.assertEqual(right.fade_in, 0)
        self.assertEqual(right.fade_out, 2)

    def test_round_trip_uses_relative_media_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            media = os.path.join(folder, "tone.wav")
            make_tone(media, 0.1)
            project = Project()
            track = project.add_audio_track("Master", master=True)
            track.clips.append(AudioClip(source_path=media, source_duration=0.1, trim_out=0.1))
            path = os.path.join(folder, "project.sketchproj")
            project.save(path)
            loaded = Project.load(path)
            self.assertEqual(os.path.normcase(loaded.master_track.clips[0].source_path), os.path.normcase(media))
            self.assertFalse(loaded.dirty)

    def test_waveform_and_overlapping_mix(self):
        with tempfile.TemporaryDirectory() as folder:
            media = os.path.join(folder, "tone.wav")
            make_tone(media)
            peaks = generate_waveform(media, points=80)
            self.assertGreater(len(peaks), 10)
            self.assertLessEqual(max(peaks), 1.0)
            project = Project()
            project.scenes[0].set_duration(1)
            master = project.add_audio_track("Master", master=True)
            overlay = project.add_audio_track("Overlay")
            master.clips.append(AudioClip(source_path=media, source_duration=1, trim_out=1, volume=0.5))
            overlay.clips.append(AudioClip(source_path=media, source_duration=1, trim_out=1, volume=0.5))
            mixed = mix_project_audio(project)
            self.assertEqual(mixed.shape, (2, EXPORT_AUDIO_RATE))
            self.assertGreater(float(abs(mixed).max()), 0)
            self.assertLessEqual(float(abs(mixed).max()), 0.98)

    def test_stereo_decode_preserves_distinct_channels(self):
        with tempfile.TemporaryDirectory() as folder:
            media = os.path.join(folder, "stereo.wav")
            make_stereo_tone(media)
            decoded = decode_audio_stereo(media)
            self.assertEqual(decoded.shape, (2, int(0.1 * EXPORT_AUDIO_RATE)))
            self.assertFalse(np.allclose(decoded[0], decoded[1]))

    def test_limiter_does_not_lower_audio_before_a_later_peak(self):
        samples = np.full((2, 1000), 0.25, dtype=np.float32)
        samples[:, 500] = 2.0
        limited = _limit_audio_peaks(samples, 1000)
        self.assertTrue(np.allclose(limited[:, :500], 0.25))
        self.assertTrue(np.allclose(limited[:, 501:], 0.25))
        self.assertLessEqual(float(np.max(np.abs(limited))), 0.981)

    def test_mono_decode_preserves_unity_gain_and_exported_mp4_keeps_constant_volume(self):
        import av
        from video_studio import replace_audio

        with tempfile.TemporaryDirectory() as folder:
            media = os.path.join(folder, "mono_4s.wav")
            make_tone(media, duration=4.0, rate=24000)
            decoded = decode_audio_stereo(media)
            self.assertEqual(decoded.shape, (2, 4 * EXPORT_AUDIO_RATE))
            # Mono 0.25 amplitude sine wave should stay at ~0.25 peak (not attenuated by 0.7071)
            self.assertGreater(float(np.percentile(np.abs(decoded), 95)), 0.22)

            silent_video = os.path.join(folder, "silent.mp4")
            with av.open(silent_video, mode="w") as container:
                v_stream = container.add_stream("libx264", rate=25)
                v_stream.width = 160
                v_stream.height = 90
                v_stream.pix_fmt = "yuv420p"
                blank = np.zeros((90, 160, 3), dtype=np.uint8)
                for _ in range(4 * 25):
                    vf = av.VideoFrame.from_ndarray(blank, format="bgr24")
                    for pkt in v_stream.encode(vf):
                        container.mux(pkt)
                for pkt in v_stream.encode(None):
                    container.mux(pkt)

            project = Project()
            project.scenes[0].set_duration(4.0)
            master = project.add_audio_track("Master", master=True)
            master.clips.append(AudioClip(source_path=media, source_duration=4.0, trim_out=4.0, volume=1.0))

            exported_mp4 = os.path.join(folder, "exported.mp4")
            replace_audio(silent_video, project, exported_mp4)
            exported_audio = decode_audio_stereo(exported_mp4)
            rms_per_sec = [
                float(np.sqrt(np.mean(exported_audio[:, i * EXPORT_AUDIO_RATE:(i + 1) * EXPORT_AUDIO_RATE] ** 2)))
                for i in range(4)
            ]
            self.assertLess(max(rms_per_sec) / min(rms_per_sec), 1.03)


if __name__ == "__main__":
    unittest.main()

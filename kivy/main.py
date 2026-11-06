# python core modules
import os
os.environ['KIVY_GL_BACKEND'] = 'sdl2'
os.environ.setdefault('KIVY_AUDIO', 'sdl2')
os.environ.setdefault('KIVY_IMAGE', 'pil,sdl2')
import sys
import shutil
import datetime
import logging
import traceback
import subprocess
from threading import Thread
import queue

# kivy world
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.label import MDLabel
from kivymd.uix.button import (
    MDFlatButton, MDFloatingActionButton,
    MDFillRoundFlatIconButton, MDIconButton
)
from kivymd.uix.card import MDCard
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.spinner import MDSpinner
from kivymd.uix.filemanager import MDFileManager
from kivymd.uix.dialog import MDDialog
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.list import (
    MDList, OneLineIconListItem, OneLineAvatarIconListItem,
    IconLeftWidget, IconRightWidget
)
from kivymd.uix.progressbar import MDProgressBar

from kivy.uix.videoplayer import VideoPlayer
from kivy.uix.image import AsyncImage, Image
from kivy.uix.widget import Widget
from kivy.uix.slider import Slider
from kivy.uix.button import Button
from kivy.uix.modalview import ModalView
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.core.audio import SoundLoader
from kivy.graphics.texture import Texture
from kivy.metrics import dp, sp
from kivy.utils import platform
from kivy.clock import Clock
from kivy.properties import (
    StringProperty, NumericProperty, ObjectProperty,
    ColorProperty, BooleanProperty, ListProperty
)
from kivy.graphics import Color, Line, RoundedRectangle

# platform specific imports & functions
video_view = None
if platform == "android":
    from android.permissions import check_permission, request_permissions, Permission
    from jnius import autoclass, cast, PythonJavaClass, java_method
    from android.runnable import run_on_ui_thread

    class AndroidVideoComplete(PythonJavaClass):
        __javainterfaces__ = [
            'android/media/MediaPlayer$OnCompletionListener'
        ]
        @java_method('(Landroid/media/MediaPlayer;)V')
        def onCompletion(self, mp):
            print("Video completed")
            remove_video_android()

    @run_on_ui_thread
    def remove_video_android():
        global video_view
        if video_view:
            try:
                video_view.stopPlayback()
            except Exception:
                pass
            parent = video_view.getParent()
            if parent:
                cast('android.view.ViewGroup', parent).removeView(video_view)
            video_view = None

    @run_on_ui_thread
    def android_play_video(path, coordinates=None):
        global video_view
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        VideoView = autoclass('android.widget.VideoView')
        LayoutParams = autoclass('android.widget.FrameLayout$LayoutParams')
        MediaController = autoclass('android.widget.MediaController')
        activity = PythonActivity.mActivity
        video_view = VideoView(activity)
        if coordinates:
            params = LayoutParams(int(coordinates[0]), int(coordinates[1]))
            params.leftMargin = int(coordinates[2])
            params.topMargin = int(coordinates[3])
        else:
            params = LayoutParams(
                LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT
            )
        activity.addContentView(video_view, params)
        video_view.setVideoPath(path)
        controller = MediaController(activity)
        controller.setAnchorView(video_view)
        video_view.setMediaController(controller)
        video_view.setOnCompletionListener(AndroidVideoComplete())
        video_view.start()


# plyer for cross-platform file chooser
from plyer import filechooser

Window.softinput_mode = "below_target"

# Local modules
from screens.divider import MyMDDivider
import sketchApi
from project_model import AudioClip, Project, SceneData, find_clip
from video_studio import (
    export_timeline_project, generate_waveform, get_audio_info,
    render_scene_clip, write_mix_preview,
)

## Global definitions
__version__ = "2.1.0"

if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))
kv_file_path = os.path.join(base_path, 'studio_layout.kv')


def safe_local_image(path, fit_mode="contain"):
    """Load local media without Kivy's crash-prone Windows image providers."""
    pixels = sketchApi.cv2.imread(path, sketchApi.cv2.IMREAD_UNCHANGED)
    if pixels is None:
        raise ValueError(f"Could not decode image: {path}")
    if len(pixels.shape) == 2:
        pixels = sketchApi.cv2.cvtColor(pixels, sketchApi.cv2.COLOR_GRAY2RGBA)
    elif pixels.shape[2] == 3:
        pixels = sketchApi.cv2.cvtColor(pixels, sketchApi.cv2.COLOR_BGR2RGBA)
    else:
        pixels = sketchApi.cv2.cvtColor(pixels, sketchApi.cv2.COLOR_BGRA2RGBA)
    pixels = sketchApi.cv2.flip(pixels, 0)
    texture = Texture.create(size=(pixels.shape[1], pixels.shape[0]), colorfmt="rgba")
    texture.blit_buffer(pixels.tobytes(), colorfmt="rgba", bufferfmt="ubyte")
    return Image(texture=texture, fit_mode=fit_mode)


# ─────────────────────────────────────────────────────────────
#  WIDGET CLASSES
# ─────────────────────────────────────────────────────────────

class MainBox(MDBoxLayout):
    top_pad = NumericProperty(0)
    bottom_pad = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if platform == "android":
            try:
                from android.display_cutout import get_height_of_bar
                self.top_pad = int(get_height_of_bar('status'))
                self.bottom_pad = int(get_height_of_bar('navigation'))
            except Exception as e:
                print(f"Failed android 15 padding: {e}")
                self.top_pad = 32
                self.bottom_pad = 48


class TempSpinWait(MDBoxLayout):
    txt = StringProperty()


class VideoActionBtn(MDBoxLayout):
    pass


class PreferencesPop(MDScrollView):
    end_colour_icon = StringProperty("toggle-switch")
    end_colour_icon_colour = StringProperty("green")
    draw_hand_icon = StringProperty("toggle-switch")
    draw_hand_icon_colour = StringProperty("green")
    max_1080p_icon = StringProperty("toggle-switch")
    max_1080p_icon_colour = StringProperty("green")


class OldFileMgrBox(MDBoxLayout):
    pass


class ManageOldFilesScrl(MDScrollView):
    txt = StringProperty()


class OldFileItem(OneLineAvatarIconListItem):
    vid_file_name = StringProperty("")


class SectionHeader(MDBoxLayout):
    """Reusable colored section header used in the inspector panel."""
    icon = StringProperty("circle")
    icon_color = ColorProperty([0.7, 0.5, 1.0, 1])
    title = StringProperty("SECTION")
    title_color = ColorProperty([0.7, 0.5, 1.0, 1])


class TimelineSceneCard(MDCard):
    scene_id = StringProperty("")
    scene_title = StringProperty("")
    duration_text = StringProperty("4.0s")
    audio_icon = StringProperty("timer-outline")
    bg_color = ColorProperty([0.12, 0.10, 0.18, 1])
    border_color = ColorProperty([0.28, 0.22, 0.42, 1])
    border_width = NumericProperty(1.5)
    text_color = ColorProperty([0.9, 0.88, 1.0, 1])
    badge_color = ColorProperty([0.6, 0.6, 0.65, 1])

    def set_thumbnail(self, image_path):
        thumb_box = self.ids.thumb_container
        thumb_box.clear_widgets()
        if image_path and os.path.isfile(image_path):
            # KivyMD 1.2's stencil/card combination can crash the native GL
            # process when a newly uploaded texture is inserted here. Keep the
            # page strip stable and show the selected filename; the full image
            # remains visible on the large canvas above.
            thumb_box.add_widget(MDLabel(
                text=os.path.basename(image_path),
                halign="center",
                valign="middle",
                font_style="Caption",
                shorten=True,
                theme_text_color="Secondary",
            ))
        else:
            empty_icon = MDIconButton(
                icon="image-outline",
                theme_icon_color="Custom",
                icon_color=[0.35, 0.30, 0.5, 0.8],
                pos_hint={"center_x": 0.5, "center_y": 0.5},
            )
            thumb_box.add_widget(empty_icon)


class AddSceneCard(MDCard):
    pass


class WaveformWidget(Widget):
    clip_id = StringProperty("")
    points = ListProperty([])
    waveform_color = ColorProperty([0.15, 0.8, 0.5, 1])
    pixels_per_second = NumericProperty(40)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._redraw, size=self._redraw, points=self._redraw)

    def _redraw(self, *args):
        self.canvas.clear()
        with self.canvas:
            Color(*self.waveform_color)
            if not self.points:
                Line(points=[self.x, self.center_y, self.right, self.center_y], width=1)
                return
            step = self.width / max(1, len(self.points) - 1)
            coordinates = []
            for index, peak in enumerate(self.points):
                coordinates.extend((self.x + index * step, self.center_y + float(peak) * self.height * 0.42))
            Line(points=coordinates, width=1.1)
            coordinates = []
            for index, peak in enumerate(self.points):
                coordinates.extend((self.x + index * step, self.center_y - float(peak) * self.height * 0.42))
            Line(points=coordinates, width=1.1)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            app = MDApp.get_running_app()
            app.selected_audio_clip_id = self.clip_id
            _track, clip = find_clip(app.project.audio_tracks, self.clip_id)
            if clip:
                app.scrub_timeline(clip.start + (touch.x - self.x) / max(1.0, self.width) * clip.duration)
            touch.grab(self)
            touch.ud["audio_origin_x"] = touch.x
            touch.ud["audio_mode"] = (
                "trim_left" if touch.x <= self.x + dp(12)
                else "trim_right" if touch.x >= self.right - dp(12)
                else "move"
            )
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            delta = (touch.x - touch.ud["audio_origin_x"]) / self.pixels_per_second
            if abs(delta) >= 0.025:
                MDApp.get_running_app().adjust_audio_clip(self.clip_id, touch.ud["audio_mode"], delta)
                touch.ud["audio_origin_x"] = touch.x
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            MDApp.get_running_app().update_expanded_timeline_ui()
            return True
        return super().on_touch_up(touch)


class SceneTimelineBar(MDCard):
    scene_id = StringProperty("")
    pixels_per_second = NumericProperty(40)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        app = MDApp.get_running_app()
        app.select_scene_by_id(self.scene_id)
        touch.grab(self)
        touch.ud["resize_scene"] = touch.x >= self.right - dp(18)
        touch.ud["origin_x"] = touch.x
        touch.ud["origin_duration"] = next(s.effective_duration for s in app.scenes if s.id == self.scene_id)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is self and touch.ud.get("resize_scene"):
            duration = touch.ud["origin_duration"] + (touch.x - touch.ud["origin_x"]) / self.pixels_per_second
            MDApp.get_running_app().set_scene_duration(self.scene_id, duration, live=True)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            MDApp.get_running_app().refresh_studio_ui()
            return True
        return super().on_touch_up(touch)


# ─────────────────────────────────────────────────────────────
#  MAIN APPLICATION
# ─────────────────────────────────────────────────────────────

class DlImg2SktchApp(MDApp):
    timeline_expanded = BooleanProperty(False)
    playhead_time = NumericProperty(0.0)
    is_playing_timeline = BooleanProperty(False)
    split_len = NumericProperty(10)
    frame_rate = NumericProperty(25)
    obj_skip_rate = NumericProperty(8)
    bck_skip_rate = NumericProperty(14)
    main_img_duration = NumericProperty(2)
    fill_speed = NumericProperty(8)
    gap_px = NumericProperty(4)
    internal_storage = ObjectProperty()
    external_storage = ObjectProperty()
    video_dir = ObjectProperty()
    vid_download_path = StringProperty("")
    last_upload_path = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(on_keyboard=self.events)
        self.wake_lock = None
        self.project = Project()
        self.scenes = self.project.scenes
        self.current_scene_idx = 0
        self.selected_audio_clip_id = ""
        self.pending_media_target = None
        self.timeline_expanded = True
        self.playhead_time = 0.0
        self.is_playing_timeline = False
        self.timeline_clock = None
        self.current_sound = None
        self.is_processing = False
        self.export_progress_dialog = None

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "DeepPurple"
        self.theme_cls.accent_palette = "Amber"
        self.end_color = True
        self.draw_hand = True
        self.max_1080p = True
        self.old_file_mgr_open = False
        self.oldFileModal = None
        self.pref_dialog = None
        self.vid_player_position = None
        self.top_menu_items = {
            "New Project": {"icon": "file-plus", "action": "new", "url": ""},
            "Open Project": {"icon": "folder-open", "action": "openproject", "url": ""},
            "Save Project": {"icon": "content-save", "action": "save", "url": ""},
            "Save Project As": {"icon": "content-save-edit", "action": "saveas", "url": ""},
            "Download old sketches": {
                "icon": "download",
                "action": "oldfiles",
                "url": "",
            },
            "Delete old sketches": {
                "icon": "delete",
                "action": "clear",
                "url": "",
            },
            "Preferences": {
                "icon": "tune",
                "action": "pref",
                "url": "",
            },
            "Documentation": {
                "icon": "file-document-check",
                "action": "web",
                "url": "https://blog.daslearning.in/llm_ai/genai/image-to-animation.html",
            },
            "Contact Us": {
                "icon": "card-account-phone",
                "action": "web",
                "url": "https://daslearning.in/contact/",
            },
        }
        return Builder.load_file(kv_file_path)

    def on_start(self):
        file_m_height = 1
        if platform == "android":
            file_m_height = 0.9
            self.speed_map = {
                640: 20, 360: 10, 480: 10, 1280: 20, 720: 20,
                1920: 20, 1080: 20, 2560: 40, 1440: 20,
                3840: 40, 2160: 40
            }
            self.android_permissions = []
            all_android_permissions = [Permission.WAKE_LOCK]
            sdk_version = 28
            try:
                VERSION = autoclass('android.os.Build$VERSION')
                sdk_version = VERSION.SDK_INT
            except Exception as e:
                print(f"Android SDK version error: {e}")
            if sdk_version >= 33:
                self.android_permissions.extend(
                    [Permission.READ_MEDIA_IMAGES, Permission.READ_MEDIA_AUDIO]
                )
            else:
                self.android_permissions.extend(
                    [Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE]
                )
            all_android_permissions.extend(self.android_permissions)
            request_permissions(all_android_permissions)
            context = autoclass('org.kivy.android.PythonActivity').mActivity
            android_path = context.getExternalFilesDir(None).getAbsolutePath()
            self.video_dir = os.path.join(android_path, 'generated')
            self.internal_storage = android_path
            try:
                Environment = autoclass("android.os.Environment")
                self.external_storage = Environment.getExternalStorageDirectory().getAbsolutePath()
            except Exception:
                self.external_storage = os.path.abspath("/storage/emulated/0/")
        else:
            self.speed_map = {
                640: 10, 360: 10, 480: 10, 1280: 20, 720: 20,
                1920: 20, 1080: 20, 2560: 40, 1440: 20,
                3840: 40, 2160: 40
            }
            self.internal_storage = os.path.expanduser("~")
            self.external_storage = os.path.abspath("/")
            self.video_dir = os.path.join(self.user_data_dir, 'generated')

        os.makedirs(self.video_dir, exist_ok=True)
        self.project_dir = os.path.join(self.user_data_dir, "projects")
        os.makedirs(self.project_dir, exist_ok=True)
        self._configure_crash_logging()

        self.is_img_manager_open = False
        self.is_audio_manager_open = False
        self.is_vid_manager_open = False

        self.vid_file_manager = MDFileManager(
            exit_manager=self.vid_file_exit_manager,
            select_path=self.select_vid_path,
            selector="folder",
            size_hint_y=file_m_height,
        )
        self.media_file_manager = MDFileManager(
            exit_manager=self.close_media_file_manager,
            select_path=self.select_media_path,
            selector="file",
            size_hint_y=file_m_height,
        )

        # Speed dropdown
        self.split_len_drp = self.root.ids.split_len_drp
        self._build_speed_menu([5, 10, 15, 20, 25, 40])

        # Top-bar menu
        top_items = [
            {
                "text": menu_key,
                "leading_icon": self.top_menu_items[menu_key]["icon"],
                "on_release": lambda x=menu_key: self.top_menu_callback(x),
                "font_size": sp(14),
            }
            for menu_key in self.top_menu_items
        ]
        self.menu = MDDropdownMenu(
            items=top_items,
            width_mult=4,
        )
        self.pref_scroll = PreferencesPop()

        # Project already contains its first blank scene.
        self.refresh_studio_ui()

    def _configure_crash_logging(self):
        log_path = os.path.join(self.user_data_dir, "sketch_studio.log")
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        if not any(getattr(handler, "baseFilename", None) == os.path.abspath(log_path) for handler in root_logger.handlers):
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            root_logger.addHandler(file_handler)

        def handle_exception(exc_type, exc_value, exc_tb):
            logging.critical(
                "Unhandled application exception",
                exc_info=(exc_type, exc_value, exc_tb),
            )
            print("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))

        sys.excepthook = handle_exception
        logging.info("Sketch Studio started")

    # ── Speed menu helper ────────────────────────────────────

    def _build_speed_menu(self, speeds):
        menu_items = [
            {
                "text": f"Speed {s}",
                "on_release": lambda val=s: self.set_split_len(val),
                "font_size": sp(14),
            }
            for s in speeds
        ]
        self.split_len_options = MDDropdownMenu(
            caller=self.split_len_drp,
            items=menu_items,
            width_mult=2.5,
        )

    # ── Scene management ─────────────────────────────────────

    @property
    def current_scene(self):
        if 0 <= self.current_scene_idx < len(self.scenes):
            return self.scenes[self.current_scene_idx]
        return None

    def add_new_scene(self, image_path="", audio_path=""):
        new_scene = SceneData(
            image_path=image_path,
            audio_path=audio_path,
            custom_duration=4.0,
            split_len=self.split_len,
            end_color=self.end_color,
            draw_hand=self.draw_hand,
            max_1080p=self.max_1080p,
            object_skip_rate=self.obj_skip_rate,
            bg_object_skip_rate=self.bck_skip_rate,
            fill_speed=self.fill_speed,
            gap_px=self.gap_px,
            frame_rate=self.frame_rate,
        )
        self.scenes.append(new_scene)
        self.project.dirty = True
        self.current_scene_idx = len(self.scenes) - 1
        self.refresh_studio_ui()
        self.show_toast_msg(f"Added Scene {len(self.scenes)}")

    def select_scene_by_index(self, idx):
        if 0 <= idx < len(self.scenes):
            self.stop_audio_playback()
            self.current_scene_idx = idx
            self.refresh_studio_ui()

    def select_scene_by_id(self, scene_id):
        for idx, s in enumerate(self.scenes):
            if s.id == scene_id:
                self.select_scene_by_index(idx)
                break

    def prev_scene(self):
        if self.current_scene_idx > 0:
            self.select_scene_by_index(self.current_scene_idx - 1)

    def next_scene(self):
        if self.current_scene_idx < len(self.scenes) - 1:
            self.select_scene_by_index(self.current_scene_idx + 1)

    def delete_scene_by_id(self, scene_id):
        if len(self.scenes) <= 1:
            s = self.scenes[0]
            s.image_path = ""
            s.audio_path = ""
            s.audio_duration = 0.0
            s.rendered_video = None
            s.dirty = True
            self.project.dirty = True
            self.refresh_studio_ui()
            self.show_toast_msg("Scene 1 reset")
            return
        for idx, s in enumerate(self.scenes):
            if s.id == scene_id:
                self.stop_audio_playback()
                self.scenes.pop(idx)
                self.project.dirty = True
                if self.current_scene_idx >= len(self.scenes):
                    self.current_scene_idx = len(self.scenes) - 1
                self.refresh_studio_ui()
                self.show_toast_msg("Scene deleted")
                break

    def delete_current_scene(self):
        if self.current_scene:
            self.delete_scene_by_id(self.current_scene.id)

    def duplicate_current_scene(self):
        if not self.current_scene:
            return
        dup = self.current_scene.clone()
        self.scenes.insert(self.current_scene_idx + 1, dup)
        self.project.dirty = True
        self.current_scene_idx += 1
        self.refresh_studio_ui()
        self.show_toast_msg(f"Duplicated to Scene {self.current_scene_idx + 1}")

    def move_scene_left(self):
        idx = self.current_scene_idx
        if idx > 0:
            self.scenes[idx], self.scenes[idx - 1] = self.scenes[idx - 1], self.scenes[idx]
            self.current_scene_idx = idx - 1
            self.project.dirty = True
            self.refresh_studio_ui()

    def move_scene_right(self):
        idx = self.current_scene_idx
        if idx < len(self.scenes) - 1:
            self.scenes[idx], self.scenes[idx + 1] = self.scenes[idx + 1], self.scenes[idx]
            self.current_scene_idx = idx + 1
            self.project.dirty = True
            self.refresh_studio_ui()

    # ── UI refresh ───────────────────────────────────────────

    def refresh_studio_ui(self):
        self.update_inspector_ui()
        self.update_stage_ui()
        self.update_timeline_ui()

    def update_inspector_ui(self):
        scene = self.current_scene
        total = len(self.scenes)
        curr_num = self.current_scene_idx + 1

        self.root.ids.insp_scene_title.text = f"Scene {curr_num} of {total}"

        # Image info
        if scene and scene.image_path:
            name = os.path.basename(scene.image_path)
            self.root.ids.insp_img_name.text = name
            self.root.ids.insp_img_name.theme_text_color = "Primary"
        else:
            self.root.ids.insp_img_name.text = "No image selected"
            self.root.ids.insp_img_name.theme_text_color = "Hint"

        # Project-level master audio info
        master = self.project.master_track
        master_clip = master.clips[0] if master and master.clips else None
        if master_clip:
            name = os.path.basename(master_clip.source_path)
            self.root.ids.insp_audio_info.text = f"🎵  {name}  ({master_clip.duration:.1f}s master)"
            self.root.ids.insp_audio_info.theme_text_color = "Custom"
            self.root.ids.insp_audio_info.text_color = [0.2, 0.85, 0.5, 1]
            self.root.ids.btn_audio_play.disabled = False
            self.root.ids.btn_audio_remove.disabled = False
        else:
            self.root.ids.insp_audio_info.text = "No master audio — add an MP3 timeline"
            self.root.ids.insp_audio_info.theme_text_color = "Hint"
            self.root.ids.btn_audio_play.disabled = True
            self.root.ids.btn_audio_remove.disabled = True

        # Duration & speed
        eff_dur = scene.effective_duration if scene else 4.0
        self.root.ids.insp_duration_lbl.text = f"Duration: {eff_dur:.1f}s"
        sp_len = scene.split_len if scene else self.split_len
        self.root.ids.split_len_drp.text = f"Speed: {sp_len}"

    def update_stage_ui(self):
        player_box = self.root.ids.player_box
        # Safely teardown any existing VideoPlayer
        for child in list(player_box.children):
            if isinstance(child, VideoPlayer):
                try:
                    child.state = 'stop'
                    child.unload()
                except Exception:
                    pass
        player_box.clear_widgets()

        scene = self.current_scene
        curr_num = self.current_scene_idx + 1

        if not scene:
            return

        if scene.rendered_video and os.path.isfile(scene.rendered_video):
            self.root.ids.stage_status_lbl.text = f"Scene {curr_num}  —  Rendered Preview ✓"
            if platform == "android":
                btn = MDFillRoundFlatIconButton(
                    text="Play Preview",
                    icon="play-circle",
                    pos_hint={"center_x": 0.5, "center_y": 0.5},
                    on_release=lambda x: android_play_video(scene.rendered_video),
                )
                player_box.add_widget(btn)
            else:
                player = VideoPlayer(
                    source=scene.rendered_video,
                    options={'fit_mode': 'contain'},
                )
                player_box.add_widget(player)

        elif scene.image_path and os.path.isfile(scene.image_path):
            self.root.ids.stage_status_lbl.text = f"Scene {curr_num}  —  Ready to Render"
            try:
                player_box.add_widget(safe_local_image(scene.image_path, "contain"))
            except Exception as exc:
                logging.exception("Stage image decode failed")
                self.root.ids.stage_status_lbl.text = f"Scene {curr_num} — Image error: {exc}"

        else:
            self.root.ids.stage_status_lbl.text = f"Scene {curr_num}  —  Empty"
            self._build_empty_stage(player_box)

    def _build_empty_stage(self, parent):
        """Build a polished empty-state placeholder for the stage."""
        outer = MDBoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=dp(24),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        )
        icon_btn = MDIconButton(
            icon="image-plus",
            theme_icon_color="Custom",
            icon_color=[0.45, 0.32, 0.72, 0.7],
            pos_hint={"center_x": 0.5},
        )
        # Use font_size for the icon size (MDIconButton is an MDLabel subclass)
        icon_btn.font_size = sp(56)
        lbl = MDLabel(
            text="Upload an image to start this scene",
            halign="center",
            font_style="Body1",
            theme_text_color="Secondary",
            adaptive_height=True,
        )
        hint = MDLabel(
            text="Add an image, then attach an MP3 — Sketch Studio does the rest",
            halign="center",
            font_style="Caption",
            theme_text_color="Hint",
            adaptive_height=True,
        )
        upload_btn = MDFillRoundFlatIconButton(
            text="Upload Image",
            icon="image-plus",
            pos_hint={"center_x": 0.5},
            size_hint_x=None,
            width=dp(180),
            md_bg_color="#3B1F6E",
            on_release=lambda x: self.open_img_file_manager(),
        )
        outer.add_widget(icon_btn)
        outer.add_widget(lbl)
        outer.add_widget(hint)
        outer.add_widget(upload_btn)
        parent.add_widget(outer)

    def update_timeline_ui(self):
        strip = self.root.ids.timeline_strip
        strip.clear_widgets()

        total_dur = self.project.duration
        n = len(self.scenes)
        scene_word = "Scene" if n == 1 else "Scenes"
        self.root.ids.timeline_summary_lbl.text = (
            f"TIMELINE  —  {n} {scene_word}  (Total: {total_dur:.1f}s)"
        )

        for idx, scene in enumerate(self.scenes):
            is_active = (idx == self.current_scene_idx)
            media_name = os.path.basename(scene.image_path) if scene.image_path else "Blank scene"
            scene_button = Button(
                text=f"Scene {idx + 1}\n{media_name}\n{scene.effective_duration:.1f}s",
                size_hint=(None, None),
                size=(dp(145), dp(100)),
                background_normal="",
                background_color=[0.45, 0.22, 0.72, 1] if is_active else [0.20, 0.20, 0.24, 1],
                color=[1, 1, 1, 1],
                halign="center",
                valign="middle",
            )
            scene_button.bind(on_release=lambda _btn, sid=scene.id: self.select_scene_by_id(sid))
            strip.add_widget(scene_button)
            if idx < len(self.scenes) - 1:
                transition_btn = Button(
                    text="FADE" if scene.transition.kind == "fade" else "+",
                    size_hint=(None, None),
                    size=(dp(42), dp(100)),
                    background_normal="",
                    background_color=[0.16, 0.16, 0.19, 1],
                )
                transition_btn.bind(on_release=lambda _btn, sid=scene.id: self.toggle_scene_transition(sid))
                strip.add_widget(transition_btn)

        add_button = Button(
            text="+\nAdd scene",
            size_hint=(None, None),
            size=(dp(105), dp(100)),
            background_normal="",
            background_color=[0.25, 0.25, 0.29, 1],
        )
        add_button.bind(on_release=lambda _btn: self.add_new_scene())
        strip.add_widget(add_button)
        self.update_expanded_timeline_ui()

    def set_scene_duration(self, scene_id, duration, live=False):
        scene = next((item for item in self.scenes if item.id == scene_id), None)
        if not scene:
            return
        scene.set_duration(max(0.1, float(duration)))
        self.project.dirty = True
        if live:
            self.root.ids.timeline_summary_lbl.text = (
                f"TIMELINE — {len(self.scenes)} Scenes (Total: {self.project.duration:.1f}s)"
            )
        else:
            self.refresh_studio_ui()

    def adjust_current_scene_duration(self, delta):
        if self.current_scene:
            self.set_scene_duration(
                self.current_scene.id,
                self.current_scene.effective_duration + float(delta),
            )

    def toggle_scene_transition(self, scene_id):
        scene = next((item for item in self.scenes if item.id == scene_id), None)
        if scene:
            scene.transition.kind = "none" if scene.transition.kind == "fade" else "fade"
            scene.transition.duration = 0.0 if scene.transition.kind == "none" else 0.5
            scene.transition.normalize(scene.effective_duration)
            self.project.dirty = True
            self.refresh_studio_ui()

    def toggle_timeline(self):
        self.timeline_expanded = not self.timeline_expanded
        self.root.ids.expanded_panel.opacity = 1 if self.timeline_expanded else 0
        self.root.ids.expanded_panel.height = dp(190) if self.timeline_expanded else 0
        self.root.ids.timeline_root.height = dp(340) if self.timeline_expanded else dp(150)
        self.update_expanded_timeline_ui()

    def scrub_timeline(self, value, redraw=True):
        self.playhead_time = max(0.0, min(float(value), self.project.duration))
        index, _scene, _local = self.project.scene_at(self.playhead_time)
        if index != self.current_scene_idx:
            self.current_scene_idx = index
            self.update_stage_ui()
        if redraw:
            self.update_expanded_timeline_ui()
        elif self.root and "timeline_time_lbl" in self.root.ids:
            self.root.ids.timeline_time_lbl.text = f"{self.playhead_time:.1f} / {self.project.duration:.1f}s"

    def toggle_timeline_playback(self):
        if self.is_playing_timeline:
            self.is_playing_timeline = False
            if self.timeline_clock:
                self.timeline_clock.cancel()
                self.timeline_clock = None
            self.stop_audio_playback()
            return
        if self.project.audio_tracks:
            try:
                preview_path = os.path.join(self.user_data_dir, "timeline_preview.wav")
                write_mix_preview(self.project.snapshot(), preview_path, start_time=self.playhead_time)
                self.stop_audio_playback()
                if platform == "win":
                    self.current_sound = self._start_windows_audio(preview_path)
                else:
                    self.current_sound = SoundLoader.load(preview_path)
                    if self.current_sound:
                        self.current_sound.play()
            except Exception as exc:
                logging.exception("Timeline audio preview failed")
                self.show_toast_msg(f"Audio preview failed: {exc}", is_error=True)
        self.is_playing_timeline = True
        self.timeline_clock = Clock.schedule_interval(self._advance_playhead, 1 / 25.0)

    def _advance_playhead(self, dt):
        if not self.is_playing_timeline:
            return False
        next_time = self.playhead_time + dt
        if next_time >= self.project.duration:
            self.playhead_time = self.project.duration
            self.toggle_timeline_playback()
            self.update_expanded_timeline_ui()
            return False
        self.scrub_timeline(next_time, redraw=False)
        return True

    def update_expanded_timeline_ui(self):
        if not self.root or "expanded_tracks" not in self.root.ids:
            return
        tracks_box = self.root.ids.expanded_tracks
        tracks_box.clear_widgets()
        if not self.timeline_expanded:
            return
        pps = 40.0
        scene_row = MDBoxLayout(orientation="horizontal", size_hint=(None, None), height=dp(46), spacing=dp(2))
        scene_row.width = max(self.root.width - dp(150), self.project.duration * pps)
        for index, scene in enumerate(self.scenes):
            bar = SceneTimelineBar(
                scene_id=scene.id,
                pixels_per_second=pps,
                size_hint=(None, None),
                width=max(dp(36), scene.effective_duration * pps),
                height=dp(42),
                radius=[dp(6)],
                md_bg_color=[0.35, 0.18, 0.65, 1] if index == self.current_scene_idx else [0.22, 0.14, 0.38, 1],
            )
            bar.add_widget(MDLabel(text=f"Scene {index + 1}  {scene.effective_duration:.1f}s  ⇥", halign="center", font_style="Caption"))
            scene_row.add_widget(bar)
        tracks_box.add_widget(scene_row)

        for track in self.project.audio_tracks:
            row = MDBoxLayout(orientation="horizontal", size_hint=(None, None), height=dp(54), spacing=dp(4))
            row.width = max(self.root.width - dp(150), self.project.duration * pps)
            label = MDLabel(
                text=("MASTER" if track.role == "master" else track.name),
                size_hint=(None, 1), width=dp(74), font_style="Caption",
            )
            row.add_widget(label)
            mute = MDIconButton(
                icon="volume-off" if track.muted else "volume-high",
                size_hint=(None, None), size=(dp(28), dp(28)),
            )
            mute.bind(on_release=lambda _btn, tid=track.id: self.toggle_track_mute(tid))
            row.add_widget(mute)
            track_slider = Slider(
                min=0, max=2, value=track.volume, step=0.05,
                size_hint=(None, 1), width=dp(70),
            )
            track_slider.bind(value=lambda _slider, value, tid=track.id: self.set_track_volume(tid, value))
            row.add_widget(track_slider)
            cursor = 0.0
            for clip in sorted(track.clips, key=lambda item: item.start):
                gap = max(0.0, clip.start - cursor)
                if gap:
                    row.add_widget(Widget(size_hint=(None, 1), width=gap * pps))
                wave = WaveformWidget(
                    clip_id=clip.id,
                    points=clip.waveform,
                    size_hint=(None, 1),
                    width=max(dp(40), clip.duration * pps),
                )
                row.add_widget(wave)
                cursor = max(cursor, clip.end)
            tracks_box.add_widget(row)
        self.root.ids.timeline_time_lbl.text = f"{self.playhead_time:.1f} / {self.project.duration:.1f}s"

    def split_selected_audio(self):
        track, clip = find_clip(self.project.audio_tracks, self.selected_audio_clip_id)
        if not clip:
            self.show_toast_msg("Select an audio waveform first", is_error=True)
            return
        try:
            right = clip.split(self.playhead_time)
            track.clips.append(right)
            self.selected_audio_clip_id = right.id
            self.project.dirty = True
            self.update_expanded_timeline_ui()
        except ValueError as exc:
            self.show_toast_msg(str(exc), is_error=True)

    def set_selected_clip_volume(self, value):
        _track, clip = find_clip(self.project.audio_tracks, self.selected_audio_clip_id)
        if clip:
            clip.volume = max(0.0, min(2.0, float(value)))
            self.project.dirty = True

    def set_track_volume(self, track_id, value):
        track = next((item for item in self.project.audio_tracks if item.id == track_id), None)
        if track:
            track.volume = max(0.0, min(2.0, float(value)))
            self.project.dirty = True

    def toggle_track_mute(self, track_id):
        track = next((item for item in self.project.audio_tracks if item.id == track_id), None)
        if track:
            track.muted = not track.muted
            self.project.dirty = True
            self.update_expanded_timeline_ui()

    def nudge_selected_audio(self, delta):
        _track, clip = find_clip(self.project.audio_tracks, self.selected_audio_clip_id)
        if clip:
            clip.start = max(0.0, clip.start + float(delta))
            self.project.dirty = True
            self.update_expanded_timeline_ui()

    def adjust_audio_clip(self, clip_id, mode, delta):
        _track, clip = find_clip(self.project.audio_tracks, clip_id)
        if not clip:
            return
        delta = float(delta)
        if mode == "move":
            clip.start = max(0.0, clip.start + delta)
        elif mode == "trim_left":
            new_trim = max(0.0, min(clip.trim_out - 0.1, clip.trim_in + delta))
            applied = new_trim - clip.trim_in
            clip.trim_in = new_trim
            clip.start = max(0.0, clip.start + applied)
        elif mode == "trim_right":
            clip.trim_out = max(clip.trim_in + 0.1, min(clip.source_duration, clip.trim_out + delta))
        clip.normalize()
        self.project.dirty = True

    def delete_selected_audio(self):
        track, clip = find_clip(self.project.audio_tracks, self.selected_audio_clip_id)
        if track and clip:
            track.clips.remove(clip)
            if not track.clips:
                self.project.audio_tracks.remove(track)
                self.project.ensure_single_master()
            self.selected_audio_clip_id = ""
            self.project.dirty = True
            self.refresh_studio_ui()

    # ── File selection ───────────────────────────────────────

    def open_img_file_manager(self):
        try:
            if self.is_processing:
                return
            scene_id = self.current_scene.id if self.current_scene else ""
            self.pending_media_target = ("image", scene_id)
            if not self.last_upload_path or platform == "android":
                self.last_upload_path = self.external_storage
            if platform == "android":
                if not self.check_request_android_permission():
                    return
                filechooser.open_file(
                    on_selection=self.handle_img_selection,
                    path=self.last_upload_path,
                    multiple=False,
                    filters=[["*.JPG", "*.jpg", "*.png", "*.PNG", "*.jpeg", "*.JPEG", "*.webp"], "*"],
                    preview=True,
                )
            else:
                self.media_file_manager.ext = [".jpg", ".jpeg", ".png", ".webp"]
                self.media_file_manager.show(self.last_upload_path)
            self.is_img_manager_open = True
        except Exception as e:
            self.show_toast_msg(f"Error opening image chooser: {e}", is_error=True)

    def handle_img_selection(self, selection=None):
        self.is_img_manager_open = False
        if selection and selection[0]:
            img_path = str(selection[0])
            self.last_upload_path = os.path.dirname(img_path)
            target = self.pending_media_target
            self.pending_media_target = None
            Clock.schedule_once(lambda dt: self.apply_image_to_scene(img_path, target[1] if target else ""))

    def apply_image_to_scene(self, path, scene_id=""):
        scene = next((item for item in self.scenes if item.id == scene_id), self.current_scene)
        if not scene:
            return
        if not os.path.isfile(path) or not path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            self.show_toast_msg(f"Unsupported image format: {os.path.basename(path)}", is_error=True)
            return

        scene.image_path = path
        scene.rendered_video = None
        scene.dirty = True
        self.project.dirty = True

        # Calculate optimal split length for this image resolution
        try:
            resp = sketchApi.get_split_lens(path, self.max_1080p)
            split_lens = resp.get("split_lens", [])
            img_res = resp.get("image_res", [])
            if len(img_res) >= 2:
                max_dim = max(img_res[0], img_res[1])
                nearest_res = sketchApi.find_nearest_res(max_dim)
                scene.split_len = int(self.speed_map.get(nearest_res, 10))
            if split_lens:
                self._build_speed_menu(split_lens)
        except Exception as e:
            print(f"Split len calc error: {e}")

        self.refresh_studio_ui()
        self.show_toast_msg(f"Image added to Scene {self.current_scene_idx + 1}")

    def open_audio_file_manager(self):
        try:
            if self.is_processing:
                return
            self.pending_media_target = ("audio", "")
            if not self.last_upload_path or platform == "android":
                self.last_upload_path = self.external_storage
            if platform == "android":
                if not self.check_request_android_permission():
                    return
                filechooser.open_file(
                    on_selection=self.handle_audio_selection,
                    path=self.last_upload_path,
                    multiple=False,
                    filters=[["*.mp3", "*.MP3", "*.wav", "*.WAV", "*.m4a", "*.aac"], "*"],
                    preview=False,
                )
            else:
                self.media_file_manager.ext = [".mp3", ".wav", ".m4a", ".aac"]
                self.media_file_manager.show(self.last_upload_path)
            self.is_audio_manager_open = True
        except Exception as e:
            self.show_toast_msg(f"Error opening audio chooser: {e}", is_error=True)

    def handle_audio_selection(self, selection=None):
        self.is_audio_manager_open = False
        if selection and selection[0]:
            audio_path = str(selection[0])
            self.last_upload_path = os.path.dirname(audio_path)
            self.pending_media_target = None
            Clock.schedule_once(lambda dt: self.add_audio_file(audio_path))

    def select_media_path(self, path):
        target = self.pending_media_target
        self.close_media_file_manager()
        self.last_upload_path = os.path.dirname(path)
        if not target:
            return
        if target[0] == "image":
            Clock.schedule_once(lambda dt: self.apply_image_to_scene(path, target[1]))
        elif target[0] == "audio":
            Clock.schedule_once(lambda dt: self.add_audio_file(path))
        elif target[0] == "project":
            Clock.schedule_once(lambda dt: self.load_project(path))

    def close_media_file_manager(self, *args):
        try:
            self.media_file_manager.close()
        except Exception:
            pass
        self.is_img_manager_open = False
        self.is_audio_manager_open = False
        self.pending_media_target = None

    def add_audio_file(self, path):
        if not os.path.isfile(path) or not path.lower().endswith((".mp3", ".wav", ".m4a", ".aac")):
            self.show_toast_msg(
                f"Unsupported audio format: {os.path.basename(path)}", is_error=True
            )
            return
        try:
            info = get_audio_info(path)
            if info["duration"] <= 0:
                raise ValueError("The file has no readable audio duration")
            is_master = self.project.master_track is None
            track = self.project.add_audio_track(
                "Master Audio" if is_master else f"Audio {len(self.project.audio_tracks) + 1}",
                master=is_master,
            )
            clip = AudioClip(source_path=path, source_duration=info["duration"], trim_out=info["duration"])
            clip.waveform = generate_waveform(path)
            track.clips.append(clip)
            self.selected_audio_clip_id = clip.id
            self.project.dirty = True
            self.refresh_studio_ui()
            self.show_toast_msg(
                f"{'Master' if is_master else 'Overlay'} audio added ({info['duration']:.1f}s)"
            )
        except Exception as e:
            self.show_toast_msg(f"Audio error: {e}", is_error=True)

    # ── Audio playback ────────────────────────────────────────

    def toggle_audio_playback(self):
        if self.current_sound and (
            isinstance(self.current_sound, subprocess.Popen)
            or getattr(self.current_sound, "state", None) == "play"
        ):
            self.stop_audio_playback()
            return

        track = self.project.master_track
        clip = track.clips[0] if track and track.clips else None
        if clip and os.path.isfile(clip.source_path):
            try:
                self.stop_audio_playback()
                if platform == "win":
                    preview_path = os.path.join(self.user_data_dir, "timeline_preview.wav")
                    write_mix_preview(self.project.snapshot(), preview_path)
                    self.current_sound = self._start_windows_audio(preview_path)
                    self.root.ids.btn_audio_play.icon = "stop-circle"
                else:
                    sound = SoundLoader.load(clip.source_path)
                    if sound:
                        self.current_sound = sound
                        self.current_sound.play()
                        self.root.ids.btn_audio_play.icon = "stop-circle"
                        self.current_sound.bind(on_stop=self._on_sound_finished_thread_safe)
                    else:
                        self.show_toast_msg("Could not load audio file", is_error=True)
            except Exception as e:
                self.show_toast_msg(f"Audio playback error: {e}", is_error=True)

    def _on_sound_finished_thread_safe(self, *args):
        """
        Kivy's ffpyplayer backend fires `on_stop` on the audio thread.
        We MUST use Clock.schedule_once to update the UI on the main thread.
        """
        Clock.schedule_once(self._reset_audio_play_btn)

    def _reset_audio_play_btn(self, *args):
        try:
            self.root.ids.btn_audio_play.icon = "play-circle"
        except Exception:
            pass

    def stop_audio_playback(self):
        if self.current_sound:
            try:
                if isinstance(self.current_sound, subprocess.Popen):
                    self.current_sound.terminate()
                else:
                    self.current_sound.stop()
                    self.current_sound.unload()
            except Exception:
                pass
            self.current_sound = None
        try:
            self.root.ids.btn_audio_play.icon = "play-circle"
        except Exception:
            pass

    def _start_windows_audio(self, wav_path):
        script = "import sys,winsound; winsound.PlaySound(sys.argv[1], winsound.SND_FILENAME)"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.Popen(
            [sys.executable, "-c", script, wav_path],
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def remove_current_scene_audio(self):
        self.stop_audio_playback()
        track = self.project.master_track
        if track:
            self.project.audio_tracks.remove(track)
            self.project.ensure_single_master()
            self.project.dirty = True
            self.refresh_studio_ui()
            self.show_toast_msg("Master audio removed")

    # ── Speed / split len ────────────────────────────────────

    def open_split_len_menu(self):
        self.split_len_options.open()

    def set_split_len(self, value):
        sp_int = int(value)
        if self.current_scene:
            self.current_scene.split_len = sp_int
            self.current_scene.rendered_video = None
            self.current_scene.dirty = True
            self.project.dirty = True
        self.split_len = sp_int
        self.root.ids.split_len_drp.text = f"Speed: {sp_int}"
        self.split_len_options.dismiss()

    # ── Rendering engine ─────────────────────────────────────

    def render_current_scene(self):
        scene = self.current_scene
        if not scene or not scene.image_path or not os.path.isfile(scene.image_path):
            self.show_toast_msg("Upload an image for this scene first!", is_error=True)
            return

        if self.is_processing:
            self.show_toast_msg("Processing in progress…", is_error=True)
            return

        self.is_processing = True
        self.stop_audio_playback()

        # Show spinner in stage
        player_box = self.root.ids.player_box
        for child in list(player_box.children):
            if isinstance(child, VideoPlayer):
                try:
                    child.state = 'stop'
                    child.unload()
                except Exception:
                    pass
        player_box.clear_widgets()
        wait_widget = TempSpinWait(
            txt=f"Rendering Scene {self.current_scene_idx + 1} — sketch animation & audio…"
        )
        player_box.add_widget(wait_widget)

        # Snapshot the scene index so the closure captures it correctly
        scene_num = self.current_scene_idx + 1

        def worker():
            err = None
            try:
                render_scene_clip(
                    scene=scene,
                    output_dir=self.video_dir,
                    platform=platform,
                    progress_callback=lambda msg: Clock.schedule_once(
                        lambda dt: self.update_stage_status_text(msg)
                    ),
                )
            except Exception as e:
                import traceback
                err = str(e)
                print(f"Render error:\n{traceback.format_exc()}")

            def finish(dt):
                self.is_processing = False
                if err:
                    self.show_toast_msg(f"Render failed: {err}", is_error=True)
                    self.update_stage_ui()
                else:
                    self.show_toast_msg(f"Scene {scene_num} rendered successfully!")
                    self.refresh_studio_ui()

            Clock.schedule_once(finish)

        Thread(target=worker, daemon=True).start()

    def update_stage_status_text(self, text):
        try:
            self.root.ids.stage_status_lbl.text = text
        except Exception:
            pass

    def export_full_video(self):
        if not self.scenes:
            self.show_toast_msg("No scenes in project!", is_error=True)
            return

        for idx, s in enumerate(self.scenes):
            if not s.image_path or not os.path.isfile(s.image_path):
                self.show_toast_msg(f"Scene {idx + 1} has no image — please upload one.", is_error=True)
                return

        if self.is_processing:
            self.show_toast_msg("Export already in progress…", is_error=True)
            return

        self.is_processing = True
        self.stop_audio_playback()

        # Progress dialog
        self.export_progress_bar = MDProgressBar(value=0)
        self.export_status_lbl = MDLabel(
            text="Preparing scenes for export…",
            font_style="Caption",
            adaptive_height=True,
        )
        box = MDBoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=dp(16),
            adaptive_height=True,
        )
        box.add_widget(self.export_status_lbl)
        box.add_widget(self.export_progress_bar)

        self.export_dialog = MDDialog(
            title="Exporting Full Video",
            type="custom",
            content_cls=box,
            auto_dismiss=False,
        )
        self.export_dialog.open()

        now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        final_video_name = f"sketch_movie_{now}.mp4"
        final_output_path = os.path.join(self.video_dir, final_video_name)

        def worker():
            err = None
            try:
                def on_progress(msg, pct=0.0):
                    Clock.schedule_once(
                        lambda dt: self.update_export_dialog_progress(msg, pct)
                    )

                export_timeline_project(
                    project=self.project.snapshot(),
                    output_path=final_output_path,
                    output_dir=self.video_dir,
                    platform=platform,
                    progress_callback=on_progress,
                )
            except Exception as e:
                import traceback
                err = str(e)
                print(f"Export error:\n{traceback.format_exc()}")

            def finish(dt):
                self.is_processing = False
                if self.export_dialog:
                    self.export_dialog.dismiss()
                    self.export_dialog = None
                if err:
                    self.show_toast_msg(f"Export failed: {err}", is_error=True)
                else:
                    self.vid_download_path = final_output_path
                    self.show_toast_msg("Full video exported! 🎬")
                    self.display_master_video(final_output_path)

            Clock.schedule_once(finish)

        Thread(target=worker, daemon=True).start()

    def update_export_dialog_progress(self, msg, pct):
        try:
            if self.export_status_lbl:
                self.export_status_lbl.text = msg
            if self.export_progress_bar:
                self.export_progress_bar.value = int(pct * 100)
        except Exception:
            pass

    def display_master_video(self, video_path):
        player_box = self.root.ids.player_box
        for child in list(player_box.children):
            if isinstance(child, VideoPlayer):
                try:
                    child.state = 'stop'
                    child.unload()
                except Exception:
                    pass
        player_box.clear_widgets()
        self.root.ids.stage_status_lbl.text = "✅  Master Video Exported"

        if platform == "android":
            btn = MDFillRoundFlatIconButton(
                text="Play Full Video",
                icon="play-circle",
                pos_hint={"center_x": 0.5, "center_y": 0.5},
                on_release=lambda x: android_play_video(video_path),
            )
            player_box.add_widget(btn)
        else:
            player = VideoPlayer(
                source=video_path,
                options={'fit_mode': 'contain'},
            )
            player_box.add_widget(player)

        act_box = VideoActionBtn()
        player_box.add_widget(act_box)

    # ── Video save / download ─────────────────────────────────

    def open_vid_file_manager(self):
        try:
            self.vid_file_manager.show(self.external_storage)
            self.is_vid_manager_open = True
        except Exception as e:
            self.show_toast_msg(f"Error opening save location: {e}", is_error=True)

    def select_vid_path(self, path: str):
        if not self.vid_download_path or not os.path.isfile(self.vid_download_path):
            self.show_toast_msg("No video file to save!", is_error=True)
            self.vid_file_exit_manager()
            return
        filename = os.path.basename(self.vid_download_path)
        dest_path = os.path.join(path, filename)
        try:
            shutil.copyfile(self.vid_download_path, dest_path)
            self.show_toast_msg(f"Video saved → {dest_path}")
            self.vid_file_exit_manager()
        except Exception as e:
            self.show_toast_msg(f"Error saving video: {e}", is_error=True)

    def vid_file_exit_manager(self, *args):
        self.is_vid_manager_open = False
        self.vid_file_manager.close()

    def current_delete_alert(self):
        if not self.vid_download_path:
            return
        filename = os.path.basename(self.vid_download_path)
        self.show_text_dialog(
            title="Delete this Video?",
            text=f"Delete '{filename}'? This cannot be undone.",
            buttons=[
                MDFlatButton(text="CANCEL", on_release=self.txt_dialog_closer),
                MDFlatButton(
                    text="DELETE",
                    theme_text_color="Custom",
                    text_color="red",
                    on_release=self.confirm_delete_video,
                ),
            ],
        )

    def confirm_delete_video(self, instance):
        self.txt_dialog_closer(instance)
        if self.vid_download_path and os.path.exists(self.vid_download_path):
            try:
                os.remove(self.vid_download_path)
                self.vid_download_path = ""
                self.update_stage_ui()
                self.show_toast_msg("Video deleted.")
            except Exception as e:
                self.show_toast_msg(f"Error deleting video: {e}", is_error=True)

    # ── Top menu & preferences ────────────────────────────────

    def menu_bar_callback(self, button):
        self.menu.caller = button
        self.menu.open()

    def top_menu_callback(self, text_item):
        self.menu.dismiss()
        action = self.top_menu_items.get(text_item, {}).get("action", "")
        url = self.top_menu_items.get(text_item, {}).get("url", "")
        if action == "new":
            self.new_project()
        elif action == "openproject":
            self.open_project_picker()
        elif action == "save":
            self.save_project()
        elif action == "saveas":
            self.save_project(force_new=True)
        elif action == "web" and url:
            self.open_link(url)
        elif action == "pref":
            self.popup_preference()
        elif action == "clear":
            self.all_delete_alert()
        elif action == "oldfiles":
            self.show_old_file_mgr()

    def _confirm_discard(self, callback):
        if not self.project.dirty:
            callback()
            return
        dialog = MDDialog(
            title="Unsaved changes",
            text="Save the current project before continuing?",
            buttons=[
                MDFlatButton(text="CANCEL", on_release=lambda _btn: dialog.dismiss()),
                MDFlatButton(text="DISCARD", on_release=lambda _btn: (dialog.dismiss(), callback())),
                MDFlatButton(text="SAVE", on_release=lambda _btn: (self.save_project(), dialog.dismiss(), callback())),
            ],
        )
        dialog.open()

    def new_project(self, *args, force=False):
        if self.project.dirty and not force:
            self._confirm_discard(lambda: self.new_project(force=True))
            return
        self.stop_audio_playback()
        self.project = Project()
        self.scenes = self.project.scenes
        self.current_scene_idx = 0
        self.selected_audio_clip_id = ""
        self.playhead_time = 0.0
        self.refresh_studio_ui()
        self.show_toast_msg("New project created")

    def open_project_picker(self):
        if self.project.dirty:
            self._confirm_discard(self._open_project_picker_now)
            return
        self._open_project_picker_now()

    def _open_project_picker_now(self):
        if self.is_processing:
            return
        self.pending_media_target = ("project", "")
        self.media_file_manager.ext = [".sketchproj", ".json"]
        self.media_file_manager.show(self.project_dir)

    def save_project(self, force_new=False):
        try:
            path = self.project.project_path
            if force_new or not path:
                stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                path = os.path.join(self.project_dir, f"sketch_project_{stamp}.sketchproj")
            self.project.save(path)
            self.show_toast_msg(f"Project saved: {os.path.basename(path)}")
        except Exception as exc:
            logging.exception("Project save failed")
            self.show_toast_msg(f"Project save failed: {exc}", is_error=True)

    def load_project(self, path):
        try:
            loaded = Project.load(path)
            self.stop_audio_playback()
            self.project = loaded
            self.scenes = loaded.scenes
            self.current_scene_idx = 0
            self.selected_audio_clip_id = ""
            self.playhead_time = 0.0
            self.refresh_studio_ui()
            missing = sum(not os.path.isfile(s.image_path) for s in self.scenes)
            for track in self.project.audio_tracks:
                missing += sum(not os.path.isfile(c.source_path) for c in track.clips)
            message = "Project opened" if not missing else f"Project opened with {missing} missing media file(s)"
            self.show_toast_msg(message, is_error=bool(missing))
        except Exception as exc:
            logging.exception("Project load failed")
            self.show_toast_msg(f"Project load failed: {exc}", is_error=True)

    def on_request_close(self, *args):
        if self.project.dirty:
            self._confirm_discard(self.stop)
            return True
        return False

    def popup_preference(self):
        if not self.pref_dialog:
            self.pref_dialog = MDDialog(
                title="Studio Preferences",
                type="custom",
                content_cls=self.pref_scroll,
                buttons=[
                    MDFlatButton(
                        text="CLOSE",
                        theme_text_color="Custom",
                        text_color=self.theme_cls.primary_color,
                        on_release=self.close_preference,
                    )
                ],
            )
        self.pref_dialog.open()

    def close_preference(self, instance=None):
        if self.pref_dialog:
            self.pref_dialog.dismiss()

    def preference_toggle(self, instance, choice):
        if choice == "end_colour":
            self.end_color = not self.end_color
            self.pref_scroll.end_colour_icon = "toggle-switch" if self.end_color else "toggle-switch-off"
            self.pref_scroll.end_colour_icon_colour = "green" if self.end_color else "gray"
            for s in self.scenes:
                s.end_color = self.end_color
        elif choice == "draw_hand":
            self.draw_hand = not self.draw_hand
            self.pref_scroll.draw_hand_icon = "toggle-switch" if self.draw_hand else "toggle-switch-off"
            self.pref_scroll.draw_hand_icon_colour = "green" if self.draw_hand else "gray"
            for s in self.scenes:
                s.draw_hand = self.draw_hand
        elif choice == "max_1080p":
            self.max_1080p = not self.max_1080p
            self.pref_scroll.max_1080p_icon = "toggle-switch" if self.max_1080p else "toggle-switch-off"
            self.pref_scroll.max_1080p_icon_colour = "green" if self.max_1080p else "gray"
            for s in self.scenes:
                s.max_1080p = self.max_1080p

    # ── Saved videos manager ──────────────────────────────────

    def show_old_file_mgr(self):
        self.dismiss_old_file_mgr()
        total_vids = []
        if os.path.exists(self.video_dir):
            for filename in os.listdir(self.video_dir):
                if filename.endswith((".mp4", ".avi")):
                    total_vids.append(filename)

        if total_vids:
            self.old_file_mgr_open = True
            self.oldFileModal = ModalView(
                size_hint=(0.9, 0.8),
                background_color=[0.06, 0.04, 0.1, 0.97],
            )
            oldFileBox = OldFileMgrBox()
            oldFileScroll = ManageOldFilesScrl()
            kivyFileList = MDList(adaptive_height=True)
            oldFileCloseBtn = MDFlatButton(
                text="CLOSE",
                theme_text_color="Custom",
                text_color=self.theme_cls.primary_color,
                on_release=self.dismiss_old_file_mgr,
            )
            for vid in total_vids:
                item = OldFileItem()
                item.vid_file_name = vid
                kivyFileList.add_widget(item)
            oldFileScroll.add_widget(kivyFileList)
            oldFileBox.add_widget(oldFileScroll)
            oldFileBox.add_widget(oldFileCloseBtn)
            self.oldFileModal.add_widget(oldFileBox)
            self.oldFileModal.open()
        else:
            self.show_toast_msg("No saved videos found.")

    def dismiss_old_file_mgr(self, instance=None):
        if self.oldFileModal:
            self.oldFileModal.dismiss(force=True)
        self.old_file_mgr_open = False
        self.oldFileModal = None

    def old_file_action(self, instance, action, filename):
        src_file = os.path.join(self.video_dir, filename)
        if action == "download":
            self.vid_download_path = src_file
            self.open_vid_file_manager()
        elif action == "delete":
            try:
                os.remove(src_file)
                self.show_toast_msg(f"Deleted {filename}")
                self.show_old_file_mgr()
            except Exception as e:
                self.show_toast_msg(f"Error deleting: {e}", is_error=True)

    def all_delete_alert(self):
        self.show_text_dialog(
            title="Delete All Saved Videos?",
            text="This will permanently remove all generated video files from internal storage.",
            buttons=[
                MDFlatButton(text="CANCEL", on_release=self.txt_dialog_closer),
                MDFlatButton(
                    text="DELETE ALL",
                    theme_text_color="Custom",
                    text_color="red",
                    on_release=self.confirm_all_delete,
                ),
            ],
        )

    def confirm_all_delete(self, instance):
        self.txt_dialog_closer(instance)
        try:
            for f in os.listdir(self.video_dir):
                if f.endswith((".mp4", ".avi")):
                    os.remove(os.path.join(self.video_dir, f))
            self.show_toast_msg("All videos deleted.")
        except Exception as e:
            self.show_toast_msg(f"Error: {e}", is_error=True)

    # ── Dialogs & toasts ──────────────────────────────────────

    def show_text_dialog(self, title, text="", buttons=None):
        self.txt_dialog = MDDialog(
            title=title,
            text=text,
            buttons=buttons or [],
        )
        self.txt_dialog.open()

    def txt_dialog_closer(self, instance=None):
        if hasattr(self, 'txt_dialog') and self.txt_dialog:
            self.txt_dialog.dismiss()

    def show_toast_msg(self, message, is_error=False, duration=3):
        try:
            from kivymd.uix.snackbar import MDSnackbar
            bg_color = (0.08, 0.48, 0.25, 1) if not is_error else (0.72, 0.15, 0.15, 1)
            MDSnackbar(
                MDLabel(text=message, font_style="Body2"),
                md_bg_color=bg_color,
                y=dp(28),
                pos_hint={"center_x": 0.5},
                duration=duration,
            ).open()
        except Exception:
            print(f"[Toast] {message}")

    def open_link(self, url):
        import webbrowser
        webbrowser.open(url)

    # ── Keyboard events ───────────────────────────────────────

    def events(self, instance, keyboard, keycode, text_input, modifiers):
        global video_view
        if keyboard == 32:
            self.toggle_timeline_playback()
            return True
        if keyboard in (83, 115):
            self.split_selected_audio()
            return True
        if keyboard in (1001, 27):
            if self.is_img_manager_open or self.is_audio_manager_open or self.pending_media_target:
                self.close_media_file_manager()
                return True
            if self.is_vid_manager_open:
                self.vid_file_exit_manager()
                return True
            if self.old_file_mgr_open and self.oldFileModal:
                self.dismiss_old_file_mgr()
                return True
            if platform == "android" and video_view:
                remove_video_android()
                return True
            return True  # Consume Escape/Back — never exit accidentally
        return False

    def check_request_android_permission(self):
        if platform == "android":
            permission_flag = True
            for permission in self.android_permissions:
                if not check_permission(permission):
                    permission_flag = False
                    break
            if not permission_flag:
                request_permissions(self.android_permissions)
            return permission_flag
        return True


if __name__ == "__main__":
    DlImg2SktchApp().run()

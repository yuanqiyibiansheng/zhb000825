import os
import threading
from beatrice_python_sample.cui.frontend import Frontend
from beatrice_python_sample.cui.realtime_vc import ReailtimeVC
from textual import on
from textual.app import ComposeResult
from textual.widgets import Header, Button, Label, Select
from beatrice_python_sample.cui.shortcut_setting import ShortcutList
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from beatrice_python_sample.audio_device import AudioDevice
from beatrice_python_sample.cui.config import Config
from beatrice_python_sample.cui.custom_footer import CustomFooter
from beatrice_python_sample.const import VERSION

Title = f"Beatrice v2 realtime voice changer cui (ver.{VERSION})"


def load_shortcut_settings():
    shortcuts = [
        {"command": "ctrl+c", "function": "dummy", "description": "NOOP"},
        {"command": "q", "function": "quit", "description": "Quit"},
        {"command": "right", "function": "increase_pitch_shift", "description": "increase pitch shift"},
        {"command": "left", "function": "decrease_pitch_shift", "description": "decrease_pitch_shift"}
    ]

    if os.path.exists("shortcut.json"):
        shortcut_setting = ShortcutList.model_validate_json(open("shortcut.json").read())
        not_changed = ["ctrl+c", "q", "right", "left"]
        shortcut_setting_valid = [shortcut for shortcut in shortcut_setting.shortcuts if
                                  shortcut.command not in not_changed]
        shortcuts.extend(shortcut_setting_valid)
        shortcut_setting = ShortcutList(shortcuts=shortcuts)
    else:
        shortcuts.extend([
            {"command": "1", "function": "set_speaker(1,0)", "description": ""},
            {"command": "2", "function": "set_speaker(2,0)", "description": ""},
            {"command": "3", "function": "set_speaker(3,0)", "description": ""},
            {"command": "4", "function": "set_speaker(4,0)", "description": ""},
            {"command": "5", "function": "set_speaker(5,0)", "description": ""},
            {"command": "6", "function": "set_speaker(6,0)", "description": ""},
            {"command": "7", "function": "set_speaker(7,0)", "description": ""},
            {"command": "8", "function": "set_speaker(8,0)", "description": ""},
            {"command": "9", "function": "set_speaker(9,0)", "description": ""}
        ])
        shortcut_setting = ShortcutList(shortcuts=shortcuts)
        with open("shortcut.json", "w") as f:
            f.write(shortcut_setting.model_dump_json(indent=4))

    return [(shortcut.command, shortcut.function, shortcut.description) for shortcut in shortcut_setting.shortcuts]


class ReactiveLabel(Label):
    text = reactive("", always_update=True)

    def render(self):
        return f"{self.text}"


class CuiFront(Frontend):
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = load_shortcut_settings()

    def __init__(self, audio_input_devices, audio_output_devices):
        super().__init__(
            css_path='front.css',
            #watch_css=watch_css
        )
        self.audio_input_devices = audio_input_devices
        self.audio_output_devices = audio_output_devices

    def compose(self) -> ComposeResult:
        conf = Config.get_instance()
        header = Header(show_clock=True)
        header.app.title = Title
        yield header

        main_control = Horizontal(
            Button("Start", id="start", classes="field-button"),
            Button("Stop", id="stop", classes="field-button"),
            classes="main-control"
        )
        main_control.border_title = "Main Control"
        yield main_control

        speaker_setting = Vertical(
            Horizontal(
                Label("Voice", classes="field-name"),
                Select(
                    ((str(voice_id), voice_id) for voice_id in range(0, 100)),
                    allow_blank=False,
                    value=conf.dst_sid,
                    id="voice_selector",
                    classes="field-select"
                ),
                classes="one-line-horizontal",
                id="voice_selector_container"
            ),
            Horizontal(
                Label("Pitch Shift", classes="field-name"),
                Button("<<", classes="arrow-button", id="pitch-shift-dec"),
                ReactiveLabel(f"{Config.get_instance().pitch_shift}", id="pitch-shift-val", classes="arrowed-value"),
                Button(">>", classes="arrow-button", id="pitch-shift-inc"),
                classes="one-line-horizontal",
                id="pitch-shift-input-container"
            ),
            Horizontal(
                Label("Formant Shift", classes="field-name"),
                Button("<<", classes="arrow-button", id="formant-shift-dec"),
                ReactiveLabel(f"{Config.get_instance().pitch_shift}", id="formant-shift-val", classes="arrowed-value"),
                Button(">>", classes="arrow-button", id="formant-shift-inc"),
                classes="one-line-horizontal",
                id="formant-shift-input-container"
            ),
            classes="speaker_setting"
        )
        speaker_setting.border_title = "[b]Speaker Setting[/b]"
        yield speaker_setting

        audio_input_device_options = [
            (f"[{input_device.host_api}] {input_device.name}", input_device.index)
            for input_device in self.audio_input_devices
        ]
        audio_input_device_options.insert(0, ("not selected", -1))

        audio_output_device_options = [
            (f"[{output_device.host_api}] {output_device.name}", output_device.index)
            for output_device in self.audio_output_devices
        ]
        audio_output_device_options.insert(0, ("not selected", -1))

        device_setting = Vertical(
            Horizontal(
                Label("Input", classes="field-name"),
                Select(
                    audio_input_device_options,
                    allow_blank=False,
                    value=conf.input_device,
                    id="input_device_selector",
                    classes="field-device-select"
                ),
                classes="one-line-horizontal",
                id="input-device-container"
            ),
            Horizontal(
                Label("Output", classes="field-name"),
                Select(
                    audio_output_device_options,
                    allow_blank=False,
                    value=conf.output_device,
                    id="output_device_selector",
                    classes="field-device-select"
                ),
                classes="one-line-horizontal",
                id="output-device-container"
            ),
            classes="device_setting"
        )
        device_setting.border_title = "[b]Device and Gain Setting[/b]"
        yield device_setting

        yield CustomFooter()

    def on_mount(self):
        self.query_one("#pitch-shift-val", ReactiveLabel).text = str(Config.get_instance().pitch_shift)
        self.query_one("#formant-shift-val", ReactiveLabel).text = str(Config.get_instance().formant_shift)
        self.set_start_button_color()

    @on(Button.Pressed, "#start")
    def start_button_pressed(self, event):
        Config.get_instance().started = True
        self.set_start_button_color()
        self.vc = ReailtimeVC(self.audio_input_devices, self.audio_output_devices)
        threading.Thread(target=self.vc.start, args=(self,)).start()

    def notify_exception_end(self, mess):
        self.notify(f"realtime vc exception:{str(mess)}", timeout=8, severity="error")

    @on(Button.Pressed, "#stop")
    def stop_button_pressed(self, event):
        Config.get_instance().started = False
        self.set_start_button_color()

    def set_start_button_color(self):
        if Config.get_instance().started:
            self.query_one("#start", Button).add_class("active")
            self.query_one("#stop", Button).remove_class("active")
        else:
            self.query_one("#start", Button).remove_class("active")
            self.query_one("#stop", Button).add_class("active")

    @on(Select.Changed, "#voice_selector")
    def voice_selector_changed(self, event):
        Config.get_instance().dst_sid = event.value

    @on(Button.Pressed, "#pitch-shift-dec")
    def pitch_shift_dec_button_pressed(self, event):
        if Config.get_instance().pitch_shift > -20:
            Config.get_instance().pitch_shift -= 1
            self.query_one("#pitch-shift-val", ReactiveLabel).text = str(Config.get_instance().pitch_shift)

    @on(Button.Pressed, "#pitch-shift-inc")
    def pitch_shift_inc_button_pressed(self, event):
        if Config.get_instance().pitch_shift < 20:
            Config.get_instance().pitch_shift += 1
            self.query_one("#pitch-shift-val", ReactiveLabel).text = str(Config.get_instance().pitch_shift)

    @on(Button.Pressed, "#formant-shift-dec")
    def formant_shift_dec_button_pressed(self, event):
        if Config.get_instance().formant_shift > -2:
            Config.get_instance().formant_shift -= 0.5
            self.query_one("#formant-shift-val", ReactiveLabel).text = str(Config.get_instance().formant_shift)

    @on(Button.Pressed, "#formant-shift-inc")
    def formant_shift_inc_button_pressed(self, event):
        if Config.get_instance().formant_shift < 2:
            Config.get_instance().formant_shift += 0.5
            self.query_one("#formant-shift-val", ReactiveLabel).text = str(Config.get_instance().formant_shift)

    @on(Select.Changed, "#input_device_selector")
    def input_device_selector_changed(self, event):
        if Config.get_instance().started is True:
            self.notify("Please stop before changing the device", timeout=2, severity="error")
            event.select.value = Config.get_instance().input_device
        else:
            Config.get_instance().input_device = event.value

    @on(Select.Changed, "#output_device_selector")
    def output_device_selector_changed(self, event):
        if Config.get_instance().started is True:
            self.notify("Please stop before changing the device", timeout=2, severity="error")
            event.select.value = Config.get_instance().output_device
        else:
            Config.get_instance().output_device = event.value

    def action_quit(self):
        Config.get_instance().started = False
        self.exit()

    def action_dummy(self):
        self.notify("push 'q' to quit.", timeout=2)

    def action_set_speaker(self, dst_sid: int, pitch_shift: int):
        Config.get_instance().dst_sid = dst_sid
        self.query_one("#voice_selector", Select).value = dst_sid
        Config.get_instance().pitch_shift = pitch_shift
        self.query_one("#pitch-shift-val", ReactiveLabel).text = str(Config.get_instance().pitch_shift)

    def action_increase_pitch_shift(self):
        if Config.get_instance().pitch_shift < 20:
            Config.get_instance().pitch_shift += 1
            self.query_one("#pitch-shift-val", ReactiveLabel).text = str(Config.get_instance().pitch_shift)

    def action_decrease_pitch_shift(self):
        if Config.get_instance().pitch_shift > -20:
            Config.get_instance().pitch_shift -= 1
            self.query_one("#pitch-shift-val", ReactiveLabel).text = str(Config.get_instance().pitch_shift)
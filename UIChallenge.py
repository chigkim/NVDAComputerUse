# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=2.32.0",
#     "pillow>=12.2.0",
#     "python-dotenv>=1.2.2",
#     "wxpython>=4.2.5",
# ]
# ///

import wx
import wx.grid
import wx.lib.newevent
import datetime
import uuid
import os
import json
import base64
import ctypes
import ctypes.wintypes
import io
import threading
import time
import argparse
from enum import IntEnum
from dataclasses import dataclass
from PIL import ImageGrab
from openai import OpenAI
import dotenv

dotenv.load_dotenv()

# ---------------------------------------------------------------------------
# Win32 Constants & Ctypes
# ---------------------------------------------------------------------------

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000

VK = {
    "alt": 0x12, "backspace": 0x08, "ctrl": 0x11, "control": 0x11, "delete": 0x2E,
    "down": 0x28, "end": 0x23, "enter": 0x0D, "escape": 0x1B, "esc": 0x1B,
    "home": 0x24, "insert": 0x2D, "left": 0x25, "meta": 0x5B, "pagedown": 0x22,
    "page_down": 0x22, "pageup": 0x21, "page_up": 0x21, "right": 0x27, "shift": 0x10,
    "space": 0x20, "tab": 0x09, "up": 0x26, "win": 0x5B, "windows": 0x5B,
    "cmd": 0x5B, "command": 0x5B,
}
for i in range(1, 25):
    VK[f"f{i}"] = 0x6F + i

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.wintypes.DWORD),
        ("wParamL", ctypes.wintypes.WORD),
        ("wParamH", ctypes.wintypes.WORD),
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", ctypes.wintypes.DWORD), ("union", INPUT_UNION)]

def set_dpi_awareness() -> None:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

@dataclass
class Capture:
    image_url: str
    left: int
    top: int
    width: int
    height: int
    image_width: int
    image_height: int

    def to_screen(self, x, y) -> tuple[int, int]:
        x_scale = self.width / self.image_width if self.image_width else 1.0
        y_scale = self.height / self.image_height if self.image_height else 1.0
        return self.left + int(float(x) * x_scale), self.top + int(float(y) * y_scale)

def logical_window_size(hwnd: int, physical_width: int, physical_height: int) -> tuple[int, int]:
    dpi = 96
    try:
        dpi = int(ctypes.windll.user32.GetDpiForWindow(hwnd))
    except Exception:
        pass
    if dpi <= 0:
        dpi = 96
    scale = dpi / 96.0
    return max(1, round(physical_width / scale)), max(1, round(physical_height / scale))

def capture_window(hwnd: int) -> Capture:
    rect = ctypes.wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("Could not get test app window rectangle.")

    left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
    if right <= left or bottom <= top:
        raise RuntimeError("Invalid test app window rectangle.")

    physical_width = right - left
    physical_height = bottom - top
    target_width, target_height = logical_window_size(hwnd, physical_width, physical_height)

    image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    if image.width != target_width or image.height != target_height:
        image = image.resize((target_width, target_height))
    
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    
    return Capture(
        image_url=image_url,
        left=left,
        top=top,
        width=physical_width,
        height=physical_height,
        image_width=image.width,
        image_height=image.height,
    )

def type_text(text: str) -> None:
    for char in text:
        send_unicode(char)

def send_unicode(char: str) -> None:
    if ord(char) > 0xFFFF:
        data = char.encode("utf-16-le", "surrogatepass")
        for index in range(0, len(data), 2):
            send_unicode(chr(int.from_bytes(data[index:index + 2], "little")))
        return
    extra = ctypes.c_ulong(0)
    input_down = INPUT()
    input_down.type = 1
    input_down.ki = KEYBDINPUT(0, ord(char), KEYEVENTF_UNICODE, 0, ctypes.pointer(extra))
    input_up = INPUT()
    input_up.type = 1
    input_up.ki = KEYBDINPUT(0, ord(char), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))
    ctypes.windll.user32.SendInput(1, ctypes.pointer(input_down), ctypes.sizeof(input_down))
    ctypes.windll.user32.SendInput(1, ctypes.pointer(input_up), ctypes.sizeof(input_up))

def key_code(key) -> int | None:
    normalized = str(key).lower().replace("+", "").replace("arrow", "")
    if normalized == "return":
        normalized = "enter"
    if len(normalized) == 1:
        return ctypes.windll.user32.VkKeyScanW(ctypes.c_wchar(normalized)) & 0xFF
    return VK.get(normalized)

def press_key(key) -> None:
    code = key_code(key)
    if code is None:
        if isinstance(key, str):
            type_text(key)
        return
    ctypes.windll.user32.keybd_event(code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)

class held_keys:
    def __init__(self, keys):
        if keys is None: keys = []
        if isinstance(keys, str): keys = [keys]
        self.codes = [key_code(key) for key in keys if key_code(key) is not None]

    def __enter__(self):
        for code in self.codes:
            ctypes.windll.user32.keybd_event(code, 0, 0, 0)

    def __exit__(self, exc_type, exc, tb):
        for code in reversed(self.codes):
            ctypes.windll.user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)

def mouse_down(button: str) -> None:
    flag = {
        "left": MOUSEEVENTF_LEFTDOWN, "right": MOUSEEVENTF_RIGHTDOWN, "middle": MOUSEEVENTF_MIDDLEDOWN,
    }.get(str(button).lower(), MOUSEEVENTF_LEFTDOWN)
    ctypes.windll.user32.mouse_event(flag, 0, 0, 0, 0)

def mouse_up(button: str) -> None:
    flag = {
        "left": MOUSEEVENTF_LEFTUP, "right": MOUSEEVENTF_RIGHTUP, "middle": MOUSEEVENTF_MIDDLEUP,
    }.get(str(button).lower(), MOUSEEVENTF_LEFTUP)
    ctypes.windll.user32.mouse_event(flag, 0, 0, 0, 0)

def mouse_click(button: str) -> None:
    mouse_down(button)
    mouse_up(button)

def click(action: dict, capture: Capture, count: int) -> None:
    x, y = capture.to_screen(action.get("x", 0), action.get("y", 0))
    button = action.get("button", "left")
    keys = action.get("keys", action.get("modifiers", []))
    with held_keys(keys):
        ctypes.windll.user32.SetCursorPos(x, y)
        for _ in range(count):
            mouse_click(button)

def drag(action: dict, capture: Capture) -> None:
    path = action.get("path", [])
    if len(path) < 2: return
    first_x, first_y = path[0].get("x", 0), path[0].get("y", 0)
    x, y = capture.to_screen(first_x, first_y)
    ctypes.windll.user32.SetCursorPos(x, y)
    mouse_down("left")
    try:
        for item in path[1:]:
            px, py = item.get("x", 0), item.get("y", 0)
            x, y = capture.to_screen(px, py)
            ctypes.windll.user32.SetCursorPos(x, y)
            time.sleep(0.04)
    finally:
        mouse_up("left")

def scroll(action: dict, capture: Capture) -> None:
    x = action.get("x")
    y = action.get("y")
    if x is not None and y is not None:
        ctypes.windll.user32.SetCursorPos(*capture.to_screen(x, y))
    
    scroll_y = int(action.get("scrollY", action.get("scroll_y", action.get("dy", 0))))
    scroll_x = int(action.get("scrollX", action.get("scroll_x", action.get("dx", 0))))
    
    if scroll_y:
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, -scroll_y, 0)
    if scroll_x:
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_HWHEEL, 0, 0, scroll_x, 0)

def perform_action(action: dict, capture: Capture) -> str:
    action_type = action.get("type", action.get("action", ""))
    target = action.get("target", "unknown")
    
    if action_type == "click":
        x, y = action.get("x", 0), action.get("y", 0)
        click(action, capture, 1)
        return f"Clicked '{target}' at ({x}, {y})"
    elif action_type == "double_click":
        x, y = action.get("x", 0), action.get("y", 0)
        click(action, capture, 2)
        return f"Double clicked '{target}' at ({x}, {y})"
    elif action_type == "triple_click":
        x, y = action.get("x", 0), action.get("y", 0)
        click(action, capture, 3)
        return f"Triple clicked '{target}' at ({x}, {y})"
    elif action_type == "move":
        x, y = action.get("x", 0), action.get("y", 0)
        capture_x, capture_y = capture.to_screen(x, y)
        ctypes.windll.user32.SetCursorPos(capture_x, capture_y)
        return f"Moved to '{target}' at ({x}, {y})"
    elif action_type == "drag":
        drag(action, capture)
        return f"Dragged '{target}'"
    elif action_type == "scroll":
        scroll(action, capture)
        return f"Scrolled '{target}'"
    elif action_type == "keypress":
        keys = action.get("keys", [])
        if isinstance(keys, str): keys = [keys]
        with held_keys(keys[:-1]):
            if keys: press_key(keys[-1])
        return f"Pressed keys for '{target}': {keys}"
    elif action_type == "type":
        text = action.get("text", "")
        type_text(text)
        return f"Typed text into '{target}': {text}"
    elif action_type == "wait":
        duration = action.get("duration_ms", 1000) / 1000.0
        time.sleep(max(0.1, duration))
        return f"Waited for '{target}' ({duration}s)"
    elif action_type == "screenshot":
        return "Screenshot requested"
    elif action_type == "cursor_position":
        return "Cursor position recorded"
    else:
        return f"Unknown action: {action_type}"

def describe_action(action: dict) -> str:
    action_type = action.get("type", action.get("action", ""))
    target = action.get("target", "")
    
    if action_type == "type":
        text = action.get("text", "")
        return f"Type '{text}' into '{target}'"
    elif action_type in ["click", "double_click", "triple_click", "move"]:
        x, y = action.get("x", 0), action.get("y", 0)
        return f"{action_type.capitalize()} '{target}' at ({x}, {y})"
    
    target_str = f" '{target}'" if target else ""
    return f"{action_type.capitalize()}{target_str}"

# ---------------------------------------------------------------------------
# UI Challenge App Logic
# ---------------------------------------------------------------------------

LevelChangedEvent, EVT_LEVEL_CHANGED = wx.lib.newevent.NewEvent()
LogEvent, EVT_LOG = wx.lib.newevent.NewEvent()
ComputerUseStatusEvent, EVT_CU_STATUS = wx.lib.newevent.NewEvent()

class LevelID(IntEnum):
    ACCEPT_CHALLENGE = 0
    TEXT_ENTRY = 1
    MODAL_TASK = 2
    SELECTION_CONTROLS = 3
    TABLE_LIST = 4
    NUMERIC_CONTROLS = 5
    CONTEXT_MENU = 6
    KEYBOARD_SHORTCUT = 7
    TEXT_EDITING = 8
    SCROLL_TASK = 9
    POINTER_TASK = 10
    STRESS = 11
    SUMMARY = 12

    @property
    def number(self): return self.value + 1

    @property
    def title(self):
        titles = [
            "Accept Challenge", "Text Entry", "Modal Task", "Selection Controls",
            "Table and List", "Numeric Controls", "Context Menu", "Keyboard Shortcut",
            "Text Editing", "Scroll", "Pointer Actions", "Stress", "Results Summary"
        ]
        return titles[self.value]

    @property
    def instruction(self):
        instructions = [
            "Enable the 'I Accept Challenge' toggle, then click Next.",
            "Type launch code delta-42 in the Message field, click Send, then click Next.",
            "Open the approval sheet, type Rivera in the reviewer field, choose Approve, confirm the sheet, then click Next.",
            "Choose Charlie from the popup menu, choose Three in the radio group, enable the checkbox, then click Next.",
            "Select table cell 13 and list row Gamma, then click Next.",
            "Set the slider between 70 and 80 and the stepper between 3 and 5, then click Next.",
            "Right-click the Context Target and choose Archive, then click Next.",
            "Click Start Shortcut Capture, press Command+Shift+M in the shortcut test area, then click Next.",
            "In the notes editor, make the text exactly: Alpha beta gamma. Then double-click the Word Target and triple-click the Paragraph Target before clicking Next.",
            "Scroll the list, click Hidden Target 18, then click Next.",
            "Drag the Drag Source onto the Drop Target, then click Next.",
            "Set the popup to Delta, type final check in the small field, select cell 24, enable Ready, click the lower Confirm button, then click Next.",
            "Review your overall performance in the UI Challenge."
        ]
        return instructions[self.value]

class ActionLogger:
    def __init__(self, target_window):
        self.target_window = target_window
        self.entries = []

    def log(self, category, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        entry = f"[{timestamp}] {category}: {message}"
        self.entries.append(entry)
        if len(self.entries) > 500:
            self.entries.pop(0)
        
        evt = LogEvent(category=category, message=message, timestamp=timestamp, full_log="\n".join(self.entries) + "\n")
        if self.target_window:
            wx.PostEvent(self.target_window, evt)
        print(entry)

    def clear(self):
        self.entries = []
        self.log("Log", "Cleared")

    def full_text(self):
        return "\n".join(self.entries)

class LevelController:
    def __init__(self, logger):
        self.logger = logger
        self.current_level = LevelID.ACCEPT_CHALLENGE
        self.test_results = {}
        self.reset_all_state()

    def reset_all_state(self):
        self.challenge_accepted = False
        self.message_text = ""
        self.message_sent = False
        self.selected_popup = "Alpha"
        self.selected_radio = "One"
        self.checkbox_enabled = False
        self.slider_value = 50
        self.stepper_value = 0
        self.scroll_target_clicked = False
        self.modal_reviewer = ""
        self.modal_decision = "Review"
        self.modal_confirmed = False
        self.context_choice = ""
        self.notes_text = ""
        self.word_double_clicked = False
        self.paragraph_triple_clicked = False
        self.selected_cell = None
        self.selected_list_row = ""
        self.shortcut_pressed = ""
        self.drop_received = False
        self.stress_popup = "Alpha"
        self.stress_text = ""
        self.stress_cell = None
        self.stress_ready = False
        self.stress_lower_confirm_clicked = False
        self.update_results()

    def reset_current_level(self):
        l = self.current_level
        if l == LevelID.ACCEPT_CHALLENGE: self.challenge_accepted = False
        elif l == LevelID.TEXT_ENTRY: self.message_text = ""; self.message_sent = False
        elif l == LevelID.MODAL_TASK: self.modal_reviewer = ""; self.modal_decision = "Review"; self.modal_confirmed = False
        elif l == LevelID.SELECTION_CONTROLS: self.selected_popup = "Alpha"; self.selected_radio = "One"; self.checkbox_enabled = False
        elif l == LevelID.TABLE_LIST: self.selected_cell = None; self.selected_list_row = ""
        elif l == LevelID.NUMERIC_CONTROLS: self.slider_value = 50; self.stepper_value = 0
        elif l == LevelID.CONTEXT_MENU: self.context_choice = ""
        elif l == LevelID.KEYBOARD_SHORTCUT: self.shortcut_pressed = ""
        elif l == LevelID.TEXT_EDITING: self.notes_text = ""; self.word_double_clicked = False; self.paragraph_triple_clicked = False
        elif l == LevelID.SCROLL_TASK: self.scroll_target_clicked = False
        elif l == LevelID.POINTER_TASK: self.drop_received = False
        elif l == LevelID.STRESS: self.stress_popup = "Alpha"; self.stress_text = ""; self.stress_cell = None; self.stress_ready = False; self.stress_lower_confirm_clicked = False
        self.update_results()

    def get_requirements(self, level):
        if level == LevelID.ACCEPT_CHALLENGE: return ["I Accept Challenge enabled"]
        if level == LevelID.TEXT_ENTRY: return ["Message is 'launch code delta-42'", "Send clicked"]
        if level == LevelID.MODAL_TASK: return ["Reviewer is Rivera", "Decision is Approve", "Sheet confirmed"]
        if level == LevelID.SELECTION_CONTROLS: return ["Popup is Charlie", "Radio is Three", "Checkbox enabled"]
        if level == LevelID.TABLE_LIST: return ["Cell 13 selected", "Row Gamma selected"]
        if level == LevelID.NUMERIC_CONTROLS: return ["Slider 70-80", "Stepper 3-5"]
        if level == LevelID.CONTEXT_MENU: return ["Choice is Archive"]
        if level == LevelID.KEYBOARD_SHORTCUT: return ["Cmd+Shift+M pressed"]
        if level == LevelID.TEXT_EDITING: return ["Text is 'Alpha beta gamma.'", "Word double-clicked", "Paragraph triple-clicked"]
        if level == LevelID.SCROLL_TASK: return ["Target 18 clicked"]
        if level == LevelID.POINTER_TASK: return ["Drag and drop complete"]
        if level == LevelID.STRESS: return ["Popup Delta", "Text 'final check'", "Cell 24", "Ready enabled", "Lower Confirm clicked"]
        return []

    def check_requirement(self, level, requirement):
        if level == LevelID.ACCEPT_CHALLENGE: return self.challenge_accepted
        if level == LevelID.TEXT_ENTRY:
            if "Message" in requirement: return self.message_text == "launch code delta-42"
            return self.message_sent
        if level == LevelID.MODAL_TASK:
            if "Reviewer" in requirement: return self.modal_reviewer == "Rivera"
            if "Decision" in requirement: return self.modal_decision == "Approve"
            return self.modal_confirmed
        if level == LevelID.SELECTION_CONTROLS:
            if "Popup" in requirement: return self.selected_popup == "Charlie"
            if "Radio" in requirement: return self.selected_radio == "Three"
            return self.checkbox_enabled
        if level == LevelID.TABLE_LIST:
            if "Cell" in requirement: return self.selected_cell == 13
            return self.selected_list_row == "Gamma"
        if level == LevelID.NUMERIC_CONTROLS:
            if "Slider" in requirement: return 70 <= self.slider_value <= 80
            return 3 <= self.stepper_value <= 5
        if level == LevelID.CONTEXT_MENU: return self.context_choice == "Archive"
        if level == LevelID.KEYBOARD_SHORTCUT: return self.shortcut_pressed == "Pressed Command+Shift+M"
        if level == LevelID.TEXT_EDITING:
            if "Text" in requirement: return self.notes_text == "Alpha beta gamma."
            if "Word" in requirement: return self.word_double_clicked
            return self.paragraph_triple_clicked
        if level == LevelID.SCROLL_TASK: return self.scroll_target_clicked
        if level == LevelID.POINTER_TASK: return self.drop_received
        if level == LevelID.STRESS:
            if "Popup" in requirement: return self.stress_popup == "Delta"
            if "Text" in requirement: return self.stress_text == "final check"
            if "Cell" in requirement: return self.stress_cell == 24
            if "Ready" in requirement: return self.stress_ready
            return self.stress_lower_confirm_clicked
        return True

    def update_results(self):
        reqs = self.get_requirements(self.current_level)
        self.test_results = {req: self.check_requirement(self.current_level, req) for req in reqs}

    def get_score_report(self):
        if self.current_level == LevelID.SUMMARY:
            total_met, total_possible = self.get_total_score()
            return f"Final Score: {total_met}/{total_possible}"
        
        current_reqs = self.get_requirements(self.current_level)
        met = sum(1 for r in current_reqs if self.check_requirement(self.current_level, r))
        total_met, total_possible = self.get_total_score()
        return f"Level: {self.current_level.number}/{len(LevelID)} | Level Score: {met}/{len(current_reqs)} | Total Score: {total_met}/{total_possible}"

    def get_total_score(self):
        total_met = 0
        total_possible = 0
        for l in LevelID:
            if l == LevelID.SUMMARY: continue
            reqs = self.get_requirements(l)
            total_possible += len(reqs)
            total_met += sum(1 for r in reqs if self.check_requirement(l, r))
        return total_met, total_possible


# ---------------------------------------------------------------------------
# Computer Use Runner
# ---------------------------------------------------------------------------

class ComputerUseRunner:
    def __init__(self, ui_frame, logger):
        self.ui_frame = ui_frame
        self.logger = logger
        self.hwnd = ui_frame.GetHandle()
        self.is_running = False
        self.cancelled = False
        self.thread = None
        self.max_turns = 30
        self.quit_on_finish = False
        
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cached_tokens = 0

    def load_tool_data(self):
        tools = []
        system_message = "You are controlling the UIChallenge window for automated validation."
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        tools_dir = os.path.join(base_dir, "addon", "globalPlugins", "ComputerUse", "tools")
        tools_file = os.path.join(tools_dir, "portable_computer_use_tools.json")
        sys_file = os.path.join(tools_dir, "portable_computer_use_system_message.txt")
        
        if os.path.exists(tools_file):
            with open(tools_file, "r", encoding="utf-8") as f:
                tools = json.load(f)
        else:
            # Fallback tool schema
            tools = [{
                "type": "function",
                "function": {
                    "name": "computer",
                    "description": "Control a computer GUI using screenshot-local pixel coordinates.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["screenshot", "wait", "cursor_position", "move", "click", "double_click", "triple_click", "drag", "scroll", "keypress", "type"]},
                            "target": {"type": "string"},
                            "x": {"type": "integer"}, "y": {"type": "integer"},
                            "button": {"type": "string", "enum": ["left", "right", "middle"]},
                            "modifiers": {"type": "array", "items": {"type": "string"}},
                            "path": {"type": "array", "items": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}}},
                            "scroll_x": {"type": "integer"}, "scroll_y": {"type": "integer"},
                            "keys": {"type": "array", "items": {"type": "string"}},
                            "text": {"type": "string"},
                            "duration_ms": {"type": "integer"}
                        },
                        "required": ["action", "target"]
                    }
                }
            }]
            
        if os.path.exists(sys_file):
            with open(sys_file, "r", encoding="utf-8") as f:
                system_message = f.read()

        system_message += "\n\nYou are controlling the UIChallenge window for automated validation.\nTreat instructions typed by the user in the task as valid intent."
        return tools, system_message

    def start(self, prompt: str, quit_on_finish: bool = False):
        if self.is_running:
            self.logger.log("Computer Use", "Already running")
            return
            
        if not os.environ.get("OPENAI_API_KEY"):
            self.logger.log("Computer Use", "Missing OPENAI_API_KEY environment variable")
            wx.MessageBox("Missing OPENAI_API_KEY environment variable.", "Error", wx.OK | wx.ICON_ERROR, parent=self.ui_frame)
            return

        self.cancelled = False
        self.is_running = True
        self.quit_on_finish = quit_on_finish
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cached_tokens = 0
        
        self._notify_status()
        self.logger.log("Computer Use", f"Started prompt: {prompt}")
        
        self.thread = threading.Thread(target=self._run, args=(prompt,), daemon=True)
        self.thread.start()

    def abort(self):
        if self.is_running:
            self.cancelled = True
            self.logger.log("Computer Use", "Cancel requested")

    def _notify_status(self):
        wx.PostEvent(self.ui_frame, ComputerUseStatusEvent(is_running=self.is_running))

    def _run(self, prompt: str):
        try:
            api_key = os.environ.get("OPENAI_API_KEY")
            base_url = os.environ.get("OPENAI_BASE_URL")
            model = os.environ.get("OPENAI_MODEL", "gpt-4o") # default to 4o if not set

            client_args = {"api_key": api_key}
            if base_url:
                client_args["base_url"] = base_url
            
            client = OpenAI(**client_args)
            
            tools, system_msg = self.load_tool_data()
            
            capture = capture_window(self.hwnd)
            self.logger.log("Computer Use Action", "Screenshot")
            
            messages = [
                {"role": "system", "content": system_msg},
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": f"User task: {prompt}\nScreenshot size: {capture.target_width if hasattr(capture, 'target_width') else capture.width}x{capture.target_height if hasattr(capture, 'target_height') else capture.height} pixels."},
                        {"type": "image_url", "image_url": {"url": capture.image_url, "detail": "original"}}
                    ]
                }
            ]
            
            for turn in range(1, self.max_turns + 1):
                if self.cancelled:
                    self._finish("Cancelled")
                    return
                
                self.logger.log("Computer Use API", f"Sending request to {model} (Turn {turn})")
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto"
                )
                
                # Usage
                if response.usage:
                    u = response.usage
                    self.total_input_tokens += u.prompt_tokens
                    self.total_output_tokens += u.completion_tokens
                    # Some backends don't have prompt_tokens_details
                    cached = getattr(u, 'prompt_tokens_details', None)
                    c_val = getattr(cached, 'cached_tokens', 0) if cached else 0
                    self.total_cached_tokens += c_val
                    self.logger.log("Computer Use API", f"Tokens: {u.total_tokens} [in: {u.prompt_tokens} (cache {c_val}), out: {u.completion_tokens}]")
                
                message = response.choices[0].message
                if message.content:
                    self.logger.log("Computer Use Message", message.content)
                
                tool_calls = message.tool_calls
                if not tool_calls:
                    self._finish(message.content or "Completed")
                    return
                
                # Append assistant message
                msg_dict = {"role": "assistant"}
                if message.content: msg_dict["content"] = message.content
                if tool_calls:
                    msg_dict["tool_calls"] = []
                    for tc in tool_calls:
                        msg_dict["tool_calls"].append({
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                        })
                messages.append(msg_dict)
                
                for tc in tool_calls:
                    if self.cancelled:
                        self._finish("Cancelled")
                        return
                        
                    if tc.function.name == "computer":
                        action = json.loads(tc.function.arguments)
                        self.logger.log("Computer Use Action", describe_action(action))
                        try:
                            result_str = perform_action(action, capture)
                            # if it was a screenshot, capture anew
                            if action.get("type", action.get("action", "")) == "screenshot":
                                time.sleep(0.5)
                        except Exception as e:
                            result_str = f"Error: {e}"
                            self.logger.log("Computer Use Error", result_str)
                            
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result_str
                        })
                    else:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": "Unsupported tool"
                        })
                
                if self.cancelled:
                    self._finish("Cancelled")
                    return
                
                # After tools, we capture a fresh screenshot and append as user message
                time.sleep(0.5)
                capture = capture_window(self.hwnd)
                self.logger.log("Computer Use Action", "Screenshot")
                
                # To prevent context from growing infinitely with images, we can strip old images
                self._sanitize_messages(messages)
                
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Latest screenshot."},
                        {"type": "image_url", "image_url": {"url": capture.image_url, "detail": "original"}}
                    ]
                })

            self._finish(f"Stopped after {self.max_turns} turns.")
            
        except Exception as exc:
            self.logger.log("Computer Use Error", str(exc))
            self._finish("Error")

    def _sanitize_messages(self, messages):
        # 1. Strip ALL existing images from the history to minimize token usage
        for msg in messages:
            if isinstance(msg.get("content"), list):
                msg["content"] = [item for item in msg["content"] if item.get("type") != "image_url"]

        # 2. Identify the latest turn's assistant message with tool calls
        latest_assistant_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant" and messages[i].get("tool_calls"):
                latest_assistant_idx = i
                break

        if latest_assistant_idx != -1:
            indices_to_remove = []
            # We preserve system (0) and initial prompt (1).
            # For everything in between, we keep only the assistant's text reasoning (summary).
            for i in range(2, latest_assistant_idx):
                msg = messages[i]
                role = msg.get("role")
                if role == "assistant":
                    # Remove tool calls but KEEP text content (the reasoning summary)
                    msg.pop("tool_calls", None)
                    if not msg.get("content"):
                        indices_to_remove.append(i)
                elif role in ["tool", "user"]:
                    # Remove machine data and old screenshot placeholders
                    indices_to_remove.append(i)
            
            for idx in sorted(indices_to_remove, reverse=True):
                messages.pop(idx)

    def _finish(self, status: str):
        self.is_running = False
        self._notify_status()
        
        total = self.total_input_tokens + self.total_output_tokens
        self.logger.log("Computer Use Final", status)
        self.logger.log(
            "Computer Use API",
            f"Final Usage - Total: {total} [input: {self.total_input_tokens} "
            f"(cached: {self.total_cached_tokens}), output: {self.total_output_tokens}]"
        )
        self.logger.log("Computer Use", "Finished")
        
        def finalize():
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(self.logger.full_text()))
                wx.TheClipboard.Close()
                self.logger.log("App", "Session report copied to clipboard")
            
            if self.quit_on_finish:
                time.sleep(1.0)
                self.ui_frame.Close()
        
        wx.CallAfter(finalize)


# ---------------------------------------------------------------------------
# UI Components
# ---------------------------------------------------------------------------

class ApprovalDialog(wx.Dialog):
    def __init__(self, parent, controller):
        super().__init__(parent, title="Approval Sheet", size=(360, 250))
        self.controller = controller
        
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        title = wx.StaticText(panel, label="Approval Sheet")
        title.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        sizer.Add(title, 0, wx.ALL, 10)
        
        self.reviewer = wx.TextCtrl(panel, value=controller.modal_reviewer)
        self.reviewer.SetHint("Reviewer")
        sizer.Add(self.reviewer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        self.decision = wx.RadioBox(panel, label="Decision", choices=["Review", "Approve", "Reject"], majorDimension=1, style=wx.RA_SPECIFY_COLS)
        self.decision.SetStringSelection(controller.modal_decision)
        sizer.Add(self.decision, 0, wx.ALL | wx.EXPAND, 10)
        
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        confirm_btn = wx.Button(panel, wx.ID_OK, "Confirm")
        confirm_btn.SetDefault()
        
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(cancel_btn, 0, wx.RIGHT, 5)
        btn_sizer.Add(confirm_btn, 0, wx.RIGHT, 10)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.BOTTOM, 10)
        
        panel.SetSizer(sizer)

class DropTarget(wx.TextDropTarget):
    def __init__(self, window, callback):
        super().__init__()
        self.window = window
        self.callback = callback

    def OnDropText(self, x, y, data):
        self.callback(data)
        return True

    def OnDragOver(self, x, y, defResult):
        self.window.SetBackgroundColour(wx.Colour(200, 255, 200))
        self.window.Refresh()
        return wx.DragCopy

    def OnLeave(self):
        self.window.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_FRAMEBK))
        self.window.Refresh()

class UIChallengeFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="UI Challenge", size=(1040, 720))
        self.logger = ActionLogger(self)
        self.controller = LevelController(self.logger)
        self.cu_runner = ComputerUseRunner(self, self.logger)
        
        self.InitMenu()
        self.InitUI()
        self.BindEvents()
        self.UpdateLevel()
        
        self.logger.log("App", "App launched")
        self.Centre()

    def InitMenu(self):
        menubar = wx.MenuBar()
        
        file_menu = wx.Menu()
        m_new = file_menu.Append(wx.ID_NEW, "New Test Session\tCtrl+N")
        file_menu.AppendSeparator()
        m_exit = file_menu.Append(wx.ID_EXIT, "Exit")
        menubar.Append(file_menu, "File")
        
        test_menu = wx.Menu()
        self.m_run_cu = test_menu.Append(wx.ID_ANY, "Ask Computer Use...")
        self.m_cancel_cu = test_menu.Append(wx.ID_ANY, "Cancel Computer Use\tEsc")
        self.m_cancel_cu.Enable(False)
        test_menu.AppendSeparator()
        m_clear_log = test_menu.Append(wx.ID_CLEAR, "Clear Action Log\tCtrl+K")
        menubar.Append(test_menu, "Test Actions")
        
        help_menu = wx.Menu()
        m_about = help_menu.Append(wx.ID_ABOUT, "About")
        menubar.Append(help_menu, "Help")
        
        self.SetMenuBar(menubar)
        
        self.Bind(wx.EVT_MENU, lambda e: self.logger.clear(), m_new)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), m_exit)
        self.Bind(wx.EVT_MENU, self.OnAskComputerUse, self.m_run_cu)
        self.Bind(wx.EVT_MENU, lambda e: self.cu_runner.abort(), self.m_cancel_cu)
        self.Bind(wx.EVT_MENU, lambda e: self.logger.clear(), m_clear_log)
        self.Bind(wx.EVT_MENU, self.OnAbout, m_about)

    def InitUI(self):
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.left_panel = wx.Panel(self.panel)
        self.left_sizer = wx.BoxSizer(wx.VERTICAL)
        
        header_panel = wx.Panel(self.left_panel)
        h_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.lvl_title = wx.StaticText(header_panel, label="Level 1: Accept Challenge")
        self.lvl_title.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.score_text = wx.StaticText(header_panel, label="Score: 0/0")
        self.score_text.SetFont(wx.Font(11, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        
        h_sizer.Add(self.lvl_title, 1, wx.ALIGN_CENTER_VERTICAL)
        h_sizer.Add(self.score_text, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        header_panel.SetSizer(h_sizer)
        self.left_sizer.Add(header_panel, 0, wx.EXPAND | wx.ALL, 10)
        
        self.instr_text = wx.StaticText(self.left_panel, label="", style=wx.ST_NO_AUTORESIZE)
        self.instr_text.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_INFOBK))
        self.left_sizer.Add(self.instr_text, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        self.content_area = wx.Panel(self.left_panel)
        self.content_sizer = wx.BoxSizer(wx.VERTICAL)
        self.content_area.SetSizer(self.content_sizer)
        self.left_sizer.Add(self.content_area, 1, wx.EXPAND | wx.ALL, 10)
        
        self.req_box = wx.StaticBox(self.left_panel, label="Requirements Status")
        self.req_sizer = wx.StaticBoxSizer(self.req_box, wx.VERTICAL)
        self.left_sizer.Add(self.req_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        nav_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.prev_btn = wx.Button(self.left_panel, label="Previous")
        self.next_btn = wx.Button(self.left_panel, label="Next")
        self.reset_btn = wx.Button(self.left_panel, label="Reset Level")
        
        nav_sizer.Add(self.prev_btn, 0, wx.RIGHT, 5)
        nav_sizer.Add(self.next_btn, 0, wx.RIGHT, 5)
        nav_sizer.AddStretchSpacer()
        nav_sizer.Add(self.reset_btn, 0)
        self.left_sizer.Add(nav_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        self.left_panel.SetSizer(self.left_sizer)
        
        self.right_panel = wx.Panel(self.panel)
        r_sizer = wx.BoxSizer(wx.VERTICAL)
        
        log_header = wx.BoxSizer(wx.HORIZONTAL)
        log_label = wx.StaticText(self.right_panel, label="Visible Log")
        log_label.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.clear_log_btn = wx.Button(self.right_panel, label="Clear", size=(60, -1))
        
        log_header.Add(log_label, 1, wx.ALIGN_CENTER_VERTICAL)
        log_header.Add(self.clear_log_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        r_sizer.Add(log_header, 0, wx.EXPAND | wx.ALL, 5)
        
        self.log_ctrl = wx.TextCtrl(self.right_panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        self.log_ctrl.SetFont(wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        r_sizer.Add(self.log_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        
        self.right_panel.SetSizer(r_sizer)
        
        main_sizer.Add(self.left_panel, 3, wx.EXPAND)
        main_sizer.Add(self.right_panel, 2, wx.EXPAND)
        
        self.panel.SetSizer(main_sizer)

    def BindEvents(self):
        self.prev_btn.Bind(wx.EVT_BUTTON, self.OnPrev)
        self.next_btn.Bind(wx.EVT_BUTTON, self.OnNext)
        self.reset_btn.Bind(wx.EVT_BUTTON, self.OnReset)
        self.clear_log_btn.Bind(wx.EVT_BUTTON, lambda e: self.logger.clear())
        self.Bind(EVT_LOG, self.OnLog)
        self.Bind(EVT_CU_STATUS, self.OnCUStatus)

    def OnLog(self, evt):
        self.log_ctrl.SetValue(evt.full_log)
        self.log_ctrl.SetInsertionPointEnd()

    def OnCUStatus(self, evt):
        running = evt.is_running
        self.m_run_cu.Enable(not running)
        self.m_cancel_cu.Enable(running)

    def OnAskComputerUse(self, evt):
        dlg = wx.TextEntryDialog(self, "Enter a task for the built-in computer-use loop.", "Ask Computer Use", self.controller.current_level.instruction)
        if dlg.ShowModal() == wx.ID_OK:
            prompt = dlg.GetValue()
            if prompt:
                self.cu_runner.start(prompt)
        dlg.Destroy()

    def OnAbout(self, evt):
        wx.MessageBox("A Windows test harness for validating computer-use clicks, drags, typing, menus, shortcuts, and selections.", "About UI Challenge", wx.OK | wx.ICON_INFORMATION, self)

    def OnPrev(self, evt):
        if self.controller.current_level > 0:
            self.controller.current_level = LevelID(self.controller.current_level - 1)
            self.UpdateLevel()
            self.logger.log("Level", f"Went back to Level {self.controller.current_level.number}")

    def OnNext(self, evt):
        if self.controller.current_level < LevelID.SUMMARY:
            self.controller.current_level = LevelID(self.controller.current_level + 1)
            self.UpdateLevel()
            self.logger.log("Level", f"Advanced to Level {self.controller.current_level.number}")

    def OnReset(self, evt):
        self.controller.reset_current_level()
        self.UpdateLevel()
        self.logger.log("Level", "Current level reset")

    def UpdateLevel(self):
        self.controller.update_results()
        self.lvl_title.SetLabel(f"Level {self.controller.current_level.number}: {self.controller.current_level.title}")
        self.score_text.SetLabel(self.controller.get_score_report())
        self.instr_text.SetLabel(self.controller.current_level.instruction)
        self.instr_text.Wrap(self.left_panel.GetSize().width - 40)
        
        self.req_sizer.Clear(True)
        for req, pass_status in self.controller.test_results.items():
            color = wx.Colour(0, 150, 0) if pass_status else wx.Colour(128, 128, 128)
            label = f"✓ {req}" if pass_status else f"○ {req}"
            txt = wx.StaticText(self.req_box, label=label)
            txt.SetForegroundColour(color)
            self.req_sizer.Add(txt, 0, wx.ALL, 2)
        
        self.prev_btn.Enable(self.controller.current_level > 0)
        self.next_btn.Enable(self.controller.current_level < LevelID.SUMMARY)
        
        self.content_sizer.Clear(True)
        self.CreateLevelContent()
        self.content_area.Layout()
        self.left_panel.Layout()

    def CreateLevelContent(self):
        l = self.controller.current_level
        if l == LevelID.ACCEPT_CHALLENGE:
            btn = wx.ToggleButton(self.content_area, label="I Accept Challenge")
            btn.SetValue(self.controller.challenge_accepted)
            btn.Bind(wx.EVT_TOGGLEBUTTON, self.OnChallengeToggle)
            self.content_sizer.Add(btn, 0, wx.ALL | wx.CENTER, 20)
            
        elif l == LevelID.TEXT_ENTRY:
            h_sizer = wx.BoxSizer(wx.HORIZONTAL)
            self.msg_field = wx.TextCtrl(self.content_area, value=self.controller.message_text)
            self.msg_field.SetHint("Message")
            send_btn = wx.Button(self.content_area, label="Send")
            h_sizer.Add(self.msg_field, 1, wx.EXPAND | wx.RIGHT, 5)
            h_sizer.Add(send_btn, 0)
            self.content_sizer.Add(h_sizer, 0, wx.EXPAND | wx.ALL, 10)
            
            self.msg_field.Bind(wx.EVT_TEXT, self.OnMessageChange)
            send_btn.Bind(wx.EVT_BUTTON, self.OnSendMessage)
            
        elif l == LevelID.MODAL_TASK:
            self.content_sizer.Add(wx.StaticText(self.content_area, label=f"Reviewer: {self.controller.modal_reviewer or 'None'}"))
            self.content_sizer.Add(wx.StaticText(self.content_area, label=f"Decision: {self.controller.modal_decision}"))
            self.content_sizer.Add(wx.StaticText(self.content_area, label=f"Confirmed: {'Yes' if self.controller.modal_confirmed else 'No'}"))
            
            btn = wx.Button(self.content_area, label="Open Approval Sheet")
            btn.Bind(wx.EVT_BUTTON, self.OnOpenModal)
            self.content_sizer.Add(btn, 0, wx.TOP, 10)
            
        elif l == LevelID.SELECTION_CONTROLS:
            choices = ["Alpha", "Bravo", "Charlie", "Delta"]
            popup = wx.Choice(self.content_area, choices=choices)
            popup.SetStringSelection(self.controller.selected_popup)
            self.content_sizer.Add(wx.StaticText(self.content_area, label="Popup Menu:"), 0, wx.LEFT, 5)
            self.content_sizer.Add(popup, 0, wx.ALL | wx.EXPAND, 5)
            
            radio = wx.RadioBox(self.content_area, label="Radio Box", choices=["One", "Two", "Three"])
            radio.SetStringSelection(self.controller.selected_radio)
            self.content_sizer.Add(radio, 0, wx.ALL | wx.EXPAND, 5)
            
            chk = wx.CheckBox(self.content_area, label="Enable Checkbox")
            chk.SetValue(self.controller.checkbox_enabled)
            self.content_sizer.Add(chk, 0, wx.ALL, 5)
            
            popup.Bind(wx.EVT_CHOICE, self.OnPopupChange)
            radio.Bind(wx.EVT_RADIOBOX, self.OnRadioChange)
            chk.Bind(wx.EVT_CHECKBOX, self.OnCheckboxToggle)
            
        elif l == LevelID.TABLE_LIST:
            h_sizer = wx.BoxSizer(wx.HORIZONTAL)
            
            grid = wx.grid.Grid(self.content_area)
            grid.CreateGrid(5, 5)
            grid.SetRowLabelSize(0)
            grid.SetColLabelSize(0)
            for r in range(5):
                for c in range(5):
                    num = r * 5 + c + 1
                    grid.SetCellValue(r, c, str(num))
                    grid.SetReadOnly(r, c)
            
            grid.Bind(wx.grid.EVT_GRID_CELL_LEFT_CLICK, self.OnTableCellClick)
            h_sizer.Add(grid, 0, wx.ALL, 5)
            
            list_box = wx.ListBox(self.content_area, choices=["Alpha", "Bravo", "Gamma", "Delta", "Epsilon"])
            if self.controller.selected_list_row:
                list_box.SetStringSelection(self.controller.selected_list_row)
            list_box.Bind(wx.EVT_LISTBOX, self.OnListSelect)
            h_sizer.Add(list_box, 1, wx.EXPAND | wx.ALL, 5)
            
            self.content_sizer.Add(h_sizer, 1, wx.EXPAND)
            
        elif l == LevelID.NUMERIC_CONTROLS:
            self.sld_txt = wx.StaticText(self.content_area, label=f"Slider Value: {self.controller.slider_value}")
            self.content_sizer.Add(self.sld_txt, 0, wx.LEFT, 5)
            sld = wx.Slider(self.content_area, value=self.controller.slider_value, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
            sld.Bind(wx.EVT_SLIDER, self.OnSliderChange)
            self.content_sizer.Add(sld, 0, wx.EXPAND | wx.ALL, 5)
            
            self.stp_txt = wx.StaticText(self.content_area, label=f"Stepper Value: {self.controller.stepper_value}")
            self.content_sizer.Add(self.stp_txt, 0, wx.LEFT, 5)
            stp = wx.SpinButton(self.content_area, style=wx.SP_VERTICAL)
            stp.SetRange(0, 10)
            stp.SetValue(self.controller.stepper_value)
            stp.Bind(wx.EVT_SPIN, self.OnStepperChange)
            self.content_sizer.Add(stp, 0, wx.ALL, 5)
            
        elif l == LevelID.CONTEXT_MENU:
            target = wx.Panel(self.content_area, size=(220, 72))
            target.SetBackgroundColour(wx.Colour(240, 240, 240))
            target.SetWindowStyle(wx.BORDER_SUNKEN)
            lbl = wx.StaticText(target, label="Context Target")
            lbl.Center()
            
            target.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)
            self.content_sizer.Add(target, 0, wx.ALL | wx.CENTER, 20)
            
        elif l == LevelID.KEYBOARD_SHORTCUT:
            btn = wx.Button(self.content_area, label="Start Shortcut Capture")
            btn.Bind(wx.EVT_BUTTON, self.OnStartCapture)
            self.content_sizer.Add(btn, 0, wx.ALL, 5)
            
            self.capture_panel = wx.Panel(self.content_area, size=(-1, 80))
            self.capture_panel.SetBackgroundColour(wx.Colour(250, 250, 250))
            self.capture_panel.SetWindowStyle(wx.BORDER_SIMPLE)
            self.capture_lbl = wx.StaticText(self.capture_panel, label="Press Start Shortcut Capture")
            
            self.capture_panel.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
            self.content_sizer.Add(self.capture_panel, 0, wx.EXPAND | wx.ALL, 5)
            
        elif l == LevelID.TEXT_EDITING:
            self.notes = wx.TextCtrl(self.content_area, style=wx.TE_MULTILINE, size=(-1, 100), value=self.controller.notes_text)
            self.notes.Bind(wx.EVT_TEXT, self.OnNotesChange)
            self.content_sizer.Add(self.notes, 0, wx.EXPAND | wx.ALL, 5)
            
            h_sizer = wx.BoxSizer(wx.HORIZONTAL)
            word_target = wx.Panel(self.content_area, size=(150, 46))
            word_target.SetBackgroundColour(wx.Colour(230, 230, 230))
            wx.StaticText(word_target, label="Word Target").Center()
            word_target.Bind(wx.EVT_LEFT_DCLICK, self.OnWordDoubleClick)
            
            para_target = wx.Panel(self.content_area, size=(180, 46))
            para_target.SetBackgroundColour(wx.Colour(230, 230, 230))
            wx.StaticText(para_target, label="Paragraph Target").Center()
            para_target.Bind(wx.EVT_LEFT_DOWN, self.OnParaClick)
            self.para_clicks = 0
            self.para_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self.OnParaTimer, self.para_timer)
            
            h_sizer.Add(word_target, 0, wx.ALL, 5)
            h_sizer.Add(para_target, 0, wx.ALL, 5)
            self.content_sizer.Add(h_sizer, 0)
            
        elif l == LevelID.SCROLL_TASK:
            scroll = wx.ScrolledWindow(self.content_area, size=(-1, 240))
            scroll.SetScrollRate(20, 20)
            s_sizer = wx.BoxSizer(wx.VERTICAL)
            for i in range(1, 25):
                label = "Hidden Target 18" if i == 18 else f"Practice Target {i}"
                btn = wx.Button(scroll, label=label)
                btn.Bind(wx.EVT_BUTTON, lambda e, idx=i: self.OnScrollTarget(idx))
                s_sizer.Add(btn, 0, wx.EXPAND | wx.ALL, 2)
            scroll.SetSizer(s_sizer)
            self.content_sizer.Add(scroll, 1, wx.EXPAND | wx.ALL, 5)
            
        elif l == LevelID.POINTER_TASK:
            h_sizer = wx.BoxSizer(wx.HORIZONTAL)
            drag_src = wx.Button(self.content_area, label="Drag Source", size=(150, 54))
            drag_src.Bind(wx.EVT_LEFT_DOWN, self.OnDragStart)
            
            self.drop_target_win = wx.Panel(self.content_area, size=(150, 54))
            self.drop_target_win.SetBackgroundColour(wx.Colour(220, 220, 220))
            self.drop_target_win.SetWindowStyle(wx.BORDER_SIMPLE)
            wx.StaticText(self.drop_target_win, label="Drop Target").Center()
            
            self.drop_target_win.SetDropTarget(DropTarget(self.drop_target_win, self.OnDrop))
            
            h_sizer.Add(drag_src, 0, wx.ALL, 10)
            h_sizer.Add(self.drop_target_win, 0, wx.ALL, 10)
            self.content_sizer.Add(h_sizer, 0, wx.CENTER)
            
        elif l == LevelID.STRESS:
            grid_sizer = wx.GridSizer(rows=1, cols=3, hgap=5, vgap=5)
            for i in range(3):
                btn = wx.Button(self.content_area, label="Confirm")
                if i == 2:
                    btn.Bind(wx.EVT_BUTTON, self.OnStressLowerConfirm)
                grid_sizer.Add(btn, 0, wx.EXPAND)
            self.content_sizer.Add(grid_sizer, 0, wx.ALL, 5)
            
            h_sizer = wx.BoxSizer(wx.HORIZONTAL)
            popup = wx.Choice(self.content_area, choices=["Alpha", "Bravo", "Charlie", "Delta"])
            popup.SetStringSelection(self.controller.stress_popup)
            popup.Bind(wx.EVT_CHOICE, self.OnStressPopup)
            h_sizer.Add(popup, 0, wx.RIGHT, 5)
            
            text = wx.TextCtrl(self.content_area, value=self.controller.stress_text)
            text.Bind(wx.EVT_TEXT, self.OnStressText)
            h_sizer.Add(text, 1, wx.RIGHT, 5)
            
            chk = wx.CheckBox(self.content_area, label="Ready")
            chk.SetValue(self.controller.stress_ready)
            chk.Bind(wx.EVT_CHECKBOX, self.OnStressReady)
            h_sizer.Add(chk, 0)
            self.content_sizer.Add(h_sizer, 0, wx.EXPAND | wx.ALL, 5)
            
            cell_sizer = wx.BoxSizer(wx.HORIZONTAL)
            for i in range(21, 26):
                btn = wx.Button(self.content_area, label=f"Cell {i}")
                btn.Bind(wx.EVT_BUTTON, lambda e, num=i: self.OnStressCell(num))
                cell_sizer.Add(btn, 1, wx.EXPAND | wx.RIGHT, 2)
            self.content_sizer.Add(cell_sizer, 0, wx.EXPAND | wx.ALL, 5)
            
        elif l == LevelID.SUMMARY:
            list_ctrl = wx.ListCtrl(self.content_area, style=wx.LC_REPORT)
            list_ctrl.InsertColumn(0, "Lvl", width=40)
            list_ctrl.InsertColumn(1, "Requirement", width=300)
            list_ctrl.InsertColumn(2, "Pass", width=60)
            
            idx = 0
            for level in LevelID:
                if level == LevelID.SUMMARY: continue
                reqs = self.controller.get_requirements(level)
                for req in reqs:
                    pass_status = self.controller.check_requirement(level, req)
                    list_ctrl.InsertItem(idx, str(level.number))
                    list_ctrl.SetItem(idx, 1, req)
                    list_ctrl.SetItem(idx, 2, "Pass" if pass_status else "Fail")
                    if not pass_status:
                        list_ctrl.SetItemTextColour(idx, wx.RED)
                    else:
                        list_ctrl.SetItemTextColour(idx, wx.Colour(0, 150, 0))
                    idx += 1
            self.content_sizer.Add(list_ctrl, 1, wx.EXPAND | wx.ALL, 5)

    # Event Handlers
    def OnChallengeToggle(self, evt):
        self.controller.challenge_accepted = evt.IsChecked()
        self.logger.log("Checkbox", f"I Accept Challenge {'Checked' if self.controller.challenge_accepted else 'Unchecked'}")
        self.UpdateLevel()

    def OnMessageChange(self, evt):
        self.controller.message_text = evt.GetString()
        self.controller.message_sent = False
        self.UpdateLevel()

    def OnSendMessage(self, evt):
        self.controller.message_sent = True
        self.logger.log("Button", "Send clicked")
        self.UpdateLevel()

    def OnOpenModal(self, evt):
        dlg = ApprovalDialog(self, self.controller)
        if dlg.ShowModal() == wx.ID_OK:
            self.controller.modal_reviewer = dlg.reviewer.GetValue()
            self.controller.modal_decision = dlg.decision.GetStringSelection()
            self.controller.modal_confirmed = True
            self.logger.log("Modal", "Approval sheet confirmed")
        else:
            self.logger.log("Modal", "Approval sheet canceled")
        dlg.Destroy()
        self.UpdateLevel()

    def OnPopupChange(self, evt):
        self.controller.selected_popup = evt.GetString()
        self.logger.log("Popup", f"Selected {self.controller.selected_popup}")
        self.UpdateLevel()

    def OnRadioChange(self, evt):
        self.controller.selected_radio = evt.GetString()
        self.logger.log("Radio", f"Selected {self.controller.selected_radio}")
        self.UpdateLevel()

    def OnCheckboxToggle(self, evt):
        self.controller.checkbox_enabled = evt.IsChecked()
        self.logger.log("Checkbox", f"{'Checked' if self.controller.checkbox_enabled else 'Unchecked'}")
        self.UpdateLevel()

    def OnTableCellClick(self, evt):
        row, col = evt.GetRow(), evt.GetCol()
        self.controller.selected_cell = row * 5 + col + 1
        self.logger.log("Table", f"Selected cell {self.controller.selected_cell}")
        self.UpdateLevel()

    def OnListSelect(self, evt):
        self.controller.selected_list_row = evt.GetString()
        self.logger.log("List", f"Selected row {self.controller.selected_list_row}")
        self.UpdateLevel()

    def OnSliderChange(self, evt):
        self.controller.slider_value = evt.GetInt()
        self.sld_txt.SetLabel(f"Slider Value: {self.controller.slider_value}")
        self.logger.log("Slider", f"Changed to {self.controller.slider_value}")
        self.UpdateLevel()

    def OnStepperChange(self, evt):
        self.controller.stepper_value = evt.GetPosition()
        self.stp_txt.SetLabel(f"Stepper Value: {self.controller.stepper_value}")
        self.logger.log("Stepper", f"Changed to {self.controller.stepper_value}")
        self.UpdateLevel()

    def OnContextMenu(self, evt):
        menu = wx.Menu()
        menu.Append(101, "Open")
        menu.Append(102, "Archive")
        menu.Append(103, "Delete")
        
        self.Bind(wx.EVT_MENU, self.OnContextChoice, id=101, id2=103)
        self.PopupMenu(menu)
        menu.Destroy()

    def OnContextChoice(self, evt):
        choices = {101: "Open", 102: "Archive", 103: "Delete"}
        self.controller.context_choice = choices[evt.GetId()]
        self.logger.log("Context Menu", f"{self.controller.context_choice} selected")
        self.UpdateLevel()

    def OnStartCapture(self, evt):
        self.capture_panel.SetFocus()
        self.capture_lbl.SetLabel("Listening for shortcut")
        self.capture_panel.SetBackgroundColour(wx.Colour(230, 240, 255))
        self.capture_panel.Refresh()
        self.logger.log("Shortcut", "Shortcut capture started")

    def OnKeyDown(self, evt):
        if self.capture_panel.HasFocus():
            mods = []
            if evt.ControlDown(): mods.append("Control")
            if evt.RawControlDown() and wx.Platform == '__WXMAC__': mods.append("Command")
            if evt.CmdDown(): mods.append("Command")
            if evt.ShiftDown(): mods.append("Shift")
            if evt.AltDown(): mods.append("Option")
            
            key_code = evt.GetKeyCode()
            key_name = ""
            if key_code == wx.WXK_ESCAPE: key_name = "Escape"
            elif key_code == wx.WXK_RETURN: key_name = "Return"
            elif key_code == wx.WXK_TAB: key_name = "Tab"
            elif key_code == wx.WXK_SPACE: key_name = "Space"
            else:
                try:
                    key_name = chr(key_code).upper() if 32 < key_code < 127 else f"Key {key_code}"
                except:
                    key_name = f"Key {key_code}"
            
            shortcut = f"Pressed {'+'.join(mods + [key_name])}"
            self.controller.shortcut_pressed = shortcut
            self.capture_lbl.SetLabel(shortcut)
            self.logger.log("Shortcut", shortcut)
            self.UpdateLevel()

    def OnNotesChange(self, evt):
        self.controller.notes_text = evt.GetString()
        self.UpdateLevel()

    def OnWordDoubleClick(self, evt):
        self.controller.word_double_clicked = True
        self.logger.log("Text", "Word Target double-clicked")
        self.UpdateLevel()

    def OnParaClick(self, evt):
        self.para_clicks += 1
        if self.para_clicks == 3:
            self.controller.paragraph_triple_clicked = True
            self.logger.log("Text", "Paragraph Target triple-clicked")
            self.para_clicks = 0
            self.UpdateLevel()
        else:
            self.para_timer.Start(500, oneShot=True)

    def OnParaTimer(self, evt):
        self.para_clicks = 0

    def OnScrollTarget(self, idx):
        if idx == 18:
            self.controller.scroll_target_clicked = True
            self.logger.log("Scroll", "Hidden Target 18 clicked")
        else:
            self.logger.log("Scroll", f"Practice Target {idx} clicked")
        self.UpdateLevel()

    def OnDragStart(self, evt):
        data = wx.TextDataObject("Drag Source")
        src = wx.DropSource(self)
        src.SetData(data)
        self.logger.log("Drag", "Drag Source drag started")
        src.DoDragDrop(True)

    def OnDrop(self, data):
        self.controller.drop_received = True
        self.logger.log("Drop", f"Drop Target received: {data}")
        self.UpdateLevel()

    def OnStressLowerConfirm(self, evt):
        self.controller.stress_lower_confirm_clicked = True
        self.logger.log("Stress", "Lower Confirm clicked")
        self.UpdateLevel()

    def OnStressPopup(self, evt):
        self.controller.stress_popup = evt.GetString()
        self.UpdateLevel()

    def OnStressText(self, evt):
        self.controller.stress_text = evt.GetString()
        self.UpdateLevel()

    def OnStressReady(self, evt):
        self.controller.stress_ready = evt.IsChecked()
        self.UpdateLevel()

    def OnStressCell(self, num):
        self.controller.stress_cell = num
        self.logger.log("Stress", f"Selected cell {num}")
        self.UpdateLevel()

def main():
    parser = argparse.ArgumentParser(description="UI Challenge App")
    parser.add_argument("--prompt", type=str, help="Auto-start computer use with this prompt")
    args = parser.parse_args()

    set_dpi_awareness()
    app = wx.App()
    frame = UIChallengeFrame()
    frame.Show()
    
    if args.prompt:
        wx.CallAfter(lambda: frame.cu_runner.start(args.prompt, quit_on_finish=True))
        
    app.MainLoop()

if __name__ == "__main__":
    main()

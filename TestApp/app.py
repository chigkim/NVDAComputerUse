from __future__ import annotations

import argparse
import base64
import ctypes
import ctypes.wintypes
import io
import os
import queue
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from tkinter import messagebox, simpledialog, ttk

from PIL import ImageGrab


APP_TITLE = "Windows Computer Use Test App"
DEFAULT_MODEL = "gpt-5.5"
MAX_TURNS = 30
ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")
LOG_FILE = os.path.join(os.path.dirname(__file__), "last_run.log")

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
    "alt": 0x12,
    "backspace": 0x08,
    "ctrl": 0x11,
    "control": 0x11,
    "delete": 0x2E,
    "down": 0x28,
    "end": 0x23,
    "enter": 0x0D,
    "escape": 0x1B,
    "esc": 0x1B,
    "home": 0x24,
    "insert": 0x2D,
    "left": 0x25,
    "meta": 0x5B,
    "pagedown": 0x22,
    "page_down": 0x22,
    "pageup": 0x21,
    "page_up": 0x21,
    "right": 0x27,
    "shift": 0x10,
    "space": 0x20,
    "tab": 0x09,
    "up": 0x26,
    "win": 0x5B,
    "windows": 0x5B,
    "cmd": 0x5B,
    "command": 0x5B,
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


class ActionLogger:
    def __init__(self, root: tk.Tk, text_widget: tk.Text):
        self.root = root
        self.text_widget = text_widget
        self.entries: list[str] = []
        with open(LOG_FILE, "w", encoding="utf-8") as log_file:
            log_file.write("")

    def log(self, category: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] {category}: {message}"
        print(line)
        with open(LOG_FILE, "a", encoding="utf-8") as log_file:
            log_file.write(line + "\n")

        def append() -> None:
            self.entries.append(line)
            if len(self.entries) > 500:
                self.entries = self.entries[-500:]
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", line + "\n")
            self.text_widget.see("end")
            self.text_widget.configure(state="disabled")

        self.root.after(0, append)

    def clear(self) -> None:
        def clear_text() -> None:
            self.entries.clear()
            self.text_widget.configure(state="normal")
            self.text_widget.delete("1.0", "end")
            self.text_widget.configure(state="disabled")

        self.root.after(0, clear_text)
        self.log("Log", "Cleared")

    def full_text(self) -> str:
        return "\n".join(self.entries)


class TestApp:
    def __init__(self, launch_prompt: str | None, close_on_finish: bool, maximize: bool):
        set_dpi_awareness()
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1040x720")
        self.root.minsize(960, 680)
        self.maximize = maximize

        self.message_text = tk.StringVar()
        self.prompt_text = tk.StringVar()
        self.selected_popup = tk.StringVar(value="Alpha")
        self.selected_radio = tk.StringVar(value="One")
        self.checkbox_enabled = tk.BooleanVar(value=False)
        self.slider_value = tk.DoubleVar(value=50.0)
        self.shortcut_capture_active = False
        self.selected_cell: int | None = None
        self.drag_started = False

        self.log_text = tk.Text(self.root, width=46, wrap="word", state="disabled")
        self.logger = ActionLogger(self.root, self.log_text)
        self.computer_use = ComputerUseRunner(self.root, self.logger, self.set_running, close_on_finish)
        self.launch_prompt = launch_prompt
        self._build_menu()
        self._build_ui()

    def run(self) -> None:
        self.root.after(250, self._activate_window)
        if self.launch_prompt:
            self.prompt_text.set(self.launch_prompt)
            self.root.after(1200, lambda: self.computer_use.start(self.launch_prompt))
        self.root.mainloop()

    def set_running(self, is_running: bool) -> None:
        def update() -> None:
            state = "disabled" if is_running else "normal"
            self.prompt_entry.configure(state=state)
            self.run_button.configure(state="disabled" if is_running else "normal")
            self.cancel_button.configure(state="normal" if is_running else "disabled")
            self.run_button.configure(text="Running..." if is_running else "Run")

        self.root.after(0, update)

    def _activate_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.focus_force()
        if self.maximize:
            try:
                self.root.state("zoomed")
            except tk.TclError:
                pass
        self.root.after(1500, lambda: self.root.attributes("-topmost", False))
        self.logger.log("App", "App launched and activated")

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)

        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="New Test Session", command=self.logger.clear, accelerator="Ctrl+N")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menu.add_cascade(label="File", menu=file_menu)

        test_menu = tk.Menu(menu, tearoff=False)
        test_menu.add_command(label="Ask Computer Use...", command=self.ask_computer_use)
        test_menu.add_command(label="Cancel Computer Use", command=self.computer_use.abort, accelerator="Esc")
        test_menu.add_separator()
        test_menu.add_command(
            label="Log Menu Action",
            command=lambda: self.logger.log("Menu", "Log Menu Action selected"),
            accelerator="Ctrl+Shift+M",
        )
        test_menu.add_command(label="Clear Action Log", command=self.logger.clear, accelerator="Ctrl+K")
        menu.add_cascade(label="Test Actions", menu=test_menu)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="About", command=self.show_about)
        menu.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menu)
        self.root.bind("<Control-n>", lambda _event: self.logger.clear())
        self.root.bind("<Control-K>", lambda _event: self.logger.clear())
        self.root.bind("<Control-Shift-M>", lambda _event: self.logger.log("Menu", "Ctrl+Shift+M pressed"))
        self.root.bind("<Escape>", lambda _event: self.computer_use.abort())

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=0)
        outer.rowconfigure(0, weight=1)

        left = ttk.Frame(outer)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky="nsew")
        left.columnconfigure(0, weight=1)

        self._build_computer_use_section(left)
        self._build_drag_section(left)
        self._build_input_section(left)
        self._build_selection_section(left)
        self._build_table_section(left)
        self._build_shortcut_section(left)
        self._build_log_section(right)

    def _build_computer_use_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Computer Use", padding=10)
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(0, weight=1)
        self.prompt_entry = ttk.Entry(frame, textvariable=self.prompt_text)
        self.prompt_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.prompt_entry.configure()
        self.run_button = ttk.Button(frame, text="Run", command=lambda: self.computer_use.start(self.prompt_text.get()))
        self.run_button.grid(row=0, column=1, padx=(0, 8))
        self.cancel_button = ttk.Button(frame, text="Cancel", command=self.computer_use.abort, state="disabled")
        self.cancel_button.grid(row=0, column=2)

    def _build_drag_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Drag and Drop Buttons", padding=10)
        frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.drag_source = tk.Label(
            frame,
            text="Drag Source",
            width=18,
            height=3,
            relief="solid",
            borderwidth=2,
            background="#dceeff",
        )
        self.drag_source.grid(row=0, column=0, padx=(0, 28))
        self.drag_source.bind("<Button-1>", self._drag_source_click)
        self.drag_source.bind("<ButtonPress-1>", self._drag_start)
        self.drag_source.bind("<B1-Motion>", self._drag_motion)
        self.drag_source.bind("<ButtonRelease-1>", self._drag_release)

        self.drop_target = tk.Label(
            frame,
            text="Drop Target",
            width=18,
            height=3,
            relief="solid",
            borderwidth=2,
            background="#eeeeee",
        )
        self.drop_target.grid(row=0, column=1)
        self.drop_target.bind("<Button-1>", lambda event: self.logger.log("Button", f"Drop Target clicked with {modifiers(event)}"))

    def _build_input_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Edit Box and Send Button", padding=10)
        frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(0, weight=1)
        entry = ttk.Entry(frame, textvariable=self.message_text)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        entry.bind("<KeyRelease>", lambda _event: self.logger.log("Text", f"Edit box changed to '{self.message_text.get()}'"))
        entry.bind("<Return>", lambda _event: self.logger.log("Text", f"Return submitted '{self.message_text.get()}'"))
        send = ttk.Button(frame, text="Send", command=lambda: self.logger.log("Button", f"Send clicked with '{self.message_text.get()}'"))
        send.grid(row=0, column=1)

    def _build_selection_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Popup Menu, Radio Box, Checkbox, and Slider", padding=10)
        frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Popup Menu").grid(row=0, column=0, sticky="w", padx=(0, 8))
        popup = ttk.OptionMenu(frame, self.selected_popup, self.selected_popup.get(), "Alpha", "Bravo", "Charlie", "Delta", command=self._popup_selected)
        popup.grid(row=0, column=1, sticky="w", pady=(0, 8))

        ttk.Label(frame, text="Radio Box").grid(row=1, column=0, sticky="nw", padx=(0, 8))
        radios = ttk.Frame(frame)
        radios.grid(row=1, column=1, sticky="w", pady=(0, 8))
        for index, option in enumerate(("One", "Two", "Three")):
            ttk.Radiobutton(
                radios,
                text=option,
                value=option,
                variable=self.selected_radio,
                command=lambda value=option: self.logger.log("Radio", f"Selected {value}"),
            ).grid(row=0, column=index, padx=(0, 12))

        ttk.Checkbutton(
            frame,
            text="Enable Checkbox",
            variable=self.checkbox_enabled,
            command=lambda: self.logger.log("Checkbox", "Checked" if self.checkbox_enabled.get() else "Unchecked"),
        ).grid(row=2, column=1, sticky="w", pady=(0, 8))

        self.slider_label = ttk.Label(frame, text="Slider Value: 50")
        self.slider_label.grid(row=3, column=0, sticky="w", padx=(0, 8))
        slider = ttk.Scale(frame, from_=0, to=100, variable=self.slider_value, command=self._slider_changed)
        slider.grid(row=3, column=1, sticky="ew")

    def _build_table_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="5 by 5 Number Table", padding=10)
        frame.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        self.cell_buttons: dict[int, ttk.Button] = {}
        for number in range(1, 26):
            row = (number - 1) // 5
            column = (number - 1) % 5
            button = ttk.Button(frame, text=str(number), width=7, command=lambda value=number: self._select_cell(value))
            button.grid(row=row, column=column, padx=4, pady=4)
            self.cell_buttons[number] = button

    def _build_shortcut_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Shortcut Tests with Modifiers", padding=10)
        frame.grid(row=5, column=0, sticky="ew")
        start = ttk.Button(frame, text="Start Shortcut Capture", command=self._start_shortcut_capture)
        start.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.shortcut_label = tk.Label(
            frame,
            text="Press Start Shortcut Capture",
            relief="solid",
            borderwidth=2,
            height=3,
            background="#f4f4f4",
        )
        self.shortcut_label.grid(row=1, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)
        self.shortcut_label.bind("<Button-1>", lambda _event: self._start_shortcut_capture())
        self.shortcut_label.bind("<Key>", self._shortcut_key)

    def _build_log_section(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(header, text="Logs", font=("", 12, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Clear", command=self.logger.clear).grid(row=0, column=1, sticky="e")
        header.columnconfigure(0, weight=1)
        self.log_text.grid(row=1, column=0, sticky="nsew")

    def ask_computer_use(self) -> None:
        prompt = simpledialog.askstring(
            "Ask Computer Use",
            "Enter a task for the built-in computer-use loop.",
            initialvalue=self.prompt_text.get(),
            parent=self.root,
        )
        if prompt:
            self.prompt_text.set(prompt)
            self.computer_use.start(prompt)
        else:
            self.logger.log("Computer Use", "Prompt cancelled")

    def show_about(self) -> None:
        self.logger.log("Menu", "About selected")
        messagebox.showinfo(
            "About",
            "A Windows test harness for validating computer-use clicks, drags, typing, menus, shortcuts, and selections.",
            parent=self.root,
        )

    def _popup_selected(self, value: str) -> None:
        self.logger.log("Popup", f"Selected {value}")

    def _slider_changed(self, value: str) -> None:
        number = int(float(value))
        self.slider_label.configure(text=f"Slider Value: {number}")
        self.logger.log("Slider", f"Changed to {number}")

    def _select_cell(self, number: int) -> None:
        self.selected_cell = number
        self.logger.log("Table", f"Selected cell {number}")

    def _drag_source_click(self, event: tk.Event) -> None:
        self.logger.log("Button", f"Drag Source clicked with {modifiers(event)}")

    def _drag_start(self, _event: tk.Event) -> None:
        self.drag_started = True
        self.logger.log("Drag", "Drag Source drag started")

    def _drag_motion(self, event: tk.Event) -> None:
        if not self.drag_started:
            return
        x = self.drag_source.winfo_rootx() + event.x
        y = self.drag_source.winfo_rooty() + event.y
        targeted = widget_contains_screen_point(self.drop_target, x, y)
        self.drop_target.configure(background="#c7f0ce" if targeted else "#eeeeee")

    def _drag_release(self, event: tk.Event) -> None:
        if not self.drag_started:
            return
        self.drag_started = False
        x = self.drag_source.winfo_rootx() + event.x
        y = self.drag_source.winfo_rooty() + event.y
        targeted = widget_contains_screen_point(self.drop_target, x, y)
        self.drop_target.configure(background="#eeeeee")
        if targeted:
            self.logger.log("Drop", "Drop Target received 1 item")
        else:
            self.logger.log("Drag", "Drag Source released outside Drop Target")

    def _start_shortcut_capture(self) -> None:
        self.shortcut_capture_active = True
        self.shortcut_label.configure(text="Listening for shortcut", background="#fff7c2")
        self.shortcut_label.focus_set()
        self.logger.log("Shortcut", "Shortcut capture started")

    def _shortcut_key(self, event: tk.Event) -> None:
        self.logger.log("Shortcut", f"Pressed {describe_key_event(event)}")


class ComputerUseRunner:
    def __init__(self, root: tk.Tk, logger: ActionLogger, set_running, close_on_finish: bool):
        self.root = root
        self.logger = logger
        self.set_running = set_running
        self.close_on_finish = close_on_finish
        self.cancelled = False
        self.thread: threading.Thread | None = None
        self.message_queue: queue.Queue[str] = queue.Queue()
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cached_tokens = 0

    def start(self, prompt: str) -> None:
        prompt = prompt.strip()
        if not prompt:
            self.logger.log("Computer Use", "Prompt is empty")
            return
        if self.thread and self.thread.is_alive():
            self.logger.log("Computer Use", "Already running")
            return
        if not os.environ.get("OPENAI_API_KEY"):
            self.logger.log("Computer Use", "Missing OPENAI_API_KEY environment variable")
            messagebox.showerror("Computer Use Error", "Missing OPENAI_API_KEY environment variable.", parent=self.root)
            return

        self.cancelled = False
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cached_tokens = 0
        self.set_running(True)
        self.logger.log("Computer Use", f"Started prompt: {prompt}")
        hwnd = self.root.winfo_id()
        self.thread = threading.Thread(target=self._run, args=(prompt, hwnd), daemon=True)
        self.thread.start()

    def abort(self) -> None:
        if self.thread and self.thread.is_alive():
            self.cancelled = True
            self.logger.log("Computer Use", "Cancel requested")
        else:
            self.logger.log("Computer Use", "No running session to cancel")

    def _run(self, prompt: str, hwnd: int) -> None:
        try:
            from openai import OpenAI

            base_url = os.environ.get("OPENAI_BASE_URL")
            client_kwargs = {"api_key": os.environ["OPENAI_API_KEY"]}
            if base_url:
                client_kwargs["base_url"] = base_url
            client = OpenAI(**client_kwargs)
            model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
            capture = capture_window(hwnd)
            self.logger.log("Computer Use Action", "Screenshot")
            response = client.responses.create(
                model=model,
                tools=[{"type": "computer"}],
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "You are testing this Windows app window. Use the computer tool to operate only "
                                    "controls visible in this app. Log-producing controls include buttons, drag and "
                                    "drop, text entry, popup menu, radio buttons, checkbox, slider, table cells, menu "
                                    f"commands, and shortcut capture. User task: {prompt}"
                                ),
                            },
                            {
                                "type": "input_image",
                                "image_url": capture.image_url,
                                "detail": "original",
                            },
                        ],
                    }
                ],
            )
            self._record_usage(response, 1)

            for turn in range(1, MAX_TURNS + 1):
                if self.cancelled:
                    self._finish("Cancelled")
                    return
                computer_call = find_computer_call(response)
                if computer_call is None:
                    self._finish(final_text(response) or "Completed")
                    return

                actions = field(computer_call, "actions", []) or []
                for action in actions:
                    if self.cancelled:
                        self._finish("Cancelled")
                        return
                    label = describe_action(action, capture)
                    self.logger.log("Computer Use Action", label)
                    perform_action(action, capture)
                    time.sleep(0.2)

                capture = capture_window(hwnd)
                self.logger.log("Computer Use Action", "Screenshot")
                response = client.responses.create(
                    model=model,
                    tools=[{"type": "computer"}],
                    previous_response_id=response.id,
                    input=[
                        {
                            "type": "computer_call_output",
                            "call_id": field(computer_call, "call_id"),
                            "output": {
                                "type": "computer_screenshot",
                                "image_url": capture.image_url,
                                "detail": "original",
                            },
                        }
                    ],
                )
                self._record_usage(response, turn + 1)

            self._finish(f"Stopped after {MAX_TURNS} turns.")
        except Exception as exc:
            self.logger.log("Computer Use Error", repr(exc))
            self.root.after(0, lambda: messagebox.showerror("Computer Use Error", str(exc), parent=self.root))
            self.set_running(False)

    def _record_usage(self, response, turn: int) -> None:
        usage = field(response, "usage")
        input_tokens = int(field(usage, "input_tokens", 0) or 0)
        output_tokens = int(field(usage, "output_tokens", 0) or 0)
        total_tokens = int(field(usage, "total_tokens", input_tokens + output_tokens) or 0)
        details = field(usage, "input_tokens_details")
        cached_tokens = int(field(details, "cached_tokens", 0) or 0)
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cached_tokens += cached_tokens
        self.logger.log(
            "Computer Use API",
            f"Turn {turn}: {total_tokens} tokens [input {input_tokens} (cache {cached_tokens}) output {output_tokens}]",
        )

    def _finish(self, status: str) -> None:
        total = self.total_input_tokens + self.total_output_tokens
        self.logger.log("Computer Use Final", status)
        self.logger.log(
            "Computer Use API",
            f"Final Usage - Total: {total} [input: {self.total_input_tokens} "
            f"(cached: {self.total_cached_tokens}), output: {self.total_output_tokens}]",
        )
        self.set_running(False)
        self.root.after(0, lambda: self.root.clipboard_clear())
        self.root.after(0, lambda: self.root.clipboard_append(self.logger.full_text()))
        if self.close_on_finish:
            self.logger.log("App", "Closing after Computer Use finished")
            self.root.after(1000, self.root.destroy)


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


def find_computer_call(response):
    for item in field(response, "output", []) or []:
        if field(item, "type") == "computer_call":
            return item
    return None


def final_text(response) -> str:
    text = field(response, "output_text")
    if text:
        return str(text)
    parts = []
    for item in field(response, "output", []) or []:
        if field(item, "type") != "message":
            continue
        for content in field(item, "content", []) or []:
            value = field(content, "text")
            if value:
                parts.append(str(value))
    return "\n".join(parts).strip()


def perform_action(action, capture: Capture) -> None:
    action_type = field(action, "type")
    if action_type == "click":
        click(action, capture, 1)
    elif action_type == "double_click":
        click(action, capture, 2)
    elif action_type == "move":
        x, y = capture.to_screen(field(action, "x"), field(action, "y"))
        ctypes.windll.user32.SetCursorPos(x, y)
    elif action_type == "drag":
        drag(action, capture)
    elif action_type == "scroll":
        scroll(action, capture)
    elif action_type == "keypress":
        keypress(field(action, "keys", []))
    elif action_type == "type":
        type_text(field(action, "text", ""))
    elif action_type == "wait" or action_type == "screenshot":
        time.sleep(0.5)
    else:
        raise RuntimeError(f"Unsupported computer action: {action_type}")


def click(action, capture: Capture, count: int) -> None:
    x, y = capture.to_screen(field(action, "x"), field(action, "y"))
    button = field(action, "button", "left")
    keys = field(action, "keys", [])
    with held_keys(keys):
        ctypes.windll.user32.SetCursorPos(x, y)
        for _ in range(count):
            mouse_click(button)


def drag(action, capture: Capture) -> None:
    path = field(action, "path", []) or []
    if len(path) < 2:
        return
    first_x, first_y = point(path[0])
    x, y = capture.to_screen(first_x, first_y)
    ctypes.windll.user32.SetCursorPos(x, y)
    mouse_down("left")
    try:
        for item in path[1:]:
            point_x, point_y = point(item)
            x, y = capture.to_screen(point_x, point_y)
            ctypes.windll.user32.SetCursorPos(x, y)
            time.sleep(0.04)
    finally:
        mouse_up("left")


def scroll(action, capture: Capture) -> None:
    x = field(action, "x")
    y = field(action, "y")
    if x is not None and y is not None:
        ctypes.windll.user32.SetCursorPos(*capture.to_screen(x, y))
    scroll_y = int(field(action, "scrollY", field(action, "scroll_y", field(action, "dy", 0))) or 0)
    scroll_x = int(field(action, "scrollX", field(action, "scroll_x", field(action, "dx", 0))) or 0)
    if scroll_y:
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, -scroll_y, 0)
    if scroll_x:
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_HWHEEL, 0, 0, scroll_x, 0)


def keypress(keys) -> None:
    if isinstance(keys, str):
        keys = [keys]
    with held_keys(keys[:-1]):
        if keys:
            press_key(keys[-1])


def type_text(text: str) -> None:
    for char in text:
        send_unicode(char)


def mouse_click(button: str) -> None:
    mouse_down(button)
    mouse_up(button)


def mouse_down(button: str) -> None:
    flag = {
        "left": MOUSEEVENTF_LEFTDOWN,
        "right": MOUSEEVENTF_RIGHTDOWN,
        "middle": MOUSEEVENTF_MIDDLEDOWN,
    }.get(str(button).lower(), MOUSEEVENTF_LEFTDOWN)
    ctypes.windll.user32.mouse_event(flag, 0, 0, 0, 0)


def mouse_up(button: str) -> None:
    flag = {
        "left": MOUSEEVENTF_LEFTUP,
        "right": MOUSEEVENTF_RIGHTUP,
        "middle": MOUSEEVENTF_MIDDLEUP,
    }.get(str(button).lower(), MOUSEEVENTF_LEFTUP)
    ctypes.windll.user32.mouse_event(flag, 0, 0, 0, 0)


class held_keys:
    def __init__(self, keys):
        if keys is None:
            keys = []
        if isinstance(keys, str):
            keys = [keys]
        self.codes = [key_code(key) for key in keys if key_code(key) is not None]

    def __enter__(self):
        for code in self.codes:
            ctypes.windll.user32.keybd_event(code, 0, 0, 0)

    def __exit__(self, exc_type, exc, tb):
        for code in reversed(self.codes):
            ctypes.windll.user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)


def press_key(key) -> None:
    code = key_code(key)
    if code is None:
        if isinstance(key, str):
            type_text(key)
        return
    ctypes.windll.user32.keybd_event(code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)


def key_code(key) -> int | None:
    normalized = str(key).lower().replace("+", "").replace("arrow", "")
    if normalized == "return":
        normalized = "enter"
    if len(normalized) == 1:
        return ctypes.windll.user32.VkKeyScanW(ctypes.c_wchar(normalized)) & 0xFF
    return VK.get(normalized)


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


def describe_action(action, capture: Capture | None = None) -> str:
    action_type = field(action, "type", "unknown")
    if action_type == "click":
        return point_action("Click", action, capture)
    if action_type == "double_click":
        return point_action("Double click", action, capture)
    if action_type == "move":
        return point_action("Move", action, capture)
    if action_type == "drag":
        path = field(action, "path", []) or []
        if path:
            x, y = point(path[-1])
            if capture is not None:
                x, y = capture.to_screen(x, y)
            return f"Drag to {x}, {y}"
        return "Drag"
    if action_type == "scroll":
        scroll_y = int(field(action, "scrollY", field(action, "scroll_y", field(action, "dy", 0))) or 0)
        scroll_x = int(field(action, "scrollX", field(action, "scroll_x", field(action, "dx", 0))) or 0)
        return f"Scroll {scroll_x}, {scroll_y}"
    if action_type == "keypress":
        keys = field(action, "keys", [])
        if isinstance(keys, str):
            keys = [keys]
        return "Key press " + "+".join(str(key) for key in keys)
    if action_type == "type":
        text = field(action, "text", "")
        suffix = "" if len(text) == 1 else "s"
        return f"Type {len(text)} character{suffix}"
    if action_type == "wait":
        return "Wait"
    if action_type == "screenshot":
        return "Screenshot"
    return str(action_type).replace("_", " ").title()


def point_action(name: str, action, capture: Capture | None) -> str:
    x = field(action, "x", "?")
    y = field(action, "y", "?")
    if capture is not None and x != "?" and y != "?":
        x, y = capture.to_screen(x, y)
    return f"{name} {x}, {y}"


def field(obj, name: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def point(item) -> tuple[float, float]:
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        return item[0], item[1]
    return field(item, "x"), field(item, "y")


def modifiers(event: tk.Event) -> str:
    parts = []
    state = getattr(event, "state", 0)
    if state & 0x0001:
        parts.append("Shift")
    if state & 0x0004:
        parts.append("Control")
    if state & 0x0008:
        parts.append("Alt")
    return "+".join(parts) if parts else "no modifiers"


def describe_key_event(event: tk.Event) -> str:
    parts = []
    state = getattr(event, "state", 0)
    if state & 0x0001:
        parts.append("Shift")
    if state & 0x0004:
        parts.append("Control")
    if state & 0x0008:
        parts.append("Alt")
    key = event.keysym or event.char or "Unknown"
    parts.append(key)
    return "+".join(parts)


def widget_contains_screen_point(widget: tk.Widget, x: int, y: int) -> bool:
    left = widget.winfo_rootx()
    top = widget.winfo_rooty()
    return left <= x <= left + widget.winfo_width() and top <= y <= top + widget.winfo_height()


def self_test() -> int:
    load_env_file()
    from openai import OpenAI  # noqa: F401
    import PIL  # noqa: F401

    print("OpenAI import ok")
    print("Pillow import ok")
    print("Tkinter import ok")
    fake_capture = Capture("", 100, 200, 500, 400, 500, 400)
    assert fake_capture.to_screen(10, 20) == (110, 220)
    assert describe_action({"type": "click", "x": 10, "y": 20}, fake_capture) == "Click 110, 220"
    assert describe_action({"type": "type", "text": "hello"}, fake_capture) == "Type 5 characters"
    with held_keys(None):
        pass
    print("Action mapping ok")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", help="Run this computer-use prompt after the app opens.")
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Keep the UI open after an automatic --prompt run finishes.",
    )
    parser.add_argument(
        "--maximize",
        action="store_true",
        help="Maximize the test app window before starting.",
    )
    parser.add_argument("--self-test", action="store_true", help="Check imports and action mapping without opening the UI.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    load_env_file()
    args = parse_args(argv)
    if args.self_test:
        return self_test()
    close_on_finish = bool(args.prompt and not args.keep_open)
    app = TestApp(args.prompt, close_on_finish, args.maximize)
    app.run()
    return 0


def load_env_file(path: str = ENV_FILE) -> None:
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

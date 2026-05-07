import ctypes
import ctypes.wintypes
import time

import mouseHandler
import winUser


KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000
KEY_INPUT_DELAY_SECONDS = 0.05
CLICK_DOWN_UP_DELAY_SECONDS = 0.01
MULTI_CLICK_DELAY_SECONDS = 0.05
CLIPBOARD_OPEN_RETRY_DELAY_SECONDS = 0.02
CLIPBOARD_OPEN_RETRIES = 5
CONFIRM_ACTION = "confirm"
RISKY_WORDS = (
	"delete",
	"remove",
	"erase",
	"format",
	"purchase",
	"buy",
	"pay",
	"submit",
	"send",
	"post",
	"password",
	"api key",
	"secret",
	"install",
	"run",
	"execute",
	"permission",
	"settings",
)

ctypes.windll.kernel32.GlobalAlloc.argtypes = [ctypes.wintypes.UINT, ctypes.c_size_t]
ctypes.windll.kernel32.GlobalAlloc.restype = ctypes.wintypes.HANDLE
ctypes.windll.kernel32.GlobalLock.argtypes = [ctypes.wintypes.HANDLE]
ctypes.windll.kernel32.GlobalLock.restype = ctypes.c_void_p
ctypes.windll.kernel32.GlobalUnlock.argtypes = [ctypes.wintypes.HANDLE]
ctypes.windll.kernel32.GlobalUnlock.restype = ctypes.wintypes.BOOL
ctypes.windll.kernel32.GlobalFree.argtypes = [ctypes.wintypes.HANDLE]
ctypes.windll.kernel32.GlobalFree.restype = ctypes.wintypes.HANDLE
ctypes.windll.user32.OpenClipboard.argtypes = [ctypes.wintypes.HWND]
ctypes.windll.user32.OpenClipboard.restype = ctypes.wintypes.BOOL
ctypes.windll.user32.CloseClipboard.argtypes = []
ctypes.windll.user32.CloseClipboard.restype = ctypes.wintypes.BOOL
ctypes.windll.user32.EmptyClipboard.argtypes = []
ctypes.windll.user32.EmptyClipboard.restype = ctypes.wintypes.BOOL
ctypes.windll.user32.SetClipboardData.argtypes = [ctypes.wintypes.UINT, ctypes.wintypes.HANDLE]
ctypes.windll.user32.SetClipboardData.restype = ctypes.wintypes.HANDLE

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
	VK["f%s" % i] = 0x6F + i


class ActionRunner:
	def __init__(self, callbacks=None):
		self.callbacks = callbacks

	def perform(self, actions, capture, before_execute=None):
		for action in actions:
			label = describe_action(action, capture)
			if self.callbacks is not None:
				self.callbacks.action_performed(speech_label(action), label)
			if before_execute is not None:
				before_execute(action)
			self.perform_one(action, capture)

	def perform_one(self, action, capture):
		action_type = _field(action, "action")
		if action_type == "click":
			self._click(action, capture, count=1)
		elif action_type == "double_click":
			self._click(action, capture, count=2)
		elif action_type == "triple_click":
			self._click(action, capture, count=3)
		elif action_type == "move":
			x, y = capture.to_screen(_field(action, "x"), _field(action, "y"))
			_move_to(x, y)
		elif action_type == "drag":
			self._drag(action, capture)
		elif action_type == "scroll":
			self._scroll(action, capture)
		elif action_type == "keypress":
			self._keypress(_field(action, "keys", []))
		elif action_type == "type":
			self._type_text(_field(action, "text", ""))
		elif action_type == "wait" or action_type == "screenshot":
			# For explicit wait/screenshot actions, we still want a small pause
			duration_ms = _field(action, "duration_ms", 250)
			time.sleep(max(duration_ms / 1000.0, 0.25))
		elif action_type == CONFIRM_ACTION:
			return
		else:
			raise RuntimeError("Unsupported computer action: %s" % action_type)

	def _click(self, action, capture, count=1):
		x, y = capture.to_screen(_field(action, "x"), _field(action, "y"))
		button = _field(action, "button", "left")
		keys = _field(action, "keys", []) or _field(action, "modifiers", [])
		with _held_keys(keys):
			_move_to(x, y)
			for index in range(count):
				_mouse_click(button)
				if index < count - 1:
					time.sleep(MULTI_CLICK_DELAY_SECONDS)

	def _drag(self, action, capture):
		path = _field(action, "path", []) or []
		if len(path) < 2:
			return
		first_x, first_y = _point(path[0])
		x, y = capture.to_screen(first_x, first_y)
		_move_to(x, y)
		keys = _field(action, "modifiers", [])
		with _held_keys(keys):
			_mouse_down("left")
			try:
				for point in path[1:]:
					point_x, point_y = _point(point)
					x, y = capture.to_screen(point_x, point_y)
					_move_to(x, y)
					time.sleep(0.05)
			finally:
				_mouse_up("left")

	def _scroll(self, action, capture):
		x = _field(action, "x", None)
		y = _field(action, "y", None)
		if x is not None and y is not None:
			_move_to(*capture.to_screen(x, y))
		scroll_y = int(_field(action, "scrollY", _field(action, "scroll_y", _field(action, "dy", 0))))
		scroll_x = int(_field(action, "scrollX", _field(action, "scroll_x", _field(action, "dx", 0))))
		keys = _field(action, "modifiers", [])
		with _held_keys(keys):
			if scroll_y:
				_send_input_mouse(MOUSEEVENTF_WHEEL, mouse_data=-scroll_y)
			if scroll_x:
				_send_input_mouse(MOUSEEVENTF_HWHEEL, mouse_data=scroll_x)

	def _keypress(self, keys):
		if keys is None:
			keys = []
		if isinstance(keys, str):
			keys = [keys]
		with _held_keys(keys[:-1]):
			if keys:
				_press_key(keys[-1])

	def _type_text(self, text):
		if not text:
			return
		if _paste_text_from_clipboard(text):
			return
		_send_unicode_text(text)


def looks_risky(actions):
	for action in actions:
		if is_confirm_action(action):
			continue
		text = "%s %s %s" % (
			describe_action(action),
			_field(action, "target", ""),
			_field(action, "text", ""),
		)
		text = text.lower()
		if any(word in text for word in RISKY_WORDS):
			return True
	return False


def is_confirm_action(action):
	return str(_field(action, "action", _field(action, "type", ""))).lower() == CONFIRM_ACTION


def confirm_action_description(action):
	target = _field(action, "target", "")
	if target:
		return str(target)
	text = _field(action, "text", "")
	if text:
		return str(text)
	return "Approve this Computer Use action?"


def describe_action(action, capture=None):
	action_type = str(_field(action, "action", "unknown"))
	parts = [_action_name(action_type)]
	target = _field(action, "target", "")
	if target:
		parts.append(str(target))
	if action_type in ("click", "double_click", "triple_click", "move"):
		_add_point_values(parts, action, capture)
		button = _field(action, "button", None)
		if button:
			parts.append(str(button))
		_add_list_value(parts, _field(action, "modifiers", []))
		_add_list_value(parts, _field(action, "keys", []))
	if action_type == "drag":
		path = _field(action, "path", []) or []
		if path:
			parts.append("%d points" % len(path))
			x, y = _point(path[-1])
			if capture is not None and x is not None and y is not None:
				screen_x, screen_y = capture.to_screen(x, y)
				parts.append("%s, %s" % (screen_x, screen_y))
			else:
				parts.append("%s, %s" % (x, y))
		_add_list_value(parts, _field(action, "modifiers", []))
	elif action_type == "scroll":
		scroll_y = int(_field(action, "scrollY", _field(action, "scroll_y", _field(action, "dy", 0))))
		scroll_x = int(_field(action, "scrollX", _field(action, "scroll_x", _field(action, "dx", 0))))
		parts.append("%s, %s" % (scroll_x, scroll_y))
		_add_point_values(parts, action, capture)
		_add_list_value(parts, _field(action, "modifiers", []))
	elif action_type == "keypress":
		keys = _field(action, "keys", []) or []
		_add_list_value(parts, keys)
	elif action_type == "type":
		text = _field(action, "text", "")
		parts.append("%d character%s" % (len(text), "" if len(text) == 1 else "s"))
	elif action_type == "wait":
		duration_ms = _field(action, "duration_ms", None)
		if duration_ms is not None:
			parts.append("%s ms" % duration_ms)
	elif action_type == CONFIRM_ACTION:
		pass
	elif action_type == "screenshot":
		pass
	else:
		_add_generic_values(parts, action, exclude=("action", "target"))
	return " ".join(parts)


def speech_label(action):
	action_type = _field(action, "action", "unknown")
	target = _field(action, "target", "")
	name = _action_name(action_type)
	if target:
		return "%s %s" % (name, target)
	return name


def _action_name(action_type):
	names = {
		"click": "Click",
		"double_click": "Double click",
		"triple_click": "Triple click",
		"move": "Move",
		"drag": "Drag",
		"scroll": "Scroll",
		"keypress": "Key press",
		"type": "Type",
		"wait": "Pause",
		"screenshot": "Screenshot",
		CONFIRM_ACTION: "Confirm",
	}
	return names.get(action_type, action_type.replace("_", " ").title())


def _add_point_values(parts, action, capture):
	x = _field(action, "x", None)
	y = _field(action, "y", None)
	if x is None or y is None:
		return
	if capture is not None:
		screen_x, screen_y = capture.to_screen(x, y)
		parts.append("%s, %s" % (screen_x, screen_y))
	else:
		parts.append("%s, %s" % (x, y))


def _add_list_value(parts, values):
	if not values:
		return
	if isinstance(values, str):
		values = [values]
	parts.append("+".join(str(value) for value in values))


def _add_generic_values(parts, action, exclude=()):
	if not isinstance(action, dict):
		return
	for key in sorted(action):
		if key in exclude:
			continue
		value = action[key]
		if isinstance(value, (str, int, float, bool)):
			parts.append(str(value))


def _move_to(x, y):
	winUser.setCursorPos(int(x), int(y))
	try:
		mouseHandler.executeMouseMoveEvent(int(x), int(y))
	except Exception:
		pass


def _mouse_click(button):
	_mouse_down(button)
	time.sleep(CLICK_DOWN_UP_DELAY_SECONDS)
	_mouse_up(button)


def _mouse_down(button):
	flag = {
		"left": MOUSEEVENTF_LEFTDOWN,
		"right": MOUSEEVENTF_RIGHTDOWN,
		"middle": MOUSEEVENTF_MIDDLEDOWN,
	}.get(str(button).lower(), MOUSEEVENTF_LEFTDOWN)
	_send_input_mouse(flag)


def _mouse_up(button):
	flag = {
		"left": MOUSEEVENTF_LEFTUP,
		"right": MOUSEEVENTF_RIGHTUP,
		"middle": MOUSEEVENTF_MIDDLEUP,
	}.get(str(button).lower(), MOUSEEVENTF_LEFTUP)
	_send_input_mouse(flag)


class _held_keys:
	def __init__(self, keys):
		if keys is None:
			keys = []
		if isinstance(keys, str):
			keys = [keys]
		self.keys = [_key_code(key) for key in keys if _key_code(key) is not None]

	def __enter__(self):
		for code in self.keys:
			_send_input_key(code, is_up=False)

	def __exit__(self, exc_type, exc, tb):
		for code in reversed(self.keys):
			_send_input_key(code, is_up=True)


def _press_key(key):
	code = _key_code(key)
	if code is None:
		if isinstance(key, str):
			for char in key:
				_send_unicode(char)
		return
	_send_input_key(code, is_up=False)
	_send_input_key(code, is_up=True)


def _send_input_key(vk_code, is_up=False):
	flags = KEYEVENTF_KEYUP if is_up else 0
	inp = _INPUT()
	inp.type = INPUT_KEYBOARD
	inp.ki = _KEYBDINPUT(vk_code, 0, flags, 0, None)
	_send_input(inp)


def _send_input_mouse(flags, mouse_data=0):
	inp = _INPUT()
	inp.type = INPUT_MOUSE
	inp.mi = _MOUSEINPUT(0, 0, int(mouse_data), flags, 0, None)
	_send_input(inp)


def _send_input(inputs):
	if isinstance(inputs, _INPUT):
		count = 1
		input_pointer = ctypes.pointer(inputs)
	else:
		count = len(inputs)
		input_pointer = ctypes.cast(inputs, ctypes.POINTER(_INPUT))
	sent = ctypes.windll.user32.SendInput(count, input_pointer, ctypes.sizeof(_INPUT))
	if sent != count:
		raise ctypes.WinError()


def _paste_text_from_clipboard(text):
	try:
		_set_clipboard_text(text)
		time.sleep(KEY_INPUT_DELAY_SECONDS)
		with _held_keys(["ctrl"]):
			_press_key("v")
		time.sleep(KEY_INPUT_DELAY_SECONDS)
		return True
	except Exception:
		return False


def _set_clipboard_text(text):
	encoded_text = (text + "\0").encode("utf-16-le", "surrogatepass")
	handle = ctypes.windll.kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded_text))
	if not handle:
		raise ctypes.WinError()
	try:
		locked_memory = ctypes.windll.kernel32.GlobalLock(handle)
		if not locked_memory:
			raise ctypes.WinError()
		try:
			ctypes.memmove(locked_memory, encoded_text, len(encoded_text))
		finally:
			ctypes.windll.kernel32.GlobalUnlock(handle)

		_open_clipboard()
		try:
			if not ctypes.windll.user32.EmptyClipboard():
				raise ctypes.WinError()
			if not ctypes.windll.user32.SetClipboardData(CF_UNICODETEXT, handle):
				raise ctypes.WinError()
			handle = None
		finally:
			ctypes.windll.user32.CloseClipboard()
	finally:
		if handle:
			ctypes.windll.kernel32.GlobalFree(handle)


def _open_clipboard():
	for attempt in range(CLIPBOARD_OPEN_RETRIES):
		if ctypes.windll.user32.OpenClipboard(None):
			return
		if attempt < CLIPBOARD_OPEN_RETRIES - 1:
			time.sleep(CLIPBOARD_OPEN_RETRY_DELAY_SECONDS)
	raise ctypes.WinError()


def _key_code(key):
	key = str(key).lower().replace("+", "").replace("arrow", "")
	if key in ("return",):
		key = "enter"
	if len(key) == 1:
		return ctypes.windll.user32.VkKeyScanW(ctypes.c_wchar(key)) & 0xFF
	return VK.get(key)


def _send_unicode_text(text):
	data = text.encode("utf-16-le", "surrogatepass")
	code_units = [
		int.from_bytes(data[index:index + 2], "little")
		for index in range(0, len(data), 2)
	]
	for code_unit in code_units:
		_send_unicode_code_unit(code_unit, KEYEVENTF_UNICODE)
		time.sleep(KEY_INPUT_DELAY_SECONDS)
		_send_unicode_code_unit(code_unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
		time.sleep(KEY_INPUT_DELAY_SECONDS)


def _send_unicode_code_unit(code_unit, flags):
	inp = _INPUT()
	inp.type = INPUT_KEYBOARD
	inp.ki = _KEYBDINPUT(0, code_unit, flags, 0, None)
	_send_input(inp)


def _send_unicode(char):
	if ord(char) > 0xFFFF:
		data = char.encode("utf-16-le", "surrogatepass")
		for index in range(0, len(data), 2):
			_send_unicode(chr(int.from_bytes(data[index:index + 2], "little")))
		return
	inputs = (_INPUT * 2)()

	# Down
	inputs[0].type = INPUT_KEYBOARD
	inputs[0].ki = _KEYBDINPUT(0, ord(char), KEYEVENTF_UNICODE, 0, None)

	# Up
	inputs[1].type = INPUT_KEYBOARD
	inputs[1].ki = _KEYBDINPUT(0, ord(char), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None)

	_send_input(inputs)


class _KEYBDINPUT(ctypes.Structure):
	_fields_ = [
		("wVk", ctypes.wintypes.WORD),
		("wScan", ctypes.wintypes.WORD),
		("dwFlags", ctypes.wintypes.DWORD),
		("time", ctypes.wintypes.DWORD),
		("dwExtraInfo", ctypes.c_void_p),
	]


class _MOUSEINPUT(ctypes.Structure):
	_fields_ = [
		("dx", ctypes.wintypes.LONG),
		("dy", ctypes.wintypes.LONG),
		("mouseData", ctypes.wintypes.DWORD),
		("dwFlags", ctypes.wintypes.DWORD),
		("time", ctypes.wintypes.DWORD),
		("dwExtraInfo", ctypes.c_void_p),
	]


class _HARDWAREINPUT(ctypes.Structure):
	_fields_ = [
		("uMsg", ctypes.wintypes.DWORD),
		("wParamL", ctypes.wintypes.WORD),
		("wParamH", ctypes.wintypes.WORD),
	]


class _INPUT_UNION(ctypes.Union):
	_fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
	_anonymous_ = ("union",)
	_fields_ = [("type", ctypes.wintypes.DWORD), ("union", _INPUT_UNION)]


def _field(obj, name, default=None):
	if isinstance(obj, dict):
		return obj.get(name, default)
	return getattr(obj, name, default)


def _point(point):
	if isinstance(point, (list, tuple)) and len(point) >= 2:
		return point[0], point[1]
	return _field(point, "x"), _field(point, "y")

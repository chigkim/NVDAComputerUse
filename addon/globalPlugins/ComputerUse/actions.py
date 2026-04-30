import ctypes
import ctypes.wintypes
import time

import mouseHandler
import winUser


KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
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
	VK["f%s" % i] = 0x6F + i


class ActionRunner:
	def __init__(self, callbacks=None):
		self.callbacks = callbacks

	def perform(self, actions, capture):
		for action in actions:
			label = describe_action(action, capture)
			if self.callbacks is not None:
				self.callbacks.action_performed(speech_label(action), label)
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
		else:
			raise RuntimeError("Unsupported computer action: %s" % action_type)

	def _click(self, action, capture, count=1):
		x, y = capture.to_screen(_field(action, "x"), _field(action, "y"))
		button = _field(action, "button", "left")
		keys = _field(action, "keys", []) or _field(action, "modifiers", [])
		with _held_keys(keys):
			_move_to(x, y)
			for _ in range(count):
				_mouse_click(button)

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
				ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, -scroll_y, 0)
			if scroll_x:
				ctypes.windll.user32.mouse_event(MOUSEEVENTF_HWHEEL, 0, 0, scroll_x, 0)

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
		_send_unicode_text(text)


def looks_risky(actions):
	risky_words = (
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
	for action in actions:
		text = "%s %s %s" % (
			describe_action(action),
			_field(action, "target", ""),
			_field(action, "text", ""),
		)
		text = text.lower()
		if any(word in text for word in risky_words):
			return True
	return False


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
	elif action_type == "screenshot":
		pass
	else:
		_add_generic_values(parts, action, exclude=("action", "target"))
	return " ".join(parts)


def speech_label(action):
	action_type = _field(action, "action", "unknown")
	return str(action_type).replace("_", " ").title()


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
	_mouse_up(button)


def _mouse_down(button):
	flag = {
		"left": winUser.MOUSEEVENTF_LEFTDOWN,
		"right": winUser.MOUSEEVENTF_RIGHTDOWN,
		"middle": winUser.MOUSEEVENTF_MIDDLEDOWN,
	}.get(str(button).lower(), winUser.MOUSEEVENTF_LEFTDOWN)
	winUser.mouse_event(flag, 0, 0, None, None)


def _mouse_up(button):
	flag = {
		"left": winUser.MOUSEEVENTF_LEFTUP,
		"right": winUser.MOUSEEVENTF_RIGHTUP,
		"middle": winUser.MOUSEEVENTF_MIDDLEUP,
	}.get(str(button).lower(), winUser.MOUSEEVENTF_LEFTUP)
	winUser.mouse_event(flag, 0, 0, None, None)


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
	extra = ctypes.c_ulong(0)
	flags = KEYEVENTF_KEYUP if is_up else 0
	inp = _INPUT()
	inp.type = 1 # INPUT_KEYBOARD
	inp.ki = _KEYBDINPUT(vk_code, 0, flags, 0, None)
	ctypes.windll.user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))


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
	chunk_size = 64
	for start in range(0, len(code_units), chunk_size):
		chunk = code_units[start:start + chunk_size]
		inputs = (_INPUT * (len(chunk) * 2))()
		for index, code_unit in enumerate(chunk):
			down = index * 2
			up = down + 1
			inputs[down].type = 1 # INPUT_KEYBOARD
			inputs[down].ki = _KEYBDINPUT(0, code_unit, KEYEVENTF_UNICODE, 0, None)
			inputs[up].type = 1 # INPUT_KEYBOARD
			inputs[up].ki = _KEYBDINPUT(0, code_unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None)
		ctypes.windll.user32.SendInput(len(inputs), ctypes.pointer(inputs), ctypes.sizeof(_INPUT))
		time.sleep(0.01)


def _send_unicode(char):
	if ord(char) > 0xFFFF:
		data = char.encode("utf-16-le", "surrogatepass")
		for index in range(0, len(data), 2):
			_send_unicode(chr(int.from_bytes(data[index:index + 2], "little")))
		return
	inputs = (_INPUT * 2)()

	# Down
	inputs[0].type = 1 # INPUT_KEYBOARD
	inputs[0].ki = _KEYBDINPUT(0, ord(char), KEYEVENTF_UNICODE, 0, None)

	# Up
	inputs[1].type = 1 # INPUT_KEYBOARD
	inputs[1].ki = _KEYBDINPUT(0, ord(char), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None)

	ctypes.windll.user32.SendInput(2, ctypes.pointer(inputs), ctypes.sizeof(_INPUT))


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

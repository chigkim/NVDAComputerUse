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
	def __init__(self, step_delay_ms=500, callbacks=None):
		self.step_delay = step_delay_ms / 1000.0
		self.callbacks = callbacks

	def perform(self, actions, capture):
		last_type = None
		for action in actions:
			action_type = _field(action, "type")
			label = describe_action(action, capture)
			self.perform_one(action, capture)
			if self.callbacks is not None:
				if action_type in ("wait", "screenshot") and action_type == last_type:
					# Already announced this type in this sequence, skip speech
					self.callbacks.log_only(label) # Record in log without speaking
				else:
					self.callbacks.action_performed(speech_label(action), label)
			elif self.step_delay:
				time.sleep(self.step_delay)
			last_type = action_type

	def perform_one(self, action, capture):
		action_type = _field(action, "type")
		if action_type == "click":
			self._click(action, capture, count=1)
		elif action_type == "double_click":
			self._click(action, capture, count=2)
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
			time.sleep(max(self.step_delay, 0.25))
		else:
			raise RuntimeError("Unsupported computer action: %s" % action_type)

	def _click(self, action, capture, count=1):
		x, y = capture.to_screen(_field(action, "x"), _field(action, "y"))
		button = _field(action, "button", "left")
		keys = _field(action, "keys", [])
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
		for char in text:
			_send_unicode(char)


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
		text = "%s %s" % (_field(action, "type", ""), _field(action, "text", ""))
		text = text.lower()
		if any(word in text for word in risky_words):
			return True
	return False


def describe_action(action, capture=None):
	action_type = _field(action, "type", "unknown")
	if action_type == "click":
		return _point_action("Click", action, capture)
	if action_type == "double_click":
		return _point_action("Double click", action, capture)
	if action_type == "move":
		return _point_action("Move", action, capture)
	if action_type == "drag":
		path = _field(action, "path", []) or []
		if path:
			x, y = _point(path[-1])
			if capture is not None:
				x, y = capture.to_screen(x, y)
			return "Drag to %s, %s" % (x, y)
		return "Drag"
	if action_type == "scroll":
		scroll_y = int(_field(action, "scrollY", _field(action, "scroll_y", _field(action, "dy", 0))))
		scroll_x = int(_field(action, "scrollX", _field(action, "scroll_x", _field(action, "dx", 0))))
		x = _field(action, "x", None)
		y = _field(action, "y", None)
		location = ""
		if x is not None and y is not None:
			if capture is not None:
				x, y = capture.to_screen(x, y)
			location = " at %s, %s" % (x, y)
		return "Scroll %s, %s%s" % (scroll_x, scroll_y, location)
	if action_type == "keypress":
		keys = _field(action, "keys", []) or []
		if isinstance(keys, str):
			keys = [keys]
		return "Key press " + "+".join(str(key) for key in keys)
	if action_type == "type":
		text = _field(action, "text", "")
		return "Type %s character%s" % (len(text), "" if len(text) == 1 else "s")
	if action_type == "wait":
		return "Wait"
	if action_type == "screenshot":
		return "Screenshot"
	return str(action_type).replace("_", " ").title()


def speech_label(action):
	action_type = _field(action, "type", "unknown")
	return str(action_type).replace("_", " ").title()


def _point_action(name, action, capture):
	x = _field(action, "x", "?")
	y = _field(action, "y", "?")
	if capture is not None and x != "?" and y != "?":
		x, y = capture.to_screen(x, y)
	return "%s %s, %s" % (name, x, y)


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
			ctypes.windll.user32.keybd_event(code, 0, 0, 0)

	def __exit__(self, exc_type, exc, tb):
		for code in reversed(self.keys):
			ctypes.windll.user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)


def _press_key(key):
	code = _key_code(key)
	if code is None:
		if isinstance(key, str):
			for char in key:
				_send_unicode(char)
		return
	ctypes.windll.user32.keybd_event(code, 0, 0, 0)
	ctypes.windll.user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)


def _key_code(key):
	key = str(key).lower().replace("+", "").replace("arrow", "")
	if key in ("return",):
		key = "enter"
	if len(key) == 1:
		return ctypes.windll.user32.VkKeyScanW(ctypes.c_wchar(key)) & 0xFF
	return VK.get(key)


def _send_unicode(char):
	if ord(char) > 0xFFFF:
		data = char.encode("utf-16-le", "surrogatepass")
		for index in range(0, len(data), 2):
			_send_unicode(chr(int.from_bytes(data[index:index + 2], "little")))
		return
	extra = ctypes.c_ulong(0)
	input_down = _INPUT()
	input_down.type = 1
	input_down.ki = _KEYBDINPUT(0, ord(char), KEYEVENTF_UNICODE, 0, ctypes.pointer(extra))
	input_up = _INPUT()
	input_up.type = 1
	input_up.ki = _KEYBDINPUT(0, ord(char), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))
	ctypes.windll.user32.SendInput(1, ctypes.pointer(input_down), ctypes.sizeof(input_down))
	ctypes.windll.user32.SendInput(1, ctypes.pointer(input_up), ctypes.sizeof(input_up))


class _KEYBDINPUT(ctypes.Structure):
	_fields_ = [
		("wVk", ctypes.wintypes.WORD),
		("wScan", ctypes.wintypes.WORD),
		("dwFlags", ctypes.wintypes.DWORD),
		("time", ctypes.wintypes.DWORD),
		("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
	]


class _MOUSEINPUT(ctypes.Structure):
	_fields_ = [
		("dx", ctypes.wintypes.LONG),
		("dy", ctypes.wintypes.LONG),
		("mouseData", ctypes.wintypes.DWORD),
		("dwFlags", ctypes.wintypes.DWORD),
		("time", ctypes.wintypes.DWORD),
		("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
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

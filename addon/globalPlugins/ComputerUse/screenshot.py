import base64
import ctypes
import ctypes.wintypes
import os
import tempfile

import api
import wx


class Capture:
	def __init__(
		self,
		image_url,
		left,
		top,
		width,
		height,
		display_width,
		display_height,
		app_name,
		app_version,
		window_name,
	):
		self.image_url = image_url
		self.left = left
		self.top = top
		self.width = width
		self.height = height
		self.display_width = display_width
		self.display_height = display_height
		self.app_name = app_name
		self.app_version = app_version
		self.window_name = window_name

	@property
	def scale_x(self):
		return self.width / float(self.display_width or self.width)

	@property
	def scale_y(self):
		return self.height / float(self.display_height or self.height)

	def to_screen(self, x, y):
		return int(round(self.left + (x * self.scale_x))), int(round(self.top + (y * self.scale_y)))


def capture_foreground_window():
	obj = api.getForegroundObject()
	left, top, width, height, hwnd = _foreground_rect(obj)
	process_path = _process_path(hwnd)
	if width <= 0 or height <= 0:
		raise RuntimeError("The foreground window has no visible size.")
	bitmap = wx.Bitmap(width, height)
	screen = wx.ScreenDC()
	memory = wx.MemoryDC()
	memory.SelectObject(bitmap)
	try:
		if not memory.Blit(0, 0, width, height, screen, left, top):
			raise RuntimeError("Unable to capture the foreground window.")
	finally:
		memory.SelectObject(wx.NullBitmap)
	image = bitmap.ConvertToImage()
	display_width, display_height = _logical_window_size(hwnd, width, height)
	if (display_width, display_height) != (width, height):
		image = image.Scale(display_width, display_height, wx.IMAGE_QUALITY_HIGH)
	path = tempfile.mktemp(suffix=".png")
	try:
		if not image.SaveFile(path, wx.BITMAP_TYPE_PNG):
			raise RuntimeError("Unable to encode foreground window screenshot.")
		with open(path, "rb") as image_file:
			data = base64.b64encode(image_file.read()).decode("ascii")
	finally:
		try:
			os.unlink(path)
		except OSError:
			pass
	return Capture(
		image_url="data:image/png;base64," + data,
		left=left,
		top=top,
		width=width,
		height=height,
		display_width=display_width,
		display_height=display_height,
		app_name=_app_name(obj, process_path),
		app_version=_app_version(process_path),
		window_name=_window_name(obj, hwnd),
	)


def _foreground_rect(obj):
	hwnd = int(getattr(obj, "windowHandle", 0) or 0)
	if hwnd:
		rect = ctypes.wintypes.RECT()
		try:
			if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
				width = int(rect.right - rect.left)
				height = int(rect.bottom - rect.top)
				if width > 0 and height > 0:
					return int(rect.left), int(rect.top), width, height, hwnd
		except Exception:
			pass
	left, top, width, height = _normalize_location(obj.location)
	return left, top, width, height, hwnd


def _normalize_location(location):
	try:
		left, top, width, height = location
	except TypeError:
		left = location.left
		top = location.top
		width = location.width
		height = location.height
	return int(left), int(top), int(width), int(height)


def _logical_window_size(hwnd, width, height):
	dpi = 96
	if hwnd:
		try:
			dpi = int(ctypes.windll.user32.GetDpiForWindow(hwnd))
		except Exception:
			dpi = 96
	if dpi <= 0:
		dpi = 96
	scale = dpi / 96.0
	return max(1, int(round(width / scale))), max(1, int(round(height / scale)))


def _app_name(obj, process_path=""):
	app_module = getattr(obj, "appModule", None)
	name = getattr(app_module, "appName", "") or getattr(app_module, "appNameShort", "")
	if name:
		return str(name)
	if process_path:
		return os.path.splitext(os.path.basename(process_path))[0]
	process_id = getattr(obj, "processID", None)
	if process_id:
		return "pid %s" % process_id
	return "Unknown"


def _window_name(obj, hwnd):
	if hwnd:
		try:
			length = int(ctypes.windll.user32.GetWindowTextLengthW(hwnd))
			if length > 0:
				buffer = ctypes.create_unicode_buffer(length + 1)
				ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
				if buffer.value:
					return buffer.value
		except Exception:
			pass
	name = getattr(obj, "name", "") or ""
	return str(name) if name else "Unknown"


def _process_path(hwnd):
	if not hwnd:
		return ""
	process_id = ctypes.wintypes.DWORD()
	try:
		ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
		if not process_id.value:
			return ""
		PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
		open_process = ctypes.windll.kernel32.OpenProcess
		open_process.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
		open_process.restype = ctypes.wintypes.HANDLE
		handle = open_process(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value)
		if not handle:
			return ""
		try:
			query_path = ctypes.windll.kernel32.QueryFullProcessImageNameW
			query_path.argtypes = [
				ctypes.wintypes.HANDLE,
				ctypes.wintypes.DWORD,
				ctypes.wintypes.LPWSTR,
				ctypes.POINTER(ctypes.wintypes.DWORD),
			]
			query_path.restype = ctypes.wintypes.BOOL
			size = ctypes.wintypes.DWORD(32768)
			buffer = ctypes.create_unicode_buffer(size.value)
			if query_path(handle, 0, buffer, ctypes.byref(size)):
				return buffer.value
		finally:
			ctypes.windll.kernel32.CloseHandle(handle)
	except Exception:
		pass
	return ""


def _app_version(process_path):
	if not process_path:
		return ""
	try:
		size = ctypes.windll.version.GetFileVersionInfoSizeW(process_path, None)
		if not size:
			return ""
		data = ctypes.create_string_buffer(size)
		if not ctypes.windll.version.GetFileVersionInfoW(process_path, 0, size, data):
			return ""
		pointer = ctypes.c_void_p()
		length = ctypes.wintypes.UINT()
		if not ctypes.windll.version.VerQueryValueW(data, "\\", ctypes.byref(pointer), ctypes.byref(length)):
			return ""
		info = ctypes.cast(pointer, ctypes.POINTER(_VS_FIXEDFILEINFO)).contents
		if info.dwSignature != 0xFEEF04BD:
			return ""
		return "%d.%d.%d.%d" % (
			info.dwFileVersionMS >> 16,
			info.dwFileVersionMS & 0xFFFF,
			info.dwFileVersionLS >> 16,
			info.dwFileVersionLS & 0xFFFF,
		)
	except Exception:
		return ""


class _VS_FIXEDFILEINFO(ctypes.Structure):
	_fields_ = [
		("dwSignature", ctypes.wintypes.DWORD),
		("dwStrucVersion", ctypes.wintypes.DWORD),
		("dwFileVersionMS", ctypes.wintypes.DWORD),
		("dwFileVersionLS", ctypes.wintypes.DWORD),
		("dwProductVersionMS", ctypes.wintypes.DWORD),
		("dwProductVersionLS", ctypes.wintypes.DWORD),
		("dwFileFlagsMask", ctypes.wintypes.DWORD),
		("dwFileFlags", ctypes.wintypes.DWORD),
		("dwFileOS", ctypes.wintypes.DWORD),
		("dwFileType", ctypes.wintypes.DWORD),
		("dwFileSubtype", ctypes.wintypes.DWORD),
		("dwFileDateMS", ctypes.wintypes.DWORD),
		("dwFileDateLS", ctypes.wintypes.DWORD),
	]

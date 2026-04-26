import base64
import ctypes
import ctypes.wintypes
import os
import tempfile

import api
import wx


class Capture:
	def __init__(self, image_url, left, top, width, height, display_width, display_height):
		self.image_url = image_url
		self.left = left
		self.top = top
		self.width = width
		self.height = height
		self.display_width = display_width
		self.display_height = display_height

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

"""Standalone smoke tests for the Computer Use NVDA add-on.

This script does not start NVDA. It stubs the small NVDA surface the add-on
imports, then exercises dependency packaging checks and the computer-use loop
with a fake OpenAI client.

Run from the repository root:
	python computerUse\tools\smoke_test.py

Optional:
	python computerUse\tools\smoke_test.py --check-openai-import

The optional import check only works when this Python process has the same
architecture as the bundled wheels. The release bundle is currently packaged
for 32-bit NVDA, so a 64-bit Python will skip that import check by default.
"""

from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path
import platform
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "addon" / "globalPlugins" / "computerUse"
LIB_DIR = PLUGIN_DIR / "lib"


def install_nvda_stubs() -> None:
	"""Install lightweight modules needed to import add-on code outside NVDA."""
	mouse_handler = types.ModuleType("mouseHandler")
	mouse_handler.executeMouseMoveEvent = lambda x, y: None
	sys.modules["mouseHandler"] = mouse_handler

	win_user = types.ModuleType("winUser")
	win_user.MOUSEEVENTF_LEFTDOWN = 0x0002
	win_user.MOUSEEVENTF_LEFTUP = 0x0004
	win_user.MOUSEEVENTF_RIGHTDOWN = 0x0008
	win_user.MOUSEEVENTF_RIGHTUP = 0x0010
	win_user.MOUSEEVENTF_MIDDLEDOWN = 0x0020
	win_user.MOUSEEVENTF_MIDDLEUP = 0x0040
	win_user.setCursorPos = lambda x, y: None
	win_user.mouse_event = lambda *args, **kwargs: None
	sys.modules["winUser"] = win_user

	api = types.ModuleType("api")
	api.getForegroundObject = lambda: types.SimpleNamespace(location=(0, 0, 640, 480))
	sys.modules["api"] = api

	wx = types.ModuleType("wx")
	wx.BITMAP_TYPE_PNG = 15
	wx.IMAGE_QUALITY_HIGH = 1
	wx.NullBitmap = object()
	sys.modules["wx"] = wx


def check_packaged_dependencies() -> None:
	print("Dependency package check")
	required = [
		LIB_DIR / "openai" / "__init__.py",
		LIB_DIR / "typing_extensions.py",
		LIB_DIR / "zoneinfo" / "__init__.py",
		LIB_DIR / "zoneinfo" / "_zoneinfo.py",
		LIB_DIR / "pydantic_core" / "_pydantic_core.cp311-win32.pyd",
		LIB_DIR / "jiter" / "jiter.cp311-win32.pyd",
	]
	for path in required:
		_assert(path.exists(), f"Missing required file: {path}")
		print(f"  ok: {path.relative_to(ROOT)}")

	for path in LIB_DIR.rglob("*.pyd"):
		_assert("win_amd64" not in path.name, f"Unexpected 64-bit wheel in package: {path}")
		print(f"  pyd: {path.relative_to(ROOT)}")

	_assert(not any("__pycache__" in path.parts for path in LIB_DIR.rglob("*")), "Package contains __pycache__")
	_assert(not (LIB_DIR / "bin").exists(), "Package contains unused CLI bin directory")
	print("  ok: no __pycache__ or CLI bin directory")


def check_openai_import() -> None:
	arch = platform.architecture()[0]
	if arch != "32bit":
		print(f"OpenAI import check skipped: bundled wheels are win32, current Python is {arch}.")
		return
	sys.path.insert(0, str(LIB_DIR))
	import openai
	print(f"OpenAI import ok: {openai.__version__}")


class FakeUsageDetails:
	cached_tokens = 3


class FakeUsage:
	def __init__(self, turn: int):
		self.input_tokens = 100 + turn
		self.output_tokens = 20 + turn
		self.total_tokens = self.input_tokens + self.output_tokens
		self.input_tokens_details = FakeUsageDetails()


class FakeAction:
	def __init__(self, action_type: str, **kwargs):
		self.type = action_type
		for key, value in kwargs.items():
			setattr(self, key, value)


class FakeComputerCall:
	type = "computer_call"
	call_id = "fake-call"

	def __init__(self, actions):
		self.actions = actions


class FakeMessageContent:
	text = "Finished fake task."


class FakeMessage:
	type = "message"
	content = [FakeMessageContent()]


class FakeResponse:
	def __init__(self, response_id: str, output, turn: int):
		self.id = response_id
		self.output = output
		self.output_text = None
		self.usage = FakeUsage(turn)


class FakeResponses:
	def __init__(self):
		self.calls = 0

	def create(self, **kwargs):
		self.calls += 1
		if self.calls == 1:
			return FakeResponse(
				"resp-1",
				[
					FakeComputerCall([
						FakeAction("click", x=10, y=20, button="left"),
						FakeAction("type", text="secret text not logged"),
					])
				],
				self.calls,
			)
		return FakeResponse("resp-2", [FakeMessage()], self.calls)


class FakeOpenAI:
	def __init__(self, api_key=None):
		self.api_key = api_key
		self.responses = FakeResponses()


class FakeCapture:
	image_url = "data:image/png;base64,ZmFrZQ=="
	left = 100
	top = 200
	width = 640
	height = 480
	display_width = 640
	display_height = 480

	def to_screen(self, x, y):
		return self.left + int(x), self.top + int(y)


class FakeCallbacks:
	def __init__(self):
		self.statuses = []
		self.spoken = []
		self.logged = []

	def status(self, message):
		self.statuses.append(message)

	def confirm_risky(self, description):
		return True

	def action_performed(self, speech_label, log_label):
		self.spoken.append(speech_label)
		self.logged.append(log_label)
		if self.session is not None:
			self.session.record_action(log_label)


class NoOpActionRunner:
	def __init__(self, step_delay_ms=0, callbacks=None):
		self.callbacks = callbacks

	def perform(self, actions, capture):
		from computerUse.actions import describe_action, speech_label
		for action in actions:
			self.callbacks.action_performed(speech_label(action), describe_action(action, capture))


def run_fake_session() -> None:
	print("Fake session check")
	install_nvda_stubs()
	sys.path.insert(0, str(PLUGIN_DIR.parent))

	fake_openai = types.ModuleType("openai")
	fake_openai.__file__ = str(LIB_DIR / "openai" / "__init__.py")
	fake_openai.OpenAI = FakeOpenAI
	sys.modules["openai"] = fake_openai

	package = types.ModuleType("computerUse")
	package.__path__ = [str(PLUGIN_DIR)]
	package.__package__ = "computerUse"
	sys.modules["computerUse"] = package

	client = importlib.import_module("computerUse.openai_client")
	client.capture_foreground_window = lambda: FakeCapture()
	client.ActionRunner = NoOpActionRunner

	callbacks = FakeCallbacks()
	session = client.ComputerUseSession(
		api_key="test-key",
		model="test-model",
		max_steps=5,
		step_delay_ms=0,
		require_confirmation=True,
		callbacks=callbacks,
	)
	callbacks.session = session
	result = session.run("click and type")
	log_text = session.format_log()
	print(f"  result: {result}")
	print("  spoken:", ", ".join(callbacks.spoken))
	print("  log:")
	print(_indent(log_text))

	_assert(callbacks.spoken == ["Screenshot", "Click", "Type", "Screenshot"], "Unexpected speech labels")
	_assert("Click 110, 220" in log_text, "Detailed click coordinates missing from log")
	_assert("secret text not logged" not in log_text, "Typed text leaked into log")
	_assert("Type 22 characters" in log_text, "Type action count missing from log")
	_assert("Total usage:" in log_text, "Total usage missing from log")

	from computerUse.actions import ActionRunner
	ActionRunner(step_delay_ms=0).perform([FakeAction("click", x=10, y=20, keys=None)], FakeCapture())


def _indent(text: str) -> str:
	return "\n".join("    " + line for line in text.splitlines())


def _assert(condition: bool, message: str) -> None:
	if not condition:
		raise AssertionError(message)


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--check-openai-import", action="store_true")
	args = parser.parse_args()

	check_packaged_dependencies()
	if args.check_openai_import:
		check_openai_import()
	run_fake_session()
	print("Smoke tests passed.")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

import os
import sys
import importlib
import builtins
import json
import time
import logHandler

log = logHandler.log

_ = getattr(builtins, "_", None)
if not callable(_):
	try:
		from languageHandler import _ as _lh
		if callable(_lh):
			_ = _lh
	except ImportError:
		pass

if not callable(_):
	_ = lambda x: x

from .actions import ActionRunner, describe_action, looks_risky
from .screenshot import capture_foreground_window


def ensure_openai_on_path():
	lib_path = os.path.join(os.path.dirname(__file__), "lib")
	if os.path.isdir(lib_path) and lib_path not in sys.path:
		sys.path.insert(0, lib_path)
	importlib.invalidate_caches()
	for module_name in (
		"annotated_types",
		"anyio",
		"certifi",
		"colorama",
		"distro",
		"h11",
		"httpcore",
		"httpx",
		"idna",
		"jiter",
		"openai",
		"pydantic",
		"pydantic_core",
		"sniffio",
		"tqdm",
		"typing_extensions",
		"typing_inspection",
		"zoneinfo",
	):
		_remove_external_module(module_name, lib_path)


def _remove_external_module(module_name, lib_path):
	module = sys.modules.get(module_name)
	if module is None:
		return
	module_file = getattr(module, "__file__", "") or ""
	try:
		module_path = os.path.abspath(module_file)
	except (TypeError, ValueError):
		module_path = ""
	lib_path = os.path.abspath(lib_path)
	if module_path and module_path.startswith(lib_path):
		return
	if module_name == "typing_extensions" and hasattr(module, "Sentinel"):
		return
	for loaded_name in list(sys.modules):
		if loaded_name == module_name or loaded_name.startswith(module_name + "."):
			del sys.modules[loaded_name]


class ComputerUseSession:
	def __init__(self, api_key, model, max_steps, step_delay_ms, require_confirmation, callbacks, base_url=None, trim_conversation=True, debug_logging=False):
		ensure_openai_on_path()
		from openai import OpenAI

		client_args = {"api_key": api_key}
		if base_url:
			client_args["base_url"] = base_url
		self.client = OpenAI(**client_args)
		self.model = model
		self.max_steps = max_steps
		self.require_confirmation = require_confirmation
		self.trim_conversation = trim_conversation
		self.debug_logging = debug_logging
		self.callbacks = callbacks
		self.runner = ActionRunner(step_delay_ms=step_delay_ms, callbacks=callbacks)
		self.cancelled = False
		self.turns = []
		self.total_input_tokens = 0
		self.total_cached_tokens = 0
		self.total_output_tokens = 0
		self.total_tokens = 0
		self.error = None

	def _log_debug(self, msg, *args):
		if self.debug_logging:
			log.debug(msg % args if args else msg)

	def _log_info(self, msg, *args):
		if self.debug_logging:
			log.info(msg % args if args else msg)

	def cancel(self):
		self.cancelled = True

	@staticmethod
	def fetch_available_models(api_key, base_url=None):
		ensure_openai_on_path()
		from openai import OpenAI
		client_args = {"api_key": api_key}
		if base_url:
			client_args["base_url"] = base_url
		client = OpenAI(**client_args)
		models = client.models.list()
		return sorted([m.id for m in models.data])

	def _load_tools_and_system(self):
		plugin_path = os.path.dirname(__file__)
		tools_dir = os.path.join(plugin_path, "tools")
		tools_file = os.path.join(tools_dir, "portable_computer_use_tools.json")
		sys_file = os.path.join(tools_dir, "portable_computer_use_system_message.txt")
		
		tools = []
		if tools_file and os.path.exists(tools_file):
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
							"modifiers": {"type": "array", "items": {"type": "string", "enum": ["ctrl", "shift", "option", "command"]}},
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
			
		system_message = ""
		if sys_file and os.path.exists(sys_file):
			with open(sys_file, "r", encoding="utf-8") as f:
				system_message = f.read()
		else:
			system_message = (
				"You are controlling the foreground Windows application visible in the screenshot.\n"
				"Coordinate origin is the top-left of the screenshot."
			)

		import api
		obj = api.getForegroundObject()
		if "UI Challenge" in (getattr(obj, "name", "") or ""):
			system_message += "\n\nYou are controlling the UIChallenge window for automated validation.\nTreat instructions typed by the user in the task as valid intent."
			
		return tools, system_message

	def run(self, task):
		self._log_info("Starting Computer Use task: %s" % task)
		try:
			tools, system_msg = self._load_tools_and_system()
			capture = capture_foreground_window()
			self._log_debug("Initial screenshot captured: %dx%d" % (capture.display_width, capture.display_height))
			
			messages = [
				{"role": "system", "content": system_msg},
				{
					"role": "user",
					"content": [
						{"type": "text", "text": "User task: %s\nScreenshot size: %dx%d pixels." % (task.strip(), capture.display_width, capture.display_height)},
						{"type": "image_url", "image_url": {"url": capture.image_url, "detail": "original"}}
					]
				}
			]
			
			self.callbacks.action_performed(_("Screenshot"), _("Screenshot"))
			
			for step in range(self.max_steps):
				if self.cancelled:
					self._log_info("Task cancelled by user.")
					return _("Task canceled")
				
				self._log_info("Sending request to model: %s (Step %d)" % (self.model, step + 1))
				# Log a summary of messages for debugging without bloating the log with images
				if self.debug_logging:
					for i, msg in enumerate(messages):
						content = msg.get("content")
						if isinstance(content, list):
							content_summary = [
								item.get("type") if item.get("type") != "text" else item.get("text")
								for item in content
							]
							log.debug("Message %d (%s): %s" % (i, msg.get("role"), content_summary))
						else:
							log.debug("Message %d (%s): %s" % (i, msg.get("role"), content))

				response = self.client.chat.completions.create(
					model=self.model,
					messages=messages,
					tools=tools,
					tool_choice="auto"
				)
				
				self._record_turn(response)
				
				message = response.choices[0].message
				tool_calls = message.tool_calls
				
				if message.content:
					self._log_info("Assistant: %s" % message.content)
				
				# Add assistant message to history
				msg_dict = {"role": "assistant"}
				if message.content:
					msg_dict["content"] = message.content
				if tool_calls:
					msg_dict["tool_calls"] = []
					for tc in tool_calls:
						self._log_info("Tool Call: %s(%s)" % (tc.function.name, tc.function.arguments))
						msg_dict["tool_calls"].append({
							"id": tc.id,
							"type": "function",
							"function": {"name": tc.function.name, "arguments": tc.function.arguments}
						})
				messages.append(msg_dict)
				
				if not tool_calls:
					self._log_info("No more tool calls. Task finished.")
					return message.content or _("Computer Use finished.")
				
				# Perform actions
				screenshot_requested = False
				for tc in tool_calls:
					if self.cancelled:
						return _("Task canceled")
					
					if tc.function.name == "computer":
						action = json.loads(tc.function.arguments)
						if action.get("action") == "screenshot":
							screenshot_requested = True
						
						if self.require_confirmation and looks_risky([action]):
							if not self.callbacks.confirm_risky(describe_action(action, capture)):
								self._log_info("Action rejected by user confirmation.")
								return _("Stopped before a risky action.")
						
						try:
							self.runner.perform([action], capture)
							result_str = "Success"
						except Exception as e:
							result_str = "Error: %s" % e
							log.error("Action execution failed: %s" % result_str)
						
						messages.append({
							"role": "tool",
							"tool_call_id": tc.id,
							"content": result_str
						})
					else:
						log.warning("Unsupported tool call: %s" % tc.function.name)
						messages.append({
							"role": "tool",
							"tool_call_id": tc.id,
							"content": "Unsupported tool"
						})
				
				self._sanitize_messages(messages)
				if screenshot_requested:
					capture = capture_foreground_window()
					self._log_debug("Requested screenshot captured: %dx%d" % (capture.display_width, capture.display_height))
					messages.append({
						"role": "user",
						"content": [
							{"type": "text", "text": "Latest screenshot. Size: %dx%d pixels." % (capture.display_width, capture.display_height)},
							{"type": "image_url", "image_url": {"url": capture.image_url, "detail": "original"}}
						]
					})
				
			self._log_info("Reached maximum steps (%d)" % self.max_steps)
			return _("Stopped after reaching the configured maximum of {max_steps} steps.").format(max_steps=self.max_steps)
		except Exception as exc:
			log.error("Computer Use session encountered an error", exc_info=True)
			self.error = str(exc)
			raise

	def _sanitize_messages(self, messages):
		# 1. Strip images from all existing messages to save tokens.
		for msg in messages:
			content = msg.get("content")
			if isinstance(content, list):
				# Filter out image_url items
				msg["content"] = [item for item in content if item.get("type") != "image_url"]
				# If we only have one text item left, convert to plain string
				if len(msg["content"]) == 1 and msg["content"][0].get("type") == "text":
					msg["content"] = msg["content"][0]["text"]
				elif not msg["content"]:
					msg["content"] = "Previous turn"

		if not self.trim_conversation:
			self._log_debug("Current message history length: %d" % len(messages))
			return

		# 2. History length management:
		# Keep System (0), Task (1), and the last 20 messages to preserve context.
		if len(messages) > 22:
			self._log_debug("Truncating history from %d messages" % len(messages))
			new_messages = [messages[0], messages[1]]
			# Find a safe cut point in the tail to avoid splitting assistant/tool pairs.
			tail = messages[-20:]
			while tail and tail[0].get("role") == "tool":
				tail.pop(0)
			new_messages.extend(tail)
			messages[:] = new_messages
		
		self._log_debug("Current message history length: %d" % len(messages))

	def record_action(self, label):
		self._record_action(label)

	def _record_turn(self, response):
		usage = getattr(response, "usage", None)
		input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
		output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
		total_tokens = int(getattr(usage, "total_tokens", input_tokens + output_tokens) or 0)
		
		# Cached tokens handling
		cached_tokens = 0
		cached = getattr(usage, "prompt_tokens_details", None)
		if cached:
			cached_tokens = int(getattr(cached, "cached_tokens", 0) or 0)
			
		self.total_input_tokens += input_tokens
		self.total_cached_tokens += cached_tokens
		self.total_output_tokens += output_tokens
		self.total_tokens += total_tokens
		self.turns.append({
			"input": input_tokens,
			"cached": cached_tokens,
			"output": output_tokens,
			"total": total_tokens,
			"actions": [],
		})

	def _record_action(self, label):
		if not self.turns:
			self.turns.append({
				"input": 0,
				"cached": 0,
				"output": 0,
				"total": 0,
				"actions": [],
			})
		self.turns[-1]["actions"].append(label)

	def format_log(self):
		lines = []
		for index, turn in enumerate(self.turns, start=1):
			lines.append(
				"Turn {index}: {total} tokens [input {input} (cache {cached}) output {output}]".format(
					index=index,
					total=turn["total"],
					input=turn["input"],
					cached=turn["cached"],
					output=turn["output"],
				)
			)
			lines.extend(turn["actions"])
		lines.append("")
		lines.append(
			"Total usage: {total} tokens [input {input} (cache {cached}) output {output}]".format(
				total=self.total_tokens,
				input=self.total_input_tokens,
				cached=self.total_cached_tokens,
				output=self.total_output_tokens,
			)
		)
		if self.error:
			lines.append("")
			lines.append(_("Error: {error}").format(error=self.error))
		return "\n".join(lines)

# -*- coding: UTF-8 -*-

import logHandler
import threading
import builtins

import addonHandler
import globalPluginHandler
import globalVars
import gui
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel, SettingsDialog
import ui
import wx

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

from . import config_handler
from .openai_client import ComputerUseSession


log = logHandler.log

try:
	addonHandler.initTranslation()
except addonHandler.AddonError:
	log.warning("Could not initialise Computer Use translations.")


class ComputerUseSettingsPanel(SettingsPanel):
	title = _("Computer Use")

	def makeSettings(self, settingsSizer):
		settings = config_handler.config["ComputerUse"]
		helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.base_url = helper.addLabeledControl(_("URL:"), wx.TextCtrl)
		self.base_url.SetValue(settings["base_url"])
		self.api_key = helper.addLabeledControl(_("API Key:"), wx.TextCtrl, style=wx.TE_PASSWORD)
		self.api_key.SetValue(settings["api_key"])
		
		# Model selection with Fetch button
		model_sizer = wx.BoxSizer(wx.HORIZONTAL)
		model_label = wx.StaticText(self, label=_("Model:"))
		model_sizer.Add(model_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
		self.model = wx.TextCtrl(self, value=settings["model"])
		self.model.SetName(_("Model:"))
		model_sizer.Add(self.model, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=5)
		self.fetch_models_btn = wx.Button(self, label=_("Fetch Models"))
		model_sizer.Add(self.fetch_models_btn)
		settingsSizer.Add(model_sizer, flag=wx.EXPAND | wx.ALL, border=guiHelper.BORDER_FOR_DIALOGS)
		self.fetch_models_btn.Bind(wx.EVT_BUTTON, self.on_fetch_models)

		self.max_steps = helper.addLabeledControl(
			_("Maximum steps:"),
			gui.nvdaControls.SelectOnFocusSpinCtrl,
			min=1,
			max=100,
			initial=int(settings["max_steps"]),
		)
		self.step_delay = helper.addLabeledControl(
			_("Delay between actions in milliseconds:"),
			gui.nvdaControls.SelectOnFocusSpinCtrl,
			min=0,
			max=10000,
			initial=int(settings["step_delay_ms"]),
		)
		self.require_confirmation = helper.addItem(
			wx.CheckBox(self, label=_("Ask before risky actions"))
		)
		self.require_confirmation.SetValue(bool(settings["require_risky_confirmation"]))
		self.debug_logging = helper.addItem(
			wx.CheckBox(self, label=_("Debug"))
		)
		self.debug_logging.SetValue(bool(settings.get("debug_logging", False)))

	def on_fetch_models(self, event):
		api_key = self.api_key.GetValue().strip()
		base_url = self.base_url.GetValue().strip()
		
		try:
			wx.BeginBusyCursor()
			models = ComputerUseSession.fetch_available_models(api_key, base_url or None)
			if wx.IsBusy():
				wx.EndBusyCursor()
			
			if not models:
				gui.messageBox(_("The server returned an empty list of models."), _("No Models Found"), wx.OK | wx.ICON_INFORMATION, self)
				return
				
			menu = wx.Menu()
			for model in models:
				item = menu.Append(wx.ID_ANY, model)
				self.Bind(wx.EVT_MENU, lambda evt, m=model: self.model.SetValue(m), item)
			
			self.PopupMenu(menu)
			menu.Destroy()
		except Exception as e:
			if wx.IsBusy():
				wx.EndBusyCursor()
			
			error_msg = str(e)
			if "401" in error_msg:
				msg = _("Authentication failed. Please check your API key.")
			elif "404" in error_msg:
				msg = _("Base URL not found. Please check your URL configuration.")
			elif "connection" in error_msg.lower():
				msg = _("Network error. Could not connect to the server.")
			else:
				msg = _("Failed to fetch models: {error}").format(error=error_msg)
				
			gui.messageBox(msg, _("Connection Error"), wx.OK | wx.ICON_ERROR, self)

	def onSave(self):
		settings = config_handler.config["ComputerUse"]
		settings["api_key"] = self.api_key.GetValue()
		settings["base_url"] = self.base_url.GetValue()
		settings["model"] = self.model.GetValue()
		settings["max_steps"] = self.max_steps.GetValue()
		settings["step_delay_ms"] = self.step_delay.GetValue()
		settings["require_risky_confirmation"] = self.require_confirmation.GetValue()
		settings["debug_logging"] = self.debug_logging.GetValue()
		config_handler.config.write()


class TaskDialog(wx.Dialog):
	def __init__(self, parent):
		super().__init__(parent, title=_("Computer Use"), size=(560, 320))
		self.task = None
		main = wx.BoxSizer(wx.VERTICAL)
		label = wx.StaticText(self, label=_("Task to perform in the foreground application:"))
		main.Add(label, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=guiHelper.BORDER_FOR_DIALOGS)
		self.prompt = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_RICH, size=(520, 180))
		main.Add(self.prompt, proportion=1, flag=wx.EXPAND | wx.ALL, border=guiHelper.BORDER_FOR_DIALOGS)
		buttons = self.CreateButtonSizer(wx.OK | wx.CANCEL)
		self.FindWindowById(wx.ID_OK).SetLabel(_("Perform"))
		main.Add(buttons, flag=wx.ALIGN_RIGHT | wx.ALL, border=guiHelper.BORDER_FOR_DIALOGS)
		self.SetSizer(main)
		self.Bind(wx.EVT_BUTTON, self.on_perform, id=wx.ID_OK)
		self.prompt.SetFocus()

	def on_perform(self, event):
		task = self.prompt.GetValue().strip()
		if not task:
			gui.messageBox(_("Enter a task first."), _("Computer Use"), wx.OK | wx.ICON_WARNING, self)
			return
		self.task = task
		self.EndModal(wx.ID_OK)


class _Callbacks:
	def __init__(self, plugin):
		self.plugin = plugin

	def confirm_risky(self, description):
		return self.plugin.confirm_risky(description)

	def action_performed(self, speech_label, log_label):
		return self.plugin.action_performed(speech_label, log_label)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = _("Computer Use")

	def __init__(self, *args, **kwargs):
		super(GlobalPlugin, self).__init__(*args, **kwargs)
		if globalVars.appArgs.secure:
			raise RuntimeError("Computer Use cannot run on secure screens")
		config_handler.load_config()
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(ComputerUseSettingsPanel)
		self.session = None
		self.worker = None

	def terminate(self):
		try:
			gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(ComputerUseSettingsPanel)
		except ValueError:
			pass
		if self.session is not None:
			self.session.cancel()
		super().terminate()

	def report_status(self, message):
		ui.message(message)

	def action_performed(self, speech_label, log_label):
		if self.session is not None:
			self.session.record_action(log_label)
		self.speak_and_wait(speech_label)

	def speak_and_wait(self, message):
		done = threading.Event()
		timeout = max(1.5, min(10.0, 0.35 + len(message) / 9.0))

		def speak():
			try:
				from speech.commands import CallbackCommand
				import speech
				speak_func = getattr(speech, "speak", None)
				if speak_func is None:
					from speech import speech as speech_module
					speak_func = speech_module.speak
				speak_func([message, CallbackCommand(done.set, name="ComputerUseActionComplete")])
			except Exception:
				log.exception("Unable to use speech callback; falling back to timed action announcement")
				ui.message(message)
				wx.CallLater(int(timeout * 1000), done.set)

		wx.CallAfter(speak)
		done.wait(timeout + 1.0)

	def confirm_risky(self, description):
		result = {"value": False}
		done = threading.Event()

		def ask():
			msg = _("Computer Use is about to perform a potentially risky action:\n\n{action}\n\nDo you want to continue?").format(action=description)
			result["value"] = gui.messageBox(msg, _("Computer Use"), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING) == wx.YES
			done.set()

		wx.CallAfter(ask)
		done.wait()
		return result["value"]

	def script_open_task_dialog(self, gesture):
		if self.worker is not None and self.worker.is_alive():
			if self.session is not None:
				self.session.cancel()
			return
		settings = config_handler.config["ComputerUse"]
		if not settings["api_key"]:
			ui.message(_("Set your OpenAI API key in NVDA Settings, Computer Use."))
			return
		dialog = TaskDialog(gui.mainFrame)
		dialog.Raise()

		def callback(result):
			if result != wx.ID_OK or not dialog.task:
				return
			self.start_task(dialog.task)

		gui.runScriptModalDialog(dialog, callback)
	script_open_task_dialog.__doc__ = _("Open a prompt to perform a task in the foreground application using OpenAI Computer Use.")

	def start_task(self, task):
		settings = config_handler.config["ComputerUse"]
		try:
			self.session = ComputerUseSession(
				api_key=settings["api_key"],
				base_url=settings.get("base_url"),
				model=settings["model"],
				max_steps=int(settings["max_steps"]),
				step_delay_ms=int(settings["step_delay_ms"]),
				require_confirmation=bool(settings["require_risky_confirmation"]),
				debug_logging=bool(settings.get("debug_logging", False)),
				callbacks=_Callbacks(self),
			)
		except Exception as exc:
			log.exception("Failed to initialize Computer Use session")
			self.show_run_log(
				_("Computer Use failed: {error}").format(error=str(exc)),
				_("Error: {error}").format(error=str(exc))
			)
			return
		self.worker = threading.Thread(target=self._run_task, args=(task,), daemon=True)
		self.worker.start()

	def _run_task(self, task):
		log_text = ""
		try:
			result = self.session.run(task)
			log_text = self.session.format_log()
		except Exception as exc:
			log.exception("Computer Use task failed")
			result = _("Computer Use failed: {error}").format(error=str(exc))
			if self.session is not None:
				log_text = self.session.format_log()
		wx.CallAfter(self.show_run_log, result, log_text)

	def show_run_log(self, result, log_text):
		ui.message(result)
		if not log_text:
			log_text = _("No Computer Use actions were logged.")
		ui.browseableMessage(log_text, _("Computer Use log"), False)

	__gestures = {
		"kb:shift+control+NVDA+u": "open_task_dialog",
	}

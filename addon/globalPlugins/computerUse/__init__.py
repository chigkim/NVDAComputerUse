# -*- coding: UTF-8 -*-

import logging
import threading

import addonHandler
import globalPluginHandler
import globalVars
import gui
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel
import ui
import wx

from . import config_handler
from .openai_client import ComputerUseSession


log = logging.getLogger(__name__)

try:
	addonHandler.initTranslation()
except addonHandler.AddonError:
	log.warning("Could not initialise Computer Use translations.")


class ComputerUseSettingsPanel(SettingsPanel):
	title = _("Computer Use")

	def makeSettings(self, settingsSizer):
		settings = config_handler.config["computerUse"]
		helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.api_key = helper.addLabeledControl(_("OpenAI API key:"), wx.TextCtrl, style=wx.TE_PASSWORD)
		self.api_key.SetValue(settings["api_key"])
		self.model = helper.addLabeledControl(_("Model:"), wx.TextCtrl)
		self.model.SetValue(settings["model"])
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

	def onSave(self):
		settings = config_handler.config["computerUse"]
		settings["api_key"] = self.api_key.GetValue()
		settings["model"] = self.model.GetValue()
		settings["max_steps"] = self.max_steps.GetValue()
		settings["step_delay_ms"] = self.step_delay.GetValue()
		settings["require_risky_confirmation"] = self.require_confirmation.GetValue()
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

	def status(self, message):
		wx.CallAfter(self.plugin.report_status, message)

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
				speak_func([message, CallbackCommand(done.set, name="computerUseActionComplete")])
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
			ui.message(_("Computer Use cancellation requested."))
			return
		settings = config_handler.config["computerUse"]
		if not settings["api_key"]:
			ui.message(_("Set your OpenAI API key in NVDA Settings, Computer Use."))
			return
		dialog = TaskDialog(gui.mainFrame)

		def callback(result):
			if result != wx.ID_OK or not dialog.task:
				return
			self.start_task(dialog.task)

		gui.runScriptModalDialog(dialog, callback)
	script_open_task_dialog.__doc__ = _("Open a prompt to perform a task in the foreground application using OpenAI Computer Use.")

	def start_task(self, task):
		settings = config_handler.config["computerUse"]
		self.session = ComputerUseSession(
			api_key=settings["api_key"],
			model=settings["model"],
			max_steps=int(settings["max_steps"]),
			step_delay_ms=int(settings["step_delay_ms"]),
			require_confirmation=bool(settings["require_risky_confirmation"]),
			callbacks=_Callbacks(self),
		)
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

import gui
import wx
import addonHandler

import builtins

try:
	addonHandler.initTranslation()
except:
	pass

# Try to get the translation function (_) from builtins, which NVDA sets up.
# If it's not available or not callable, fall back to a identity function.
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

def onInstall():
	# Translators: Warning message shown when installing the add-on.
	msg = _(
		"Use at your own risk. This add-on uses an AI model to control your "
		"computer's mouse and keyboard. The author is not responsible for any "
		"irreversible actions, data loss, or other damages this add-on may "
		"perform or cause. Please use this tool responsibly and always monitor "
		"the add-on while it is running.\n\n"
		"Do you agree to these terms and wish to install the add-on?"
	)
	# Translators: Title of the warning dialog shown when installing the add-on.
	title = _("Computer Use for NVDA: Warning")
	
	# Use wx.MessageDialog to support custom button labels as requested.
	# This ensures the user sees "Agree and Install" and "Cancel" specifically.
	with wx.MessageDialog(
		gui.mainFrame,
		msg,
		title,
		wx.YES_NO | wx.ICON_WARNING
	) as dlg:
		# Translators: Label for the button to agree and continue installation.
		dlg.SetYesNoLabels(_("Agree and Install"), _("Cancel"))
		res = dlg.ShowModal()
	
	if res != wx.ID_YES:
		raise RuntimeError("Installation cancelled by user.")

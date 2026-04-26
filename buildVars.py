# -*- coding: UTF-8 -*-


def _(arg):
	return arg


addon_info = {
	"addon_name": "computerUse",
	"addon_summary": _("Computer Use"),
	"addon_description": _("""Control the foreground Windows application from an NVDA prompt using OpenAI Computer Use. The add-on captures the active window, sends it to the configured model, and performs guided mouse and keyboard actions with confirmation for risky steps."""),
	"addon_version": "2026.1.0",
	"addon_author": "NVDA Computer Use contributors",
	"addon_url": None,
	"addon_sourceURL": None,
	"addon_docFileName": "readme.html",
	"addon_minimumNVDAVersion": "2023.1",
	"addon_lastTestedNVDAVersion": "2026.1.0",
	"addon_updateChannel": None,
	"addon_license": "GPL v2",
	"addon_licenseURL": "https://www.gnu.org/licenses/gpl-2.0.html",
}


pythonSources = [
	"addon/globalPlugins/computerUse/*.py",
]

i18nSources = pythonSources + ["buildVars.py"]

excludedFiles = [
	"globalPlugins/computerUse/lib/bin/openai.exe",
]

baseLanguage = "en"

markdownExtensions = []

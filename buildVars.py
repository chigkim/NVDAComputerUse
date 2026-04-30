# -*- coding: UTF-8 -*-


def _(arg):
	return arg


addon_info = {
	"addon_name": "computerUse",
	"addon_summary": _("Computer Use"),
	"addon_description": _("""Control the foreground Windows application from an NVDA prompt using OpenAI Computer Use. The add-on captures the active window, sends it to the configured model, and performs mouse and keyboard actions."""),
	"addon_version": "2026.1.7",
	"addon_author": "Chi Kim",
	"addon_url": "https://github.com/chigkim/NVDAComputerUse/",
	"addon_sourceURL": "https://github.com/chigkim/NVDAComputerUse/",
	"addon_docFileName": "readme.html",
	"addon_minimumNVDAVersion": "2025.3.3",
	"addon_lastTestedNVDAVersion": "2025.3.3",
	"addon_updateChannel": "dev",
	"addon_license": "GPL v3",
	"addon_licenseURL": "https://www.gnu.org/licenses/gpl-3.0.en.html",
}


pythonSources = [
	"addon/globalPlugins/ComputerUse/*.py",
	"addon/installTasks.py",
]

addonDataFiles = [
	"addon/globalPlugins/ComputerUse/tools/*.json",
	"addon/globalPlugins/ComputerUse/tools/*.txt",
]

i18nSources = pythonSources + ["buildVars.py"]

excludedFiles = [
	"globalPlugins/ComputerUse/lib/bin/openai.exe",
]

baseLanguage = "en"

markdownExtensions = []

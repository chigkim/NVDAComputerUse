# Computer Use for NVDA

Computer Use lets you describe a task in an NVDA dialog and have OpenAI's Computer Use tool operate the foreground Windows application.

Press NVDA+shift+control+u to open the task dialog. Enter a task, choose Perform, and the add-on captures the active window, sends the screenshot to the configured model, and follows the model's mouse and keyboard actions until the task is complete or the step limit is reached.

This add-on can interact with the same desktop applications that you can. It asks for confirmation before actions that appear destructive, financial, credential-related, or otherwise difficult to reverse.

## Setup

1. Open NVDA Settings.
2. Select the Computer Use category.
3. Enter your OpenAI API key.
4. Adjust the model, max steps, and confirmation settings if needed.

The OpenAI Python package and its dependencies are bundled in the add-on under `globalPlugins/computerUse/lib`.

## Building

Use Python 3.11.9 for this workspace. Do not upgrade or downgrade Python.

To vendor dependencies during development:

```
uv pip install --python ..\.venv\Scripts\python.exe --target addon\globalPlugins\computerUse\lib openai
```

To build the add-on:

```
scons
```

The resulting `.nvda-addon` file is created in this directory.

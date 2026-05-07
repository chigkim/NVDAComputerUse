# Computer Use for NVDA

Computer Use lets you describe a task in an NVDA dialog and have Computer Use tool operate the foreground Windows application.

## WARNING

**Use at your own risk.** This add-on uses an AI model to control your computer's mouse and keyboard. The author is not responsible for any irreversible actions, data loss, or other damages this add-on may perform or cause. Please use this tool responsibly and always monitor the add-on while it is running.

## Usage

1. Open **NVDA Settings**.
2. Select the **Computer Use** category.
3. Enter URL, API key, and model to use via OpenAI compatible Chat Completions API.
4. Press `NVDA+Shift+Control+U` to open the task dialog. Enter a task, choose **Perform**.

The add-on captures the active window, sends the screenshot to the configured model, and follows the model's mouse and keyboard actions until the task is complete, cancelled, or an error occurs.

The same shortcut is used to abort while a task is running.

## Development

### Building

To build the add-on using `uv`:

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Run the build command:

uv run scons

The resulting `.nvda-addon` file is created in the project root.

The OpenAI Python package and its dependencies are bundled in the add-on under `addon/globalPlugins/ComputerUse/lib`.

### UIChallenge App

A standalone UIChallenge is provided in the for develop purpose only. This allows testing "Computer Use" logic.

uv run UIChallenge.py

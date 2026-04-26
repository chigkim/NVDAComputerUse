# Computer Use for NVDA

Computer Use lets you describe a task in an NVDA dialog and have OpenAI's Computer Use tool operate the foreground Windows application.

## WARNING

**Use at your own risk.** This add-on uses an AI model to control your computer's mouse and keyboard. The author is not responsible for any irreversible actions, data loss, or other damages this add-on may perform or cause. Please use this tool responsibly and always monitor the add-on while it is running.

## Usage

This add-on can interact with the desktop applications that is open in the foreground.

1. Open **NVDA Settings**.
2. Select the **Computer Use** category.
3. Enter your **OpenAI API key**.
4. Adjust the model, max steps, and confirmation settings if needed.
5. Press `NVDA+Shift+Control+U` to open the task dialog. Enter a task, choose **Perform**.

The add-on captures the active window, sends the screenshot to the configured model, and follows the model's mouse and keyboard actions until the task is complete or the step limit is reached.

The same shortcut is used to abort while a task is running.

## Development

### Building

To build the add-on using `uv`:

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Run the build command:
   ```bash
   uv run scons
   ```

The resulting `.nvda-addon` file is created in the project root.

The OpenAI Python package and its dependencies are bundled in the add-on under `addon/globalPlugins/ComputerUse/lib`.

### Standalone Test App

A standalone TestApp is provided in the `TestApp` directory for develop purpose only. This allows testing "Computer Use" logic without running NVDA.

1. Install test app dependencies into your local environment:
   ```powershell
   uv pip install pillow openai
   ```
2. Setup environment:
   ```powershell
   cp TestApp/.env.example TestApp/.env
   # Edit TestApp/.env with your API key
   ```
3. Run the test app:
   ```powershell
   uv run python TestApp/app.py
   ```

### Updating Dependencies (Vendoring)

The add-on bundles its own dependencies to ensure it works within NVDA's Python environment. Since NVDA is a 32-bit application, you **must** use a 32-bit Python 3.11 environment when updating these dependencies if they include binary components (like `pydantic-core`).

To vendor or update dependencies:

```bash
# Ensure you are using 32-bit Python 3.11
uv pip install --target addon\globalPlugins\ComputerUse\lib openai pydantic --python 3.11 --platform win32
```

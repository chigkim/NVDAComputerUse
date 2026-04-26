# Windows Computer Use Test App

A standalone Windows test harness for the NVDA Computer Use add-on work. It mirrors the Swift `MacComputerUseTestApp` shape:

- a visible app window with log-producing controls
- a built-in Computer Use runner for testing without NVDA
- action and token logs in the UI and terminal

## Setup

From the repository root, install the standalone app dependencies into the existing venv:

```powershell
uv pip install --python .\.venv\Scripts\python.exe openai pillow
```

The NVDA add-on package is separate and still uses its bundled 32-bit dependencies.

Copy `.env.example` to `.env` and put your OpenAI key there:

```powershell
Copy-Item WindowsComputerUseTestApp\.env.example WindowsComputerUseTestApp\.env
notepad WindowsComputerUseTestApp\.env
```

Expected contents:

```text
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_MODEL=gpt-5.5
# OPENAI_BASE_URL=https://api.openai.com/v1
```

Environment variables still work and take priority over `.env` values.

## Run

```powershell
.\.venv\Scripts\python.exe WindowsComputerUseTestApp\app.py
```

Run a quick import/action mapping check without opening the UI:

```powershell
.\.venv\Scripts\python.exe WindowsComputerUseTestApp\app.py --self-test
```

Run an automatic computer-use prompt after the app opens:

```powershell
.\.venv\Scripts\python.exe WindowsComputerUseTestApp\app.py --prompt "Click cell 13, type hello in the message field, then press Send."
```

Automatic prompt runs close the app after Computer Use finishes. Add `--keep-open` if you want to inspect the UI afterward:

```powershell
.\.venv\Scripts\python.exe WindowsComputerUseTestApp\app.py --keep-open --prompt "Click cell 13, type hello in the message field, then press Send."
```

By default the app keeps a smaller `1040x720` window so screenshots cost fewer tokens. Add `--maximize` if you need a full-screen target.

## What To Test

The app exposes controls that should produce log entries when Computer Use interacts with them:

- Run and Cancel buttons
- Drag Source and Drop Target
- text entry and Send
- popup menu
- radio buttons
- checkbox
- slider
- 5 by 5 number table
- shortcut capture area
- menu commands

The app copies the session log to the clipboard when the built-in Computer Use runner finishes.

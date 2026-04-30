from io import StringIO


configspec = StringIO("""[ComputerUse]
api_key = string(default="")
base_url = string(default="https://api.openai.com/v1")
model = string(default="gpt-5.4")
require_risky_confirmation = boolean(default=True)
trim_conversation = boolean(default=True)
debug_logging = boolean(default=False)
speak_assistant_messages = boolean(default=True)
""")

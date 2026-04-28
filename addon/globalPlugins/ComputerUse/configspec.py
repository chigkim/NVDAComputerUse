from io import StringIO


configspec = StringIO("""[ComputerUse]
api_key = string(default="")
base_url = string(default="https://api.openai.com/v1")
model = string(default="gpt-5.4")
max_steps = integer(default=20, min=1, max=100)
step_delay_ms = integer(default=500, min=0, max=10000)
require_risky_confirmation = boolean(default=True)
debug_logging = boolean(default=False)
""")

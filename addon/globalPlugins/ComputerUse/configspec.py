from io import StringIO


configspec = StringIO("""[ComputerUse]
api_key = string(default="")
model = string(default="gpt-5.5")
max_steps = integer(default=20, min=1, max=100)
step_delay_ms = integer(default=500, min=0, max=10000)
require_risky_confirmation = boolean(default=True)
""")

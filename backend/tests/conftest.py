import os
# Tests must never reach a real LLM, even when the developer's shell has keys exported.
os.environ["ANTHROPIC_API_KEY"] = ""

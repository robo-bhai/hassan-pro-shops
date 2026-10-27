import os

# Rotate the old key: it was hard-coded in models.py. Set REMOVE_BG_API_KEY in your environment.
REMOVE_BG_API_KEY = os.environ.get("REMOVE_BG_API_KEY", "")

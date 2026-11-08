import os

# tests must never start or stop a real OmniRoute
os.environ["MOZHI_MANAGE_OMNIROUTE"] = "0"

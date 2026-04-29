import ctypes
import os

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

os.environ["PYTHONIOENCODING"] = "utf-8"

from app import App

if __name__ == "__main__":
    app = App()
    app.run()

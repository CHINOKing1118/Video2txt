import os
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "video2txt_config.json")
HISTORY_FILE = os.path.join(SCRIPT_DIR, "video2txt_history.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "video2txt.log")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "douyin_downloads")
COOKIE_FILE = os.path.join(SCRIPT_DIR, "cookies.txt")
WHISPER_MODEL_NAME = "small"

os.makedirs(OUTPUT_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "browser": "chrome",
    "base_url": "https://api.xiaomimimo.com/v1",
    "model": "mimo-v2.5-pro",
    "api_key": "",
    "theme": "dark",
    "output_formats": ["md"],
    "delete_media": False,
    "cookies": "",
    "template": "notes",
    "auto_open_folder": False,
    "auto_copy_text": False,
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        # 迁移：旧 output_format (str) → output_formats (list)
        if "output_format" in cfg:
            old = cfg.pop("output_format")
            if "output_formats" not in cfg:
                cfg["output_formats"] = [old] if isinstance(old, str) else old
        cfg.setdefault("output_formats", ["md"])
        return cfg
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def ensure_cookie_file(cookies_text):
    if cookies_text and cookies_text.strip():
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            f.write(cookies_text)
        return COOKIE_FILE
    return None

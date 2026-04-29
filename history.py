import os
import json
import time
import shutil
import threading
from datetime import datetime

from config import HISTORY_FILE, LOG_FILE


# ============================================================
# 日志缓冲写入
# ============================================================

class LogBuffer:
    """批量缓冲日志，定时或满额刷盘，减少 IO"""

    def __init__(self, filepath, flush_interval=3.0, max_buffer=20):
        self._filepath = filepath
        self._buffer = []
        self._lock = threading.Lock()
        self._flush_interval = flush_interval
        self._max_buffer = max_buffer
        self._running = True
        self._thread = threading.Thread(target=self._periodic_flush, daemon=True)
        self._thread.start()

    def write(self, message):
        should_flush = False
        with self._lock:
            self._buffer.append(message)
            if len(self._buffer) >= self._max_buffer:
                should_flush = True
        if should_flush:
            self.flush()

    def flush(self):
        with self._lock:
            if not self._buffer:
                return
            lines = self._buffer[:]
            self._buffer.clear()
        # 在锁外做磁盘 IO
        try:
            with open(self._filepath, "a", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception:
            pass

    def _periodic_flush(self):
        while self._running:
            time.sleep(self._flush_interval)
            self.flush()

    def close(self):
        self._running = False
        self.flush()


_log_buffer = None


def _get_log_buffer():
    global _log_buffer
    if _log_buffer is None:
        _log_buffer = LogBuffer(LOG_FILE)
    return _log_buffer


def write_log(message):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _get_log_buffer().write(f"[{ts}] {message}\n")


def flush_log():
    """手动刷盘（程序退出时调用）"""
    if _log_buffer:
        _log_buffer.flush()


# ============================================================
# 历史记录（带 JSON 损坏自动修复 + 线程安全）
# ============================================================

_history_lock = threading.Lock()


def _backup_and_rebuild():
    try:
        backup = HISTORY_FILE + ".bak"
        shutil.copy2(HISTORY_FILE, backup)
    except Exception:
        pass
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
    except Exception:
        pass


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            write_log("[历史] history.json 格式错误，已重建")
            _backup_and_rebuild()
            return []
        except (json.JSONDecodeError, ValueError) as e:
            write_log(f"[历史] history.json 损坏({e})，已备份并重建")
            _backup_and_rebuild()
            return []
        except Exception as e:
            write_log(f"[历史] 读取 history.json 失败({e})，已重建")
            _backup_and_rebuild()
            return []
    return []


def save_history_entry(entry):
    with _history_lock:
        history = load_history()
        history.insert(0, entry)
        content = json.dumps(history, indent=2, ensure_ascii=False)
        for attempt in range(3):
            try:
                with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                    f.write(content)
                return
            except (OSError, PermissionError):
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
        write_log("[历史] 保存失败（重试耗尽）")


def delete_history_entry(index):
    with _history_lock:
        history = load_history()
        if 0 <= index < len(history):
            history.pop(index)
            content = json.dumps(history, indent=2, ensure_ascii=False)
            for attempt in range(3):
                try:
                    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                        f.write(content)
                    return
                except (OSError, PermissionError):
                    if attempt < 2:
                        time.sleep(0.5 * (attempt + 1))
            write_log("[历史] 删除记录失败（重试耗尽）")
